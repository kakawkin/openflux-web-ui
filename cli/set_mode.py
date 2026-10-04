#!/usr/bin/env python3
"""
CLI utility to switch user mode between Classic and Session.
Usage: openflux-mode <username> <session|classic>
"""
import sys
import os
import asyncio

app_dir = os.environ.get("OPENFLUX_APP_DIR", "/opt/openflux-web-ui")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from app import database, config_generator, service_manager

async def set_user_mode(username: str, mode: str):
    await database.init_db()
    user = await database.get_user_by_username(username)
    if not user:
        print(f"Error: User '{username}' not found in database.")
        sys.exit(1)
        
    mode = mode.lower()
    if mode not in ["session", "classic"]:
        print("Error: Mode must be 'session' or 'classic'.")
        sys.exit(1)
        
    await database.update_user(user["id"], mode=mode)
    updated_user = await database.get_user_by_id(user["id"])
    
    server_conf = config_generator.generate_server_conf(updated_user)
    service_manager.write_user_files(updated_user, server_conf)
    await service_manager.restart_user_service(username)
    
    print(f"Successfully switched user '{username}' to {mode.upper()} mode!")
    print(f"Config updated and openflux@{username}.service restarted.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: openflux-mode <username> <session|classic>")
        sys.exit(1)
    asyncio.run(set_user_mode(sys.argv[1], sys.argv[2]))
