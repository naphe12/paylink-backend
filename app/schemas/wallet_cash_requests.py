from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.wallet_cash_requests import (
    WalletCashRequestStatus,
    WalletCashRequestType,
)


class WalletCashDepositCreate(BaseModel):
    amount: Decimal
    note: str | None = None


class WalletCashWithdrawCreate(BaseModel):
    amount: Decimal
    mobile_number: str
    provider_name: str
    note: str | None = None


class WalletCashDecision(BaseModel):
    note: str | None = None


class WalletCashRequestBase(BaseModel):
    request_id: UUID
    type: WalletCashRequestType
    status: WalletCashRequestStatus
    amount: Decimal
    fee_amount: Decimal
    total_amount: Decimal
    currency_code: str
    mobile_number: str | None = None
    provider_name: str | None = None
    note: str | None = None
    admin_note: str | None = None
    created_at: datetime
    processed_at: datetime | None = None

    class Config:
        from_attributes = True


class WalletCashRequestRead(WalletCashRequestBase):
    pass


class WalletCashRequestUser(BaseModel):
    user_id: UUID
    full_name: str | None = None
    email: str | None = None


class WalletCashRequestAdminRead(WalletCashRequestBase):
    user: WalletCashRequestUser
