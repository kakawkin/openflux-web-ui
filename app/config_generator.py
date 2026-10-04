import os
import json
import zlib
import base64
import secrets
import io
import qrcode
from typing import Dict, Any, List

CONF_DIR = os.environ.get("OPENFLUX_CONF_DIR", "/etc/openflux/users")

def generate_secret(length: int = 32) -> str:
    """Generate a strong random 32-character hex secret for AES-256."""
    return secrets.token_hex(length // 2)

def generate_server_conf(user: Dict[str, Any], conf_dir: str = CONF_DIR) -> str:
    """Generate exit node .conf file for OpenFlux."""
    username = user["username"]
    doc_url = user["doc_url"]
    transport_type = user.get("transport_type", "yandex")
    mode = user.get("mode", "classic")
    direct_port = user.get("direct_port", 8441)
    
    key_path = os.path.join(conf_dir, f"{username}.key").replace("\\", "/")
    cookie_path = os.path.join(conf_dir, f"{username}-cookies.json").replace("\\", "/")
    sock_path = f"/run/openflux/{username}.sock"
    
    lines = [
        "# OpenFlux Exit Node Configuration",
        f"# User: {username} | Mode: {mode.upper()}",
        "",
        "[Interface]",
        "Role = exit",
        "Mode = l4",
        "Codec = batched",
        f"EncryptionKeyFile = {key_path}",
        f"CookieStore = {cookie_path}",
        f"IPCSocket = {sock_path}",
        f"URL = {doc_url}",
        ""
    ]
    
    if mode == "session":
        lines.extend([
            '[Transport "direct"]',
            "Priority = 100",
            f"Listen = 0.0.0.0:{direct_port}",
            ""
        ])
        
    lines.extend([
        f'[Transport "{transport_type}"]',
        "Priority = 50",
        f"URL = {doc_url}",
        ""
    ])
    
    return "\n".join(lines)

def generate_client_conf(user: Dict[str, Any], server_host: str = "127.0.0.1") -> str:
    """Generate client .conf file for OpenFlux Desktop / CLI."""
    username = user["username"]
    doc_url = user["doc_url"]
    transport_type = user.get("transport_type", "yandex")
    mode = user.get("mode", "classic")
    direct_port = user.get("direct_port", 8441)
    
    lines = [
        f"# OpenFlux Client Configuration for {username}",
        "# Save this file as client.conf and run: openflux --config=client.conf",
        "",
        "[Interface]",
        "Role = client",
        "Inbound = socks5",
        "Socks5 = 127.0.0.1:1080",
        "Codec = batched",
        "EncryptionKeyFile = secret.txt",
        f"URL = {doc_url}",
        ""
    ]
    
    if mode == "session":
        lines.extend([
            '[Transport "direct"]',
            "Priority = 100",
            f"Dial = {server_host}:{direct_port}",
            ""
        ])
        
    lines.extend([
        f'[Transport "{transport_type}"]',
        "Priority = 50",
        f"URL = {doc_url}",
        ""
    ])
    
    return "\n".join(lines)

def generate_openflux_link(user: Dict[str, Any], server_host: str = "127.0.0.1") -> str:
    """Encode user connection into an official openflux://v1/ link."""
    username = user["username"]
    doc_url = user["doc_url"]
    transport_type = user.get("transport_type", "yandex")
    mode = user.get("mode", "classic")
    direct_port = user.get("direct_port", 8441)
    secret = user["encryption_key"]
    
    transports: List[Dict[str, Any]] = []
    
    if mode == "session":
        transports.append({
            "type": "direct",
            "priority": 100,
            "dial": f"{server_host}:{direct_port}"
        })
        
    transports.append({
        "type": transport_type,
        "priority": 50,
        "url": doc_url
    })
    
    cfg = {
        "name": username,
        "negotiate": True,
        "codec": "batched",
        "secret": secret,
        "context": doc_url,
        "transports": transports
    }
    
    raw = json.dumps(cfg, separators=(",", ":")).encode("utf-8")
    # Standard raw DEFLATE (wbits = -15) with best compression
    compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    deflated = compressor.compress(raw) + compressor.flush()
    encoded = base64.urlsafe_b64encode(deflated).decode("ascii").rstrip("=")
    return "openflux://v1/" + encoded

def generate_qr_bytes(text: str) -> bytes:
    """Generate QR code PNG image bytes."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
