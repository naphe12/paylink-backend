# app/schemas/user_auth.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# 🧩 Schéma de base (commun à tous)
class UserAuthBase(BaseModel):
    user_id: uuid.UUID
    mfa_enabled: bool = False
    last_login_at: Optional[datetime] = None


# ✳️ Schéma pour la création (register)
class UserAuthCreate(BaseModel):
    user_id: uuid.UUID
    password: str = Field(..., min_length=6, max_length=100)
    mfa_enabled: bool = False


# 🔁 Schéma pour mise à jour (ex: activer MFA ou mise à jour login)
class UserAuthUpdate(BaseModel):
    password: Optional[str] = None
    mfa_enabled: Optional[bool] = None
    last_login_at: Optional[datetime] = None


# 📖 Schéma pour lecture (retour API)
class UserAuthRead(UserAuthBase):
    password_hash: Optional[str] = None  # ⚠️ Facultatif, ne pas exposer publiquement
    model_config = ConfigDict(from_attributes=True)