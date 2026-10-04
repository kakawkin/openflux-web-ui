import os
import io
import psutil
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import database, models, config_generator, service_manager, ipc_client, auth

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

def format_bytes(size: int) -> str:
    power = 2**10
    n = 0
    labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{size:.1f} {labels[n]}"

def get_base_path(request: Request) -> str:
    if request.url.path.startswith("/flux"):
        return "/flux"
    prefix = request.headers.get("x-forwarded-prefix")
    if prefix:
        return "/" + prefix.strip("/")
    referer = request.headers.get("referer", "")
    if "/flux" in referer:
        return "/flux"
    return ""

def get_url(request: Request, path: str) -> str:
    base = get_base_path(request)
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"

async def get_server_host(request: Optional[Request] = None) -> str:
    host = await database.get_setting("server_host")
    if not host or host.strip() == "":
        host = os.environ.get("OPENFLUX_SERVER_HOST", "")
    if not host and request:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if ":" in host:
            host = host.split(":")[0]
    if not host:
        host = "127.0.0.1"
    return host

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield

app = FastAPI(title="OpenFlux Web UI", lifespan=lifespan)
router = APIRouter()

# Mount static files if directory exists
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ----------------- AUTH ROUTES ----------------- #

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    base_path = get_base_path(request)
    sess = await auth.get_current_session(request)
    if sess:
        if sess["role"] == "admin":
            return RedirectResponse(url=get_url(request, "/dashboard"), status_code=status.HTTP_302_FOUND)
        else:
            return RedirectResponse(url=get_url(request, "/my"), status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(request=request, name="login.html", context={
        "error": error,
        "base_path": base_path,
        "authenticated": False,
        "current_user": None
    })

@router.post("/login")
async def login_action(
    request: Request,
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None)
):
    base_path = get_base_path(request)
    user_str = (username or "").strip()
    pass_str = (password or "").strip()

    # If password omitted but username provided for user profile, default password to username
    if user_str and not pass_str and user_str.lower() != "admin":
        pass_str = user_str

    # If username omitted but password provided:
    if not user_str and pass_str:
        if await auth.verify_password(pass_str):
            user_str = "admin"
        else:
            # Check if pass_str matches any profile name
            existing_user = await database.get_user_by_username(pass_str)
            if existing_user:
                user_str = existing_user["username"]

    # 1. Admin login check
    if user_str.lower() == "admin":
        if await auth.verify_password(pass_str):
            token = await auth.create_session_token("admin", "admin")
            response = RedirectResponse(url=get_url(request, "/dashboard"), status_code=status.HTTP_302_FOUND)
            response.set_cookie(key=auth.COOKIE_NAME, value=token, httponly=True, samesite="lax", max_age=30 * 86400)
            return response
        else:
            return templates.TemplateResponse(request=request, name="login.html", context={
                "error": "Неверный пароль администратора",
                "base_path": base_path,
                "authenticated": False,
                "current_user": None
            })

    # 2. User profile login check
    if user_str:
        user = await database.get_user_by_username(user_str)
        if user:
            custom_hash = user.get("password_hash")
            valid = False
            if custom_hash:
                if pass_str and database.hash_password(pass_str) == custom_hash:
                    valid = True
            else:
                if pass_str and pass_str.lower() == user["username"].lower():
                    valid = True

            if valid:
                token = await auth.create_session_token("user", user["username"])
                response = RedirectResponse(url=get_url(request, "/my"), status_code=status.HTTP_302_FOUND)
                response.set_cookie(key=auth.COOKIE_NAME, value=token, httponly=True, samesite="lax", max_age=30 * 86400)
                return response

    return templates.TemplateResponse(request=request, name="login.html", context={
        "error": "Неверный логин или пароль",
        "base_path": base_path,
        "authenticated": False,
        "current_user": None
    })

@router.get("/logout")
async def logout_action(request: Request):
    response = RedirectResponse(url=get_url(request, "/login"), status_code=status.HTTP_302_FOUND)
    response.delete_cookie(auth.COOKIE_NAME)
    return response

# ----------------- NAVIGATION & ROOT ----------------- #

@router.get("/", response_class=HTMLResponse)
async def root_redirect(request: Request):
    sess = await auth.get_current_session(request)
    if sess:
        if sess["role"] == "admin":
            return RedirectResponse(url=get_url(request, "/dashboard"), status_code=status.HTTP_302_FOUND)
        else:
            return RedirectResponse(url=get_url(request, "/my"), status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=get_url(request, "/login"), status_code=status.HTTP_302_FOUND)

# ----------------- ADMIN DASHBOARD ----------------- #

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        return RedirectResponse(url=get_url(request, "/login"), status_code=status.HTTP_302_FOUND)
    if sess["role"] != "admin":
        return RedirectResponse(url=get_url(request, "/my"), status_code=status.HTTP_302_FOUND)

    users = await database.get_users()
    server_host = await get_server_host(request)
    base_path = get_base_path(request)
    
    total_bytes = 0
    for u in users:
        # Check active systemd status
        svc_status = await service_manager.get_service_status(u["username"])
        u["status"] = svc_status

        # Try to read real-time socket metrics
        sock_path = f"/run/openflux/{u['username']}.sock"
        ipc_stat = await ipc_client.read_socket_status(sock_path)
        if ipc_stat:
            u["bytes_in"] = ipc_stat.get("bytes_in", u["bytes_in"])
            u["bytes_out"] = ipc_stat.get("bytes_out", u["bytes_out"])
            if ipc_stat.get("connected"):
                u["status"] = "active"

        u["bytes_in_str"] = format_bytes(u.get("bytes_in", 0))
        u["bytes_out_str"] = format_bytes(u.get("bytes_out", 0))
        total_bytes += u.get("bytes_in", 0) + u.get("bytes_out", 0)

    # System resources
    mem = psutil.virtual_memory()
    next_port = await database.get_next_free_port()
    default_key = config_generator.generate_secret(32)

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "users": users,
        "server_host": server_host,
        "base_path": base_path,
        "next_port": next_port,
        "default_key": default_key,
        "total_traffic_str": format_bytes(total_bytes),
        "ram_used_str": format_bytes(mem.used),
        "ram_total_str": format_bytes(mem.total),
        "authenticated": True,
        "current_user": sess
    })

# ----------------- USER PORTAL (/my) ----------------- #

@router.get("/my", response_class=HTMLResponse)
async def user_portal_page(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        return RedirectResponse(url=get_url(request, "/login"), status_code=status.HTTP_302_FOUND)
    
    if sess["role"] == "admin":
        return RedirectResponse(url=get_url(request, "/dashboard"), status_code=status.HTTP_302_FOUND)

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        response = RedirectResponse(url=get_url(request, "/login"), status_code=status.HTTP_302_FOUND)
        response.delete_cookie(auth.COOKIE_NAME)
        return response

    server_host = await get_server_host(request)
    base_path = get_base_path(request)

    # Check active systemd status
    svc_status = await service_manager.get_service_status(user["username"])
    user["status"] = svc_status

    # Socket metrics
    sock_path = f"/run/openflux/{user['username']}.sock"
    ipc_stat = await ipc_client.read_socket_status(sock_path)
    bytes_in = user.get("bytes_in", 0)
    bytes_out = user.get("bytes_out", 0)
    if ipc_stat:
        bytes_in = ipc_stat.get("bytes_in", bytes_in)
        bytes_out = ipc_stat.get("bytes_out", bytes_out)
        if ipc_stat.get("connected"):
            user["status"] = "active"

    link = config_generator.generate_openflux_link(user, server_host)

    return templates.TemplateResponse(request=request, name="user_dashboard.html", context={
        "user": user,
        "server_host": server_host,
        "base_path": base_path,
        "bytes_in_str": format_bytes(bytes_in),
        "bytes_out_str": format_bytes(bytes_out),
        "link": link,
        "has_custom_password": bool(user.get("password_hash")),
        "authenticated": True,
        "current_user": sess
    })

# ----------------- USER-DEDICATED API (/api/my/...) ----------------- #

@router.get("/api/my/info")
async def api_my_info(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    server_host = await get_server_host(request)
    svc_status = await service_manager.get_service_status(user["username"])
    link = config_generator.generate_openflux_link(user, server_host)

    sock_path = f"/run/openflux/{user['username']}.sock"
    ipc_stat = await ipc_client.read_socket_status(sock_path)
    bytes_in = user.get("bytes_in", 0)
    bytes_out = user.get("bytes_out", 0)
    if ipc_stat:
        bytes_in = ipc_stat.get("bytes_in", bytes_in)
        bytes_out = ipc_stat.get("bytes_out", bytes_out)
        if ipc_stat.get("connected"):
            svc_status = "active"

    return {
        "id": user["id"],
        "username": user["username"],
        "mode": user["mode"],
        "transport_type": user["transport_type"],
        "direct_port": user["direct_port"],
        "has_custom_password": bool(user.get("password_hash")),
        "status": svc_status,
        "bytes_in_str": format_bytes(bytes_in),
        "bytes_out_str": format_bytes(bytes_out),
        "link": link
    }

@router.post("/api/my/mode")
async def api_my_mode(data: models.ModeUpdate, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user_id = sess["user_id"]
    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_mode = data.mode.lower()
    if new_mode not in ["classic", "session"]:
        raise HTTPException(status_code=400, detail="Неверный режим")

    await database.update_user(user_id, mode=new_mode)
    updated_user = await database.get_user_by_id(user_id)
    server_conf = config_generator.generate_server_conf(updated_user)
    service_manager.write_user_files(updated_user, server_conf)
    await service_manager.restart_user_service(updated_user["username"])

    return {"status": "ok", "mode": new_mode}

@router.post("/api/my/restart")
async def api_my_restart(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await service_manager.restart_user_service(user["username"])
    return {"status": "ok"}

@router.get("/api/my/qr")
async def api_my_qr(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    server_host = await get_server_host(request)
    link = config_generator.generate_openflux_link(user, server_host)
    png_bytes = config_generator.generate_qr_bytes(link)

    return Response(content=png_bytes, media_type="image/png")

@router.get("/api/my/config")
async def api_my_config(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    server_host = await get_server_host(request)
    conf_content = config_generator.generate_client_conf(user, server_host)

    headers = {"Content-Disposition": f'attachment; filename="{user["username"]}.conf"'}
    return Response(content=conf_content, media_type="text/plain", headers=headers)

@router.get("/api/my/logs")
async def api_my_logs(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    logs = await service_manager.get_service_logs(sess["username"])
    return {"status": "ok", "logs": logs}

@router.post("/api/my/cookies")
async def api_my_cookies(data: models.CookieInput, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    jar = ipc_client.parse_netscape_cookies(data.content)
    if not jar:
        raise HTTPException(status_code=400, detail="Не удалось распознать cookies в предоставленном тексте")

    cookie_path = os.path.join(service_manager.CONF_DIR, f"{user['username']}-cookies.json")
    ipc_client.write_cookie_file(cookie_path, jar)

    sock_path = f"/run/openflux/{user['username']}.sock"
    applied_ipc = await ipc_client.send_cookies_offer(sock_path, user["transport_type"], jar)

    return {
        "status": "ok",
        "cookies_count": len(jar),
        "applied_to_running_node": applied_ipc
    }

@router.post("/api/my/password")
async def api_my_password(data: models.PasswordChange, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_pass = (data.old_password or "").strip()
    custom_hash = user.get("password_hash")

    # Verify old password
    if custom_hash:
        if not old_pass or database.hash_password(old_pass) != custom_hash:
            raise HTTPException(status_code=400, detail="Неверный текущий пароль")
    else:
        # Default password is username
        if not old_pass or old_pass.lower() != user["username"].lower():
            raise HTTPException(status_code=400, detail="Неверный текущий пароль (по умолчанию это ваше имя профиля)")

    new_pass = data.new_password.strip()
    if len(new_pass) < 4:
        raise HTTPException(status_code=400, detail="Новый пароль должен содержать не менее 4 символов")

    await database.set_user_password(user["id"], new_pass)
    return {"status": "ok", "message": "Пароль успешно изменён!"}

@router.post("/api/my/password/reset")
async def api_my_password_reset(request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "user":
        raise HTTPException(status_code=400, detail="Only for user session")

    user = await database.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await database.set_user_password(user["id"], None)
    return {"status": "ok", "message": "Пароль сброшен на стандартный (совпадает с именем профиля)"}

# ----------------- ADMIN & SHARED USER API ----------------- #

@router.post("/api/users")
async def api_create_user(data: models.UserCreate, request: Request):
    sess = await auth.get_current_session(request)
    if not sess or sess["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin only")

    existing = await database.get_user_by_username(data.username)
    if existing:
        raise HTTPException(status_code=400, detail=f"Пользователь {data.username} уже существует")

    direct_port = data.direct_port
    if not direct_port:
        direct_port = await database.get_next_free_port()

    encryption_key = data.encryption_key
    if not encryption_key or len(encryption_key.strip()) < 20:
        encryption_key = config_generator.generate_secret(32)

    pwd_hash = None
    if data.password and data.password.strip():
        pwd_hash = database.hash_password(data.password.strip())

    user_id = await database.create_user(
        username=data.username,
        doc_url=data.doc_url,
        transport_type=data.transport_type,
        mode=data.mode,
        encryption_key=encryption_key,
        direct_port=direct_port,
        password_hash=pwd_hash
    )

    user = await database.get_user_by_id(user_id)
    server_conf = config_generator.generate_server_conf(user)
    service_manager.write_user_files(user, server_conf)

    # Start systemd unit
    await service_manager.start_user_service(user["username"])

    return {"status": "ok", "id": user_id, "username": user["username"]}

@router.get("/api/users/{user_id}")
async def api_get_user(user_id: int, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    server_host = await get_server_host(request)
    link = config_generator.generate_openflux_link(user, server_host)
    client_conf = config_generator.generate_client_conf(user, server_host)

    return {
        "id": user["id"],
        "username": user["username"],
        "doc_url": user["doc_url"],
        "transport_type": user["transport_type"],
        "mode": user["mode"],
        "direct_port": user["direct_port"],
        "has_custom_password": bool(user.get("password_hash")),
        "link": link,
        "client_conf": client_conf
    }

@router.put("/api/users/{user_id}")
async def api_update_user(user_id: int, data: models.UserUpdate, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_username = user["username"]
    new_username = data.username.strip() if data.username else None
    username_changed = False

    updates = {}
    if sess["role"] == "admin":
        if new_username and new_username != old_username:
            existing = await database.get_user_by_username(new_username)
            if existing and existing["id"] != user_id:
                raise HTTPException(status_code=400, detail=f"Пользователь '{new_username}' уже существует")
            updates["username"] = new_username
            username_changed = True

        if data.doc_url is not None:
            updates["doc_url"] = data.doc_url
        if data.transport_type is not None:
            updates["transport_type"] = data.transport_type
        if data.encryption_key is not None:
            updates["encryption_key"] = data.encryption_key
        if data.direct_port is not None:
            updates["direct_port"] = data.direct_port

        if data.reset_password:
            updates["password_hash"] = None
        elif data.password is not None and data.password.strip():
            updates["password_hash"] = database.hash_password(data.password.strip())
    
    # Mode can be updated by admin or user
    if data.mode is not None:
        if data.mode.lower() in ["classic", "session"]:
            updates["mode"] = data.mode.lower()

    if username_changed:
        # Migrate files, cookies, folder, stop old service
        await service_manager.rename_user(old_username, new_username)

    if updates:
        await database.update_user(user_id, **updates)

    updated_user = await database.get_user_by_id(user_id)
    server_conf = config_generator.generate_server_conf(updated_user)
    service_manager.write_user_files(updated_user, server_conf)

    if username_changed:
        await service_manager.start_user_service(new_username)
    else:
        await service_manager.restart_user_service(updated_user["username"])

    return {"status": "ok", "username": updated_user["username"]}

@router.delete("/api/users/{user_id}")
async def api_delete_user(user_id: int, request: Request):
    sess = await auth.get_current_session(request)
    if not sess or sess["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin only")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await service_manager.disable_user_service(user["username"])
    service_manager.delete_user_files(user["username"])
    await database.delete_user(user_id)

    return {"status": "ok"}

@router.post("/api/users/{user_id}/toggle")
async def api_toggle_user(user_id: int, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    status_str = await service_manager.get_service_status(user["username"])
    if status_str == "active":
        await service_manager.restart_user_service(user["username"])
    else:
        await service_manager.start_user_service(user["username"])

    return {"status": "ok"}

@router.get("/api/users/{user_id}/qr")
async def api_user_qr(user_id: int, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    server_host = await get_server_host(request)
    link = config_generator.generate_openflux_link(user, server_host)
    png_bytes = config_generator.generate_qr_bytes(link)

    return Response(content=png_bytes, media_type="image/png")

@router.get("/api/users/{user_id}/config")
async def api_user_config_download(user_id: int, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    server_host = await get_server_host(request)
    conf_content = config_generator.generate_client_conf(user, server_host)

    headers = {"Content-Disposition": f'attachment; filename="{user["username"]}.conf"'}
    return Response(content=conf_content, media_type="text/plain", headers=headers)

@router.post("/api/users/{user_id}/cookies")
async def api_save_cookies(user_id: int, data: models.CookieInput, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = await database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    jar = ipc_client.parse_netscape_cookies(data.content)
    if not jar:
        raise HTTPException(status_code=400, detail="Не удалось распознать cookies в предоставленном тексте")

    cookie_path = os.path.join(service_manager.CONF_DIR, f"{user['username']}-cookies.json")
    ipc_client.write_cookie_file(cookie_path, jar)

    sock_path = f"/run/openflux/{user['username']}.sock"
    applied_ipc = await ipc_client.send_cookies_offer(sock_path, user["transport_type"], jar)

    return {
        "status": "ok",
        "cookies_count": len(jar),
        "applied_to_running_node": applied_ipc
    }

@router.get("/api/users/by-name/{username}/logs")
async def api_user_logs(username: str, request: Request):
    sess = await auth.get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if sess["role"] != "admin" and sess.get("username") != username:
        raise HTTPException(status_code=403, detail="Forbidden")

    logs = await service_manager.get_service_logs(username)
    return {"status": "ok", "logs": logs}

# ----------------- ADMIN SETTINGS ----------------- #

@router.get("/api/admin/settings")
async def api_get_settings(request: Request):
    await auth.require_admin(request)
    server_host = await get_server_host(request)
    return {
        "status": "ok",
        "server_host": server_host
    }

@router.post("/api/admin/settings")
async def api_update_settings(data: models.SettingsUpdate, request: Request):
    await auth.require_admin(request)
    if data.server_host is not None and data.server_host.strip():
        await database.set_setting("server_host", data.server_host.strip())
    if data.admin_password is not None and data.admin_password.strip():
        await database.set_setting("admin_password", database.hash_password(data.admin_password.strip()))
    return {
        "status": "ok",
        "message": "Настройки успешно сохранены"
    }

# Include both root and /flux prefixes
app.include_router(router)
app.include_router(router, prefix="/flux")
