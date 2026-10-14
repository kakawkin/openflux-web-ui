from pydantic import BaseModel, Field
from typing import Optional, List

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    password: Optional[str] = None
    doc_url: str = Field(..., min_length=5)
    transport_type: str = Field(default="yandex") # yandex, telemost, vyandex, mailru, boards, avito, cupsonline
    mode: str = Field(default="classic") # classic or session
    encryption_key: Optional[str] = None # 32-char hex secret or auto-generated
    direct_port: Optional[int] = None # 8441..8499

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    password: Optional[str] = None
    reset_password: Optional[bool] = None
    doc_url: Optional[str] = None
    transport_type: Optional[str] = None
    mode: Optional[str] = None
    encryption_key: Optional[str] = None
    direct_port: Optional[int] = None
    is_enabled: Optional[bool] = None

class PasswordChange(BaseModel):
    old_password: Optional[str] = None
    new_password: str = Field(..., min_length=4, max_length=64)

class CookieInput(BaseModel):
    content: str # Netscape cookies.txt or JSON string

class ModeUpdate(BaseModel):
    mode: str = Field(..., pattern=r"^(classic|session)$")

class SettingsUpdate(BaseModel):
    server_host: Optional[str] = None
    admin_password: Optional[str] = None

class MyProfileUpdate(BaseModel):
    transport_type: Optional[str] = None
    doc_url: Optional[str] = None
