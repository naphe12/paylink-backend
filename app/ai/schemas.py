from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AiMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: UUID | None = None


class AiConfirmRequest(BaseModel):
    pending_action_id: UUID
    confirm: bool = True


class ParsedIntent(BaseModel):
    intent: str | None = None
    confidence: float | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False


class ResolvedCommand(BaseModel):
    intent: str
    action_code: str
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AiResponse(BaseModel):
    type: str
    message: str
    pending_action_id: UUID | None = None
    parsed_intent: ParsedIntent | None = None
    missing_fields: list[str] = Field(default_factory=list)
    data: dict[str, Any] | None = None


class WalletBalanceData(BaseModel):
    wallet_available: Decimal
    wallet_currency: str
    credit_available: Decimal
    bonus_balance: Decimal | None = None


class PendingActionRead(BaseModel):
    id: UUID
    intent_code: str
    action_code: str
    status: str
    payload: dict[str, Any]
    expires_at: datetime
