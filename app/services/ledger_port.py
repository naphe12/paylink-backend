from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

@dataclass
class LedgerPostResult:
    entry_id: str

class LedgerPort(Protocol):
    async def hold(self, user_id: UUID, currency: str, amount: Decimal, ref: str) -> LedgerPostResult: ...
    async def release(self, user_id: UUID, currency: str, amount: Decimal, ref: str) -> LedgerPostResult: ...
    async def debit(self, user_id: UUID, currency: str, amount: Decimal, ref: str) -> LedgerPostResult: ...
    async def credit(self, user_id: UUID, currency: str, amount: Decimal, ref: str) -> LedgerPostResult: ...
