import os
import shutil
import asyncio
import subprocess
from typing import Dict, Any, Tuple

CONF_DIR = os.environ.get("OPENFLUX_CONF_DIR", "/etc/openflux/users")
RUN_DIR = "/run/openflux"

def is_linux() -> bool:
    return os.name == "posix" and os.path.exists("/bin/systemctl")

def ensure_directories():
    os.makedirs(CONF_DIR, exist_ok=True)
    os.makedirs(RUN_DIR, exist_ok=True)

def write_user_files(user: Dict[str, Any], conf_content: str):
    ensure_directories()
    username = user["username"]
    conf_path = os.path.join(CONF_DIR, f"{username}.conf")
    key_path = os.path.join(CONF_DIR, f"{username}.key")
    
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conf_content)
        
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(user["encryption_key"].strip() + "\n")
        
    if is_linux():
        try:
            os.chmod(key_path, 0o600)
            os.chmod(conf_path, 0o644)
        except Exception:
            pass

def delete_user_files(username: str):
    for filename in [f"{username}.conf", f"{username}.key", f"{username}-cookies.json"]:
        path = os.path.join(CONF_DIR, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
                
    sock_path = os.path.join(RUN_DIR, f"{username}.sock")
    if os.path.exists(sock_path):
        try:
            os.remove(sock_path)
        except Exception:
            pass

async def rename_user(old_username: str, new_username: str) -> bool:
    """Migrates all user files, cookies, and folder from old_username to new_username, then stops/disables old service."""
    ensure_directories()
    if old_username == new_username:
        return True

    # 1. Stop and disable old systemd unit
    await disable_user_service(old_username)

    # 2. Copy/migrate cookies file if present
    old_cookies = os.path.join(CONF_DIR, f"{old_username}-cookies.json")
    new_cookies = os.path.join(CONF_DIR, f"{new_username}-cookies.json")
    if os.path.exists(old_cookies):
        try:
            shutil.copy2(old_cookies, new_cookies)
        except Exception:
            pass

    # 3. Copy/migrate key file if present
    old_key = os.path.join(CONF_DIR, f"{old_username}.key")
    new_key = os.path.join(CONF_DIR, f"{new_username}.key")
    if os.path.exists(old_key) and not os.path.exists(new_key):
        try:
            shutil.copy2(old_key, new_key)
        except Exception:
            pass

    # 4. Copy/migrate folder if present (e.g. /etc/openflux/users/<username>)
    old_folder = os.path.join(CONF_DIR, old_username)
    new_folder = os.path.join(CONF_DIR, new_username)
    if os.path.isdir(old_folder):
        try:
            shutil.copytree(old_folder, new_folder, dirs_exist_ok=True)
            shutil.rmtree(old_folder, ignore_errors=True)
        except Exception:
            pass

    # 5. Clean up old user files and IPC socket
    delete_user_files(old_username)
    return True

async def run_cmd(cmd: list) -> Tuple[int, str, str]:
    if not is_linux():
        return 0, "mock_success", ""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()

async def start_user_service(username: str) -> bool:
    code, out, err = await run_cmd(["systemctl", "enable", "--now", f"openflux@{username}"])
    return code == 0

async def stop_user_service(username: str) -> bool:
    code, out, err = await run_cmd(["systemctl", "stop", f"openflux@{username}"])
    return code == 0

async def restart_user_service(username: str) -> bool:
    code, out, err = await run_cmd(["systemctl", "restart", f"openflux@{username}"])
    return code == 0

async def disable_user_service(username: str) -> bool:
    code, out, err = await run_cmd(["systemctl", "disable", "--now", f"openflux@{username}"])
    return code == 0

async def get_service_status(username: str) -> str:
    """Return 'active', 'inactive', 'failed', or 'unknown'."""
    if not is_linux():
        return "active"
    code, out, err = await run_cmd(["systemctl", "is-active", f"openflux@{username}"])
    return out if out else "inactive"

async def get_service_logs(username: str, lines: int = 50) -> str:
    if not is_linux():
        return f"[Dev Mode] Simulating logs for openflux@{username}...\nDaemon running without errors."
    code, out, err = await run_cmd(["journalctl", "-u", f"openflux@{username}", "-n", str(lines), "--no-pager"])
    return out if out else (err or "No logs found.")
