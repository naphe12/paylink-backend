from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CurrencyPreferenceUpdate(BaseModel):
    display_currency: str


class CurrencyPreferenceRead(BaseModel):
    display_currency: str
    source: str
    available_currencies: list[str] = Field(default_factory=list)


class WalletBalanceCurrencyRead(BaseModel):
    currency_code: str
    available: Decimal
    pending: Decimal
    estimated_display_available: Decimal | None = None
    estimated_display_pending: Decimal | None = None
    rate_to_display_currency: Decimal | None = None
    rate_source: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WalletDisplaySummaryRead(BaseModel):
    display_currency: str
    source: str
    available_currencies: list[str] = Field(default_factory=list)
    estimated_total_available: Decimal | None = None
    estimated_total_pending: Decimal | None = None
    balances: list[WalletBalanceCurrencyRead] = Field(default_factory=list)
    generated_at: datetime
