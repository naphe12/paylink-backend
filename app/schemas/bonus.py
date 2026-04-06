from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BonusBalanceRead(BaseModel):
    bonus_balance: Decimal
    currency_code: str = "BIF"


class BonusTransferCreate(BaseModel):
    recipient_identifier: str
    amount_bif: Decimal = Field(gt=0)


class AgentBonusTransferCreate(BaseModel):
    sender_user_id: UUID
    recipient_user_id: UUID
    amount_bif: Decimal = Field(gt=0)


class BonusTransferRead(BaseModel):
    transfer_id: UUID
    amount_bif: Decimal
    currency_code: str = "BIF"
    sender_user_id: UUID
    recipient_user_id: UUID
    sender_label: str | None = None
    recipient_label: str | None = None
    sender_bonus_balance: Decimal
    recipient_bonus_balance: Decimal
    initiated_by_agent_user_id: UUID | None = None
    created_at: datetime


class BonusHistoryRead(BaseModel):
    id: UUID
    user_id: UUID
    amount_bif: Decimal
    currency_code: str = "BIF"
    source: str
    label: str
    reference_id: UUID | None = None
    counterparty_label: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentBonusUserSummaryRead(BaseModel):
    user_id: UUID
    full_name: str | None = None
    email: str | None = None
    phone_e164: str | None = None
    bonus_balance: Decimal
    currency_code: str = "BIF"
