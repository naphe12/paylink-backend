from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.business_accounts import BusinessAccounts
from app.models.merchant_api_keys import MerchantApiKeys


@dataclass(slots=True)
class MerchantApiAuthContext:
    key_id: UUID
    business_id: UUID
    key_name: str
    key_prefix: str
    membership_role: str = "api"
    metadata: dict | None = None


def _hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_bearer(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    parts = raw_value.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def _extract_merchant_api_key(request: Request, x_api_key: str | None) -> str:
    candidates = [
        x_api_key,
        request.headers.get("X-API-Key"),
        request.headers.get("x-api-key"),
        _extract_bearer(request.headers.get("Authorization")),
        request.query_params.get("api_key"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    raise HTTPException(status_code=401, detail="Cle API marchande manquante")


async def get_current_merchant_api_context(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> MerchantApiAuthContext:
    plain_api_key = _extract_merchant_api_key(request, x_api_key)
    if not plain_api_key.startswith("pk_live_"):
        raise HTTPException(status_code=401, detail="Cle API marchande invalide")

    key_hash = _hash_api_key(plain_api_key)
    key_prefix = plain_api_key[:18]
    key = await db.scalar(
        select(MerchantApiKeys).where(
            MerchantApiKeys.key_prefix == key_prefix,
            MerchantApiKeys.is_active.is_(True),
            MerchantApiKeys.revoked_at.is_(None),
        )
    )
    if not key:
        raise HTTPException(status_code=401, detail="Cle API marchande invalide")
    if not hmac.compare_digest(str(key.key_hash or ""), key_hash):
        raise HTTPException(status_code=401, detail="Cle API marchande invalide")

    business = await db.get(BusinessAccounts, key.business_id)
    if not business or not bool(business.is_active):
        raise HTTPException(status_code=403, detail="Compte business inactif")

    key.last_used_at = datetime.now(timezone.utc)
    key.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return MerchantApiAuthContext(
        key_id=key.key_id,
        business_id=key.business_id,
        key_name=key.key_name,
        key_prefix=key.key_prefix,
        metadata=dict(key.metadata_ or {}),
    )
