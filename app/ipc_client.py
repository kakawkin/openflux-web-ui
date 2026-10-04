import os
import json
import struct
import socket
import asyncio
from typing import Optional, Dict, Any

MSG_COOKIES_REQUEST = 0x01
MSG_COOKIES_OFFER   = 0x02
MSG_STATUS          = 0x03
MSG_COMMAND         = 0x04
MSG_LOG             = 0x05

def parse_netscape_cookies(content: str) -> Dict[str, str]:
    """Parse Netscape cookies.txt or JSON into a key-value jar."""
    content = content.strip()
    # Check if already JSON
    if content.startswith("{") and content.endswith("}"):
        try:
            return json.loads(content)
        except Exception:
            pass

    jar = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            # domain, flag, path, secure, expiration, name, value
            name = parts[5].strip()
            val = parts[6].strip()
            jar[name] = val
        elif "=" in line:
            # Simple Name=Value fallback
            k, v = line.split("=", 1)
            jar[k.strip()] = v.strip().rstrip(";")
    return jar

def write_cookie_file(cookie_path: str, jar: Dict[str, str]):
    """Save cookies jar to the CookieStore JSON file."""
    os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
    with open(cookie_path, "w", encoding="utf-8") as f:
        json.dump(jar, f, indent=2)

async def read_socket_status(sock_path: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
    """Read latest status payload from the OpenFlux IPC Unix domain socket."""
    if not os.path.exists(sock_path) or os.name != "posix":
        return None

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(sock_path),
            timeout=timeout
        )
        try:
            # Read 4-byte header length
            hdr = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
            n = struct.unpack(">I", hdr)[0]
            if n < 1 or n > 1024 * 1024:
                return None
            body = await asyncio.wait_for(reader.readexactly(n), timeout=timeout)
            msg_type = body[0]
            payload_bytes = body[1:]
            if msg_type == MSG_STATUS:
                return json.loads(payload_bytes.decode("utf-8"))
            return None
        finally:
            writer.close()
            await writer.wait_closed()
    except Exception:
        return None

async def send_cookies_offer(sock_path: str, transport_name: str, jar: Dict[str, str], timeout: float = 2.0) -> bool:
    """Send fresh cookies directly to running OpenFlux node via IPC."""
    if not os.path.exists(sock_path) or os.name != "posix":
        return False

    payload = {
        "transport": transport_name,
        "jar": jar
    }
    raw = json.dumps(payload).encode("utf-8")
    length = 1 + len(raw)
    frame = struct.pack(">IB", length, MSG_COOKIES_OFFER) + raw

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(sock_path),
            timeout=timeout
        )
        try:
            writer.write(frame)
            await writer.drain()
            return True
        finally:
            writer.close()
            await writer.wait_closed()
    except Exception:
        return False
