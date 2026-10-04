import os
import aiosqlite
import hashlib
import secrets
from typing import Optional, List, Dict, Any

DB_PATH = os.environ.get("OPENFLUX_DB_PATH", "/etc/openflux/panel.db")
if not os.path.exists(os.path.dirname(DB_PATH)) and os.path.dirname(DB_PATH) != "":
    # Fallback to local directory if /etc/openflux doesn't exist
    DB_PATH = "panel.db"

def hash_password(password: str) -> str:
    salt = "openflux_salt_"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    db = await get_db()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                doc_url TEXT NOT NULL,
                transport_type TEXT NOT NULL DEFAULT 'yandex',
                mode TEXT NOT NULL DEFAULT 'classic',
                encryption_key TEXT NOT NULL,
                direct_port INTEGER UNIQUE,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                bytes_in INTEGER NOT NULL DEFAULT 0,
                bytes_out INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: ensure password_hash column exists
        try:
            await db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            await db.commit()
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Default settings initialization
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'admin_password'")
        row = await cursor.fetchone()
        if not row:
            default_pass = os.environ.get("OPENFLUX_ADMIN_PASSWORD", "admin123")
            default_pass_hash = hash_password(default_pass)
            await db.execute("INSERT INTO settings (key, value) VALUES ('admin_password', ?)", (default_pass_hash,))
            
            default_host = os.environ.get("OPENFLUX_SERVER_HOST", "127.0.0.1")
            await db.execute("INSERT INTO settings (key, value) VALUES ('server_host', ?)", (default_host,))
            await db.commit()

        await db.commit()
    finally:
        await db.close()

async def get_users() -> List[Dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()

async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()

async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()

async def get_next_free_port() -> int:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT direct_port FROM users WHERE direct_port IS NOT NULL")
        rows = await cursor.fetchall()
        used_ports = {r["direct_port"] for r in rows}
        for port in range(8441, 8500):
            if port not in used_ports:
                return port
        return 8500
    finally:
        await db.close()

async def create_user(username: str, doc_url: str, transport_type: str, mode: str, encryption_key: str, direct_port: int, password_hash: Optional[str] = None) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO users (username, password_hash, doc_url, transport_type, mode, encryption_key, direct_port, is_enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (username, password_hash, doc_url, transport_type, mode, encryption_key, direct_port)
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()

async def set_user_password(user_id: int, password: Optional[str]):
    db = await get_db()
    try:
        pwd_hash = hash_password(password.strip()) if password and password.strip() else None
        await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
        await db.commit()
    finally:
        await db.close()

async def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    db = await get_db()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(user_id)
        await db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        await db.commit()
    finally:
        await db.close()

async def delete_user(user_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()
    finally:
        await db.close()

async def get_setting(key: str, default: str = "") -> str:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else default
    except Exception:
        return default
    finally:
        await db.close()

async def set_setting(key: str, value: str):
    db = await get_db()
    try:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()
    finally:
        await db.close()
