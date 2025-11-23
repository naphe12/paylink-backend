from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.agent_transactions import AgentTransactions
from app.models.agents import Agents
from app.models.ledgeraccounts import LedgerAccounts
from app.models.ledgerentries import LedgerEntries
from app.models.ledgerjournal import LedgerJournal
from app.models.wallet_transactions import WalletTransactions
from app.models.wallets import Wallets

router = APIRouter(prefix="/admin/transactions-audit", tags=["Admin Transactions"])


@router.get("")
@router.get("/")
async def audit_transactions(
    wallet_id: UUID | None = Query(None, description="Filtrer par wallet_id"),
    agent_id: UUID | None = Query(None, description="Filtrer par agent_id"),
    search: str | None = Query(None, description="Référence, type, montant..."),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not wallet_id and not agent_id:
        raise HTTPException(
            status_code=400,
            detail="Renseignez au moins wallet_id ou agent_id pour l'audit.",
        )

    ledger_rows = []
    wallet_rows = []
    agent_rows = []

    if wallet_id:
        ledger_rows = await _fetch_ledger_entries(
            db=db,
            wallet_id=wallet_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        wallet_rows = await _fetch_wallet_transactions(
            db=db,
            wallet_id=wallet_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    if agent_id:
        agent_rows = await _fetch_agent_transactions(
            db=db,
            agent_id=agent_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    return {
        "ledger": ledger_rows,
        "wallet_transactions": wallet_rows,
        "agent_transactions": agent_rows,
        "alerts": _build_alerts(
            ledger_rows=ledger_rows,
            wallet_rows=wallet_rows,
            agent_rows=agent_rows,
            unbalanced_journals=await _find_unbalanced_journals(
                db=db, wallet_id=wallet_id
            )
            if wallet_id
            else [],
        ),
    }


async def _fetch_ledger_entries(
    db: AsyncSession,
    *,
    wallet_id: UUID,
    search: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
):
    # Récupère les comptes comptables liés au wallet
    account_ids_stmt = select(LedgerAccounts.account_id).where(
        LedgerAccounts.metadata_["wallet_id"].astext == str(wallet_id)
    )

    stmt = (
        select(
            LedgerEntries.entry_id,
            LedgerEntries.direction,
            LedgerEntries.amount,
            LedgerEntries.currency_code,
            LedgerJournal.journal_id,
            LedgerJournal.tx_id,
            LedgerJournal.occurred_at,
            LedgerJournal.description,
            LedgerAccounts.code.label("account_code"),
        )
        .join(LedgerJournal, LedgerEntries.journal_id == LedgerJournal.journal_id)
        .join(LedgerAccounts, LedgerEntries.account_id == LedgerAccounts.account_id)
        .where(LedgerEntries.account_id.in_(account_ids_stmt))
        .order_by(LedgerJournal.occurred_at.desc())
        .limit(limit)
    )

    if date_from:
        stmt = stmt.where(LedgerJournal.occurred_at >= date_from)
    if date_to:
        stmt = stmt.where(LedgerJournal.occurred_at <= date_to)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            LedgerJournal.description.ilike(pattern)
            | cast(LedgerJournal.tx_id, String).ilike(pattern)
            | LedgerAccounts.code.ilike(pattern)
            | cast(LedgerEntries.amount, String).ilike(pattern)
        )

    rows = (await db.execute(stmt)).all()
    return [
        {
          "entry_id": r.entry_id,
          "direction": r.direction,
          "amount": float(r.amount or 0),
          "currency": r.currency_code,
          "journal_id": str(r.journal_id),
          "tx_id": str(r.tx_id) if r.tx_id else None,
          "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
          "description": r.description,
          "account_code": r.account_code,
        }
        for r in rows
    ]


async def _fetch_wallet_transactions(
    db: AsyncSession,
    *,
    wallet_id: UUID,
    search: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
):
    wallet = await db.get(Wallets, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet introuvable")

    stmt = (
        select(
            WalletTransactions.transaction_id,
            WalletTransactions.amount,
            WalletTransactions.direction,
            WalletTransactions.balance_after,
            WalletTransactions.operation_type,
            WalletTransactions.reference,
            WalletTransactions.description,
            WalletTransactions.created_at,
            WalletTransactions.user_id,
        )
        .where(WalletTransactions.wallet_id == wallet_id)
        .order_by(WalletTransactions.created_at.desc())
        .limit(limit)
    )

    if date_from:
        stmt = stmt.where(WalletTransactions.created_at >= date_from)
    if date_to:
        stmt = stmt.where(WalletTransactions.created_at <= date_to)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            WalletTransactions.reference.ilike(pattern)
            | WalletTransactions.operation_type.ilike(pattern)
            | cast(WalletTransactions.description, String).ilike(pattern)
            | cast(WalletTransactions.amount, String).ilike(pattern)
        )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "transaction_id": str(r.transaction_id),
            "amount": float(r.amount),
            "direction": r.direction,
            "balance_after": float(r.balance_after),
            "operation_type": r.operation_type,
            "reference": r.reference,
            "description": r.description or "",
            "created_at": r.created_at.isoformat(),
            "user_id": str(r.user_id) if r.user_id else None,
        }
        for r in rows
    ]


async def _fetch_agent_transactions(
    db: AsyncSession,
    *,
    agent_id: UUID,
    search: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
):
    agent = await db.get(Agents, agent_id)
    if not agent:
        raise HTTPException(404, "Agent introuvable")

    stmt = (
        select(AgentTransactions)
        .where(AgentTransactions.agent_user_id == agent.user_id)
        .order_by(AgentTransactions.created_at.desc())
        .limit(limit)
    )

    if date_from:
        stmt = stmt.where(AgentTransactions.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AgentTransactions.created_at <= date_to)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            cast(AgentTransactions.related_tx, String).ilike(pattern)
            | cast(AgentTransactions.tx_type, String).ilike(pattern)
            | cast(AgentTransactions.amount, String).ilike(pattern)
        )

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.transaction_id,
            "related_tx": str(r.related_tx),
            "direction": r.direction,
            "type": r.tx_type,
            "amount": float(r.amount),
            "commission": float(r.commission or 0),
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def _find_unbalanced_journals(db: AsyncSession, wallet_id: UUID):
    account_ids_stmt = select(LedgerAccounts.account_id).where(
        LedgerAccounts.metadata_["wallet_id"].astext == str(wallet_id)
    )
    sums_stmt = (
        select(
            LedgerEntries.journal_id,
            func.sum(
                case(
                    (LedgerEntries.direction == "debit", LedgerEntries.amount), else_=0
                )
            ).label("debit"),
            func.sum(
                case(
                    (LedgerEntries.direction == "credit", LedgerEntries.amount), else_=0
                )
            ).label("credit"),
        )
        .where(LedgerEntries.account_id.in_(account_ids_stmt))
        .group_by(LedgerEntries.journal_id)
        .having(func.sum(LedgerEntries.amount) > 0)
    )
    rows = (await db.execute(sums_stmt)).all()
    alerts = []
    for r in rows:
        debit = r.debit or 0
        credit = r.credit or 0
        if debit != credit:
            alerts.append(
                {
                    "journal_id": str(r.journal_id),
                    "debit": float(debit),
                    "credit": float(credit),
                    "gap": float(debit - credit),
                    "type": "ledger_unbalanced",
                    "message": "Journal non équilibré pour ce wallet.",
                }
            )
    return alerts


def _build_alerts(
    *,
    ledger_rows: list[dict],
    wallet_rows: list[dict],
    agent_rows: list[dict],
    unbalanced_journals: list[dict],
):
    alerts: list[dict] = []

    if unbalanced_journals:
        alerts.extend(unbalanced_journals)

    # Dérive des drifts nets entre ledger et wallet history
    def net(rows, key="direction", amount="amount"):
        total = 0
        for r in rows:
            direction = (r.get(key) or "").lower()
            amt = float(r.get(amount) or 0)
            if direction in ("credit", "in"):
                total += amt
            elif direction in ("debit", "out"):
                total -= amt
        return total

    net_ledger = net(ledger_rows, key="direction", amount="amount")
    net_wallet = net(wallet_rows, key="direction", amount="amount")
    drift = net_wallet - net_ledger
    if abs(drift) > 1:  # tolérance 1 unité monétaire
        alerts.append(
            {
                "type": "ledger_wallet_drift",
                "message": "Écart entre ledger et wallet_history.",
                "details": {"net_ledger": net_ledger, "net_wallet": net_wallet, "drift": drift},
            }
        )

    # Duplicatas de référence côté wallet
    ref_counts: dict[str, list[dict]] = {}
    for row in wallet_rows:
        ref = row.get("reference") or ""
        if not ref:
            continue
        ref_counts.setdefault(ref, []).append(row)
    for ref, rows in ref_counts.items():
        if len(rows) > 1:
            alerts.append(
                {
                    "type": "wallet_duplicate_reference",
                    "message": f"Référence dupliquée dans wallet_transactions: {ref}",
                    "details": {"count": len(rows)},
                }
            )

    # Montants élevés côté agent
    high_agent = [r for r in agent_rows if abs(float(r.get("amount") or 0)) >= 1_000_000]
    for row in high_agent:
        alerts.append(
            {
                "type": "agent_high_amount",
                "message": "Montant agent élevé détecté.",
                "details": {
                    "amount": float(row.get("amount") or 0),
                    "related_tx": row.get("related_tx"),
                },
            }
        )

    return alerts
