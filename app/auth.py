import hmac
import hashlib
import time
import secrets
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from app import database

COOKIE_NAME = "openflux_session"
_SECRET_KEY: Optional[str] = None

async def get_secret_key() -> str:
    global _SECRET_KEY
    if _SECRET_KEY is None:
        key = await database.get_setting("session_secret")
        if not key:
            key = secrets.token_hex(32)
            await database.set_setting("session_secret", key)
        _SECRET_KEY = key
    return _SECRET_KEY

async def create_session_token(role: str, username: str) -> str:
    secret = await get_secret_key()
    ts = int(time.time())
    payload = f"{role}:{username}:{ts}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

async def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or token.count(":") != 3:
        return None
    try:
        role, username, ts_str, sig = token.split(":")
        secret = await get_secret_key()
        payload = f"{role}:{username}:{ts_str}"
        expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        
        ts = int(ts_str)
        # Session valid for 30 days
        if time.time() - ts > 30 * 86400:
            return None
            
        return {"role": role, "username": username}
    except Exception:
        return None

async def get_current_session(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    sess_data = await verify_session_token(token)
    if not sess_data:
        return None
        
    role = sess_data.get("role")
    username = sess_data.get("username")
    
    if role == "admin":
        return {"role": "admin", "username": "admin"}
    elif role == "user" and username:
        user = await database.get_user_by_username(username)
        if not user:
            return None
        return {"role": "user", "username": user["username"], "user_id": user["id"], "user": user}
        
    return None

async def is_authenticated(request: Request) -> bool:
    sess = await get_current_session(request)
    return sess is not None

async def is_admin(request: Request) -> bool:
    sess = await get_current_session(request)
    return sess is not None and sess.get("role") == "admin"

async def verify_password(password: str) -> bool:
    expected_hash = await database.get_setting("admin_password")
    return database.hash_password(password) == expected_hash

async def require_auth(request: Request):
    if not (await is_authenticated(request)):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )

async def require_admin(request: Request):
    if not (await is_admin(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges required"
        )
