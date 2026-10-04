#!/usr/bin/env python3
"""
CLI utility to display OpenFlux QR code and link in the terminal.
Usage: openflux-qr <username>
"""
import sys
import os
import asyncio
import qrcode

# Add app to path
app_dir = os.environ.get("OPENFLUX_APP_DIR", "/opt/openflux-web-ui")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from app import database, config_generator

async def show(username: str):
    await database.init_db()
    user = await database.get_user_by_username(username)
    if not user:
        print(f"Error: User '{username}' not found in database.")
        sys.exit(1)
        
    server_host = await database.get_setting("server_host", "127.0.0.1")
    link = config_generator.generate_openflux_link(user, server_host)
    
    print("\n" + "=" * 60)
    print(f"  OpenFlux QR Code for user: {username}")
    print(f"  Mode: {user.get('mode', 'classic').upper()} | Transport: {user.get('transport_type', 'yandex')}")
    print("=" * 60 + "\n")
    
    qr = qrcode.QRCode()
    qr.add_data(link)
    qr.print_ascii(invert=True)
    
    print("\nOpenFlux Link:")
    print(link)
    print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: openflux-qr <username>")
        sys.exit(1)
    asyncio.run(show(sys.argv[1]))
