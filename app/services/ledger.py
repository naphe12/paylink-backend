from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Mapping, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledgeraccounts import LedgerAccounts
from app.models.ledgerentries import LedgerEntries
from app.models.ledgerjournal import LedgerJournal
from app.models.wallets import Wallets

Direction = Literal["debit", "credit"]


@dataclass(frozen=True)
class LedgerLine:
    account: LedgerAccounts
    direction: Direction
    amount: Decimal
    currency_code: str


class LedgerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_wallet_account(self, wallet: Wallets) -> LedgerAccounts:
        stmt = select(LedgerAccounts).where(
            LedgerAccounts.metadata_["wallet_id"].astext == str(wallet.wallet_id)
        )
        account = await self.db.scalar(stmt)
        if account:
            return account

        account = LedgerAccounts(
            code=f"WALLET::{wallet.wallet_id}",
            name=f"Wallet {wallet.wallet_id}",
            currency_code=wallet.currency_code,
            metadata_={
                "wallet_id": str(wallet.wallet_id),
                "user_id": str(wallet.user_id) if wallet.user_id else None,
            },
        )
        self.db.add(account)
        await self.db.flush()
        return account

    async def get_account_by_code(self, code: str) -> LedgerAccounts:
        account = await self.db.scalar(
            select(LedgerAccounts).where(LedgerAccounts.code == code)
        )
        if not account:
            raise LookupError(f"Compte comptable '{code}' introuvable.")
        return account

    async def post_journal(
        self,
        *,
        tx_id: UUID | None,
        description: str,
        entries: Sequence[LedgerLine],
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerJournal:
        if len(entries) < 2:
            raise ValueError("Une écriture doit contenir au moins deux lignes.")

        total_debit = sum(line.amount for line in entries if line.direction == "debit")
        total_credit = sum(line.amount for line in entries if line.direction == "credit")
        if total_debit != total_credit:
            raise ValueError("Débit et crédit ne sont pas équilibrés.")

        journal = LedgerJournal(
            tx_id=tx_id,
            description=description,
            metadata_=metadata or {},
        )
        self.db.add(journal)
        await self.db.flush()

        for line in entries:
            self.db.add(
                LedgerEntries(
                    journal_id=journal.journal_id,
                    account_id=line.account.account_id,
                    direction=line.direction,
                    amount=line.amount,
                    currency_code=line.currency_code,
                )
            )

        return journal
