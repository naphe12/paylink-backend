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

    @staticmethod
    def _candidate_codes(code: str) -> list[str]:
        normalized_code = str(code or "").strip()
        if not normalized_code:
            return []

        aliases = [normalized_code]
        legacy_map = {
            "LEDGER::CREDIT_LINE": ["LEDGER_CREDIT"],
            "LEDGER::CASH_IN": ["LEDGER_CASH_IN", "WALLET_CASH_IN"],
            "LEDGER::CASH_OUT": ["LEDGER_CASH_OUT", "WALLET_CASH_OUT"],
        }
        aliases.extend(legacy_map.get(normalized_code, []))
        return aliases

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
        normalized_code = str(code or "").strip()
        candidate_codes = self._candidate_codes(normalized_code)

        account = await self.db.scalar(
            select(LedgerAccounts).where(LedgerAccounts.code.in_(candidate_codes))
        )
        if not account:
            raise LookupError(
                f"Compte comptable '{normalized_code}' introuvable. "
                f"Codes testes: {', '.join(candidate_codes) or '-'}."
            )
        return account

    async def get_cash_account(
        self,
        *,
        direction: Literal["in", "out"],
        currency_code: str,
    ) -> LedgerAccounts:
        normalized_direction = str(direction or "").strip().lower()
        normalized_currency = str(currency_code or "").strip().upper()
        if normalized_direction not in {"in", "out"}:
            raise ValueError(f"Unknown cash direction '{direction}'.")

        suffix = "IN" if normalized_direction == "in" else "OUT"
        candidate_codes = [
            f"LEDGER::CASH_{suffix}_{normalized_currency}",
            *self._candidate_codes(f"LEDGER::CASH_{suffix}"),
        ]

        account = await self.db.scalar(
            select(LedgerAccounts).where(LedgerAccounts.code.in_(candidate_codes))
        )
        if not account:
            raise LookupError(
                "Compte de compensation cash introuvable "
                f"(direction={normalized_direction}, currency={normalized_currency}). "
                f"Codes testes: {', '.join(candidate_codes)}."
            )
        return account

    async def get_cash_in_account(self, currency_code: str) -> LedgerAccounts:
        return await self.get_cash_account(direction="in", currency_code=currency_code)

    async def get_cash_out_account(self, currency_code: str) -> LedgerAccounts:
        return await self.get_cash_account(direction="out", currency_code=currency_code)

    async def ensure_system_account(
        self,
        *,
        code: str,
        name: str,
        currency_code: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerAccounts:
        candidate_codes = self._candidate_codes(code)
        account = await self.db.scalar(
            select(LedgerAccounts).where(LedgerAccounts.code.in_(candidate_codes))
        )
        if account:
            return account

        account = LedgerAccounts(
            code=code,
            name=name,
            currency_code=(currency_code or "").upper(),
            metadata_=dict(metadata or {}),
        )
        self.db.add(account)
        await self.db.flush()
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

        currencies = {str(line.currency_code or "").upper() for line in entries}
        if len(currencies) != 1:
            raise ValueError("Une ecriture comptable doit utiliser une seule devise.")

        for idx, line in enumerate(entries):
            if line.direction not in ("debit", "credit"):
                raise ValueError(f"Ligne {idx + 1}: direction invalide '{line.direction}'.")
            if line.amount is None or Decimal(line.amount) <= Decimal("0"):
                raise ValueError(f"Ligne {idx + 1}: montant invalide (doit etre > 0).")
            account_currency = str(getattr(line.account, "currency_code", "") or "").upper()
            line_currency = str(line.currency_code or "").upper()
            if account_currency and line_currency and account_currency != line_currency:
                raise ValueError(
                    f"Ligne {idx + 1}: devise incoherente compte={account_currency}, ligne={line_currency}."
                )

        total_debit = sum(Decimal(line.amount) for line in entries if line.direction == "debit")
        total_credit = sum(Decimal(line.amount) for line in entries if line.direction == "credit")
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
