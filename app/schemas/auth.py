from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone_e164: Optional[str] = None
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserPublic(BaseModel):
    user_id: str
    full_name: str
    email: Optional[str] = None

    class Config:
        from_attributes = True