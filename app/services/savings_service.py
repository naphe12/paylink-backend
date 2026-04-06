from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.savings_goals import SavingsGoals
from app.models.savings_movements import SavingsMovements
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement


def _to_decimal(value, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def _primary_wallet_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )


def _normalize_round_up_rule(metadata: dict | None) -> dict:
    raw = dict((metadata or {}).get("round_up_rule") or {})
    increment = raw.get("increment")
    max_amount = raw.get("max_amount")
    return {
        "enabled": bool(raw.get("enabled", False)),
        "increment": _to_decimal(increment) if increment not in (None, "") else None,
        "max_amount": _to_decimal(max_amount) if max_amount not in (None, "") else None,
        "last_applied_at": raw.get("last_applied_at"),
        "updated_at": raw.get("updated_at"),
    }


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _advance_auto_contribution(next_run_at: datetime, frequency: str) -> datetime:
    if frequency == "daily":
        return next_run_at + timedelta(days=1)
    if frequency == "weekly":
        return next_run_at + timedelta(days=7)
    if frequency == "monthly":
        return next_run_at + timedelta(days=30)
    raise HTTPException(status_code=400, detail="Frequence automatique invalide")


def _normalize_auto_contribution_rule(metadata: dict | None) -> dict:
    raw = dict((metadata or {}).get("auto_contribution_rule") or {})
    next_run_at = _parse_datetime(raw.get("next_run_at"))
    last_applied_at = _parse_datetime(raw.get("last_applied_at"))
    updated_at = _parse_datetime(raw.get("updated_at"))
    return {
        "enabled": bool(raw.get("enabled", False)),
        "amount": _to_decimal(raw.get("amount")) if raw.get("amount") not in (None, "") else None,
        "frequency": raw.get("frequency"),
        "next_run_at": next_run_at,
        "last_applied_at": last_applied_at,
        "updated_at": updated_at,
        "is_due": bool(next_run_at and next_run_at <= datetime.now(timezone.utc) and raw.get("enabled", False)),
    }


def _round_up_delta(spent_amount: Decimal, increment: Decimal) -> Decimal:
    remainder = spent_amount % increment
    if remainder == 0:
        return Decimal("0")
    return increment - remainder


async def _credit_goal_from_wallet(
    db: AsyncSession,
    *,
    goal: SavingsGoals,
    wallet: Wallets,
    current_user: Users,
    amount: Decimal,
    source: str,
    note: str | None = None,
    metadata: dict | None = None,
    description: str,
) -> None:
    if Decimal(str(wallet.available or 0)) < amount:
        raise HTTPException(status_code=400, detail="Solde insuffisant")

    wallet.available = Decimal(str(wallet.available or 0)) - amount
    goal.current_amount = Decimal(str(goal.current_amount or 0)) + amount
    goal.updated_at = datetime.now(timezone.utc)
    if Decimal(str(goal.current_amount)) >= Decimal(str(goal.target_amount)):
        goal.status = "completed"

    movement = SavingsMovements(
        goal_id=goal.goal_id,
        user_id=current_user.user_id,
        amount=amount,
        currency_code=goal.currency_code,
        direction="in",
        source=source,
        note=note,
        metadata_=metadata or {},
    )
    db.add(movement)

    wallet_movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="savings_goal_contribution",
        reference=str(goal.goal_id),
        description=description,
    )

    tx = Transactions(
        initiated_by=current_user.user_id,
        sender_wallet=wallet.wallet_id,
        receiver_wallet=wallet.wallet_id,
        amount=amount,
        currency_code=wallet.currency_code,
        channel="internal",
        status="succeeded",
        description=description,
    )
    db.add(tx)
    await db.flush()

    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    savings_account = await ledger.ensure_system_account(
        code=f"SAVINGS_GOAL_{goal.goal_id}",
        name=f"Epargne client {goal.title}",
        currency_code=goal.currency_code,
        metadata={"kind": "savings_goal", "goal_id": str(goal.goal_id), "user_id": str(current_user.user_id)},
    )
    journal_metadata = {
        "operation": "savings_goal_contribution",
        "goal_id": str(goal.goal_id),
        "user_id": str(current_user.user_id),
        "transaction_id": str(tx.tx_id),
        "source": source,
    }
    if metadata:
        journal_metadata["source_metadata"] = metadata
    if wallet_movement:
        journal_metadata["wallet_movement_id"] = str(wallet_movement.transaction_id)
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=description,
        metadata=journal_metadata,
        entries=[
            LedgerLine(account=wallet_account, direction="debit", amount=amount, currency_code=wallet.currency_code),
            LedgerLine(account=savings_account, direction="credit", amount=amount, currency_code=goal.currency_code),
        ],
    )


def _serialize_goal(goal: SavingsGoals, movements: list[SavingsMovements] | None = None) -> dict:
    current_amount = Decimal(str(goal.current_amount or 0))
    target_amount = Decimal(str(goal.target_amount or 0))
    progress = float(min((current_amount / target_amount) * Decimal("100"), Decimal("100"))) if target_amount > 0 else 0
    round_up_rule = _normalize_round_up_rule(goal.metadata_ or {})
    auto_contribution_rule = _normalize_auto_contribution_rule(goal.metadata_ or {})
    return {
        "goal_id": goal.goal_id,
        "user_id": goal.user_id,
        "title": goal.title,
        "note": goal.note,
        "currency_code": goal.currency_code,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "locked": bool(goal.locked),
        "target_date": goal.target_date,
        "status": goal.status,
        "metadata": dict(goal.metadata_ or {}),
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
        "progress_percent": round(progress, 2),
        "remaining_amount": max(target_amount - current_amount, Decimal("0")),
        "round_up_rule": round_up_rule,
        "auto_contribution_rule": auto_contribution_rule,
        "movements": movements or [],
    }


async def create_savings_goal(db: AsyncSession, *, current_user: Users, payload) -> dict:
    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    item = SavingsGoals(
        user_id=current_user.user_id,
        title=payload.title.strip(),
        note=payload.note,
        currency_code=str(wallet.currency_code or "").upper(),
        target_amount=payload.target_amount,
        current_amount=Decimal("0"),
        locked=payload.locked,
        target_date=payload.target_date,
        status="active",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _serialize_goal(item)


async def list_savings_goals(db: AsyncSession, *, current_user: Users) -> list[dict]:
    goals = (
        await db.execute(
            select(SavingsGoals)
            .where(SavingsGoals.user_id == current_user.user_id)
            .order_by(SavingsGoals.created_at.desc())
        )
    ).scalars().all()
    goal_ids = [goal.goal_id for goal in goals]
    movement_rows = []
    if goal_ids:
        movement_rows = (
            await db.execute(
                select(SavingsMovements)
                .where(SavingsMovements.goal_id.in_(goal_ids))
                .order_by(SavingsMovements.created_at.desc())
            )
        ).scalars().all()
    grouped = {}
    for movement in movement_rows:
        grouped.setdefault(movement.goal_id, []).append(movement)
    return [_serialize_goal(goal, grouped.get(goal.goal_id, [])) for goal in goals]


async def get_savings_goal_detail(db: AsyncSession, *, current_user: Users, goal_id: UUID) -> dict:
    goal = await db.scalar(
        select(SavingsGoals).where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    movements = (
        await db.execute(
            select(SavingsMovements)
            .where(SavingsMovements.goal_id == goal.goal_id)
            .order_by(SavingsMovements.created_at.desc())
        )
    ).scalars().all()
    return _serialize_goal(goal, movements)


async def contribute_savings_goal(db: AsyncSession, *, current_user: Users, goal_id: UUID, payload) -> dict:
    goal = await db.scalar(
        select(SavingsGoals)
        .where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
        .with_for_update()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    if goal.status != "active":
        raise HTTPException(status_code=400, detail="Objectif non actif")

    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    if str(wallet.currency_code or "").upper() != str(goal.currency_code or "").upper():
        raise HTTPException(status_code=400, detail="Devise incompatible")

    amount = Decimal(str(payload.amount))
    await _credit_goal_from_wallet(
        db,
        goal=goal,
        wallet=wallet,
        current_user=current_user,
        amount=amount,
        source="wallet",
        note=payload.note,
        description=f"Epargne {goal.title}",
    )

    await db.commit()
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


async def withdraw_savings_goal(db: AsyncSession, *, current_user: Users, goal_id: UUID, payload) -> dict:
    goal = await db.scalar(
        select(SavingsGoals)
        .where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
        .with_for_update()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    if goal.locked:
        raise HTTPException(status_code=400, detail="Cet objectif est verrouille")

    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    amount = Decimal(str(payload.amount))
    current_amount = Decimal(str(goal.current_amount or 0))
    if current_amount < amount:
        raise HTTPException(status_code=400, detail="Montant d'epargne insuffisant")

    goal.current_amount = current_amount - amount
    goal.updated_at = datetime.now(timezone.utc)
    if goal.status == "completed" and Decimal(str(goal.current_amount)) < Decimal(str(goal.target_amount)):
        goal.status = "active"

    wallet.available = Decimal(str(wallet.available or 0)) + amount

    movement = SavingsMovements(
        goal_id=goal.goal_id,
        user_id=current_user.user_id,
        amount=amount,
        currency_code=goal.currency_code,
        direction="out",
        source="wallet",
        note=payload.note,
    )
    db.add(movement)

    wallet_movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="credit",
        operation_type="savings_goal_withdrawal",
        reference=str(goal.goal_id),
        description=f"Retrait epargne {goal.title}",
    )

    tx = Transactions(
        initiated_by=current_user.user_id,
        sender_wallet=wallet.wallet_id,
        receiver_wallet=wallet.wallet_id,
        amount=amount,
        currency_code=wallet.currency_code,
        channel="internal",
        status="succeeded",
        description=f"Retrait epargne {goal.title}",
    )
    db.add(tx)
    await db.flush()

    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    savings_account = await ledger.ensure_system_account(
        code=f"SAVINGS_GOAL_{goal.goal_id}",
        name=f"Epargne client {goal.title}",
        currency_code=goal.currency_code,
        metadata={"kind": "savings_goal", "goal_id": str(goal.goal_id), "user_id": str(current_user.user_id)},
    )
    metadata = {
        "operation": "savings_goal_withdrawal",
        "goal_id": str(goal.goal_id),
        "user_id": str(current_user.user_id),
        "transaction_id": str(tx.tx_id),
    }
    if wallet_movement:
        metadata["wallet_movement_id"] = str(wallet_movement.transaction_id)
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=f"Retrait epargne {goal.title}",
        metadata=metadata,
        entries=[
            LedgerLine(account=savings_account, direction="debit", amount=amount, currency_code=goal.currency_code),
            LedgerLine(account=wallet_account, direction="credit", amount=amount, currency_code=wallet.currency_code),
        ],
    )

    await db.commit()
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


async def configure_savings_round_up(db: AsyncSession, *, current_user: Users, goal_id: UUID, payload) -> dict:
    goal = await db.scalar(
        select(SavingsGoals)
        .where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
        .with_for_update()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")

    metadata = dict(goal.metadata_ or {})
    metadata["round_up_rule"] = {
        "enabled": bool(payload.enabled),
        "increment": str(payload.increment),
        "max_amount": str(payload.max_amount) if payload.max_amount is not None else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_applied_at": (metadata.get("round_up_rule") or {}).get("last_applied_at"),
    }
    goal.metadata_ = metadata
    goal.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


async def apply_savings_round_up(db: AsyncSession, *, current_user: Users, goal_id: UUID, payload) -> dict:
    goal = await db.scalar(
        select(SavingsGoals)
        .where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
        .with_for_update()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    if goal.status != "active":
        raise HTTPException(status_code=400, detail="Objectif non actif")

    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    if str(wallet.currency_code or "").upper() != str(goal.currency_code or "").upper():
        raise HTTPException(status_code=400, detail="Devise incompatible")

    rule = _normalize_round_up_rule(goal.metadata_ or {})
    if not rule["enabled"] or not rule["increment"]:
        raise HTTPException(status_code=400, detail="Arrondi automatique non configure")

    spent_amount = Decimal(str(payload.spent_amount))
    raw_amount = _round_up_delta(spent_amount, rule["increment"])
    if raw_amount <= 0:
        raise HTTPException(status_code=400, detail="Aucun arrondi a appliquer pour ce montant")

    capped = False
    applied_amount = raw_amount
    if rule["max_amount"] is not None and applied_amount > rule["max_amount"]:
        applied_amount = rule["max_amount"]
        capped = True

    await _credit_goal_from_wallet(
        db,
        goal=goal,
        wallet=wallet,
        current_user=current_user,
        amount=applied_amount,
        source="round_up",
        note=payload.note or f"Arrondi automatique depuis une depense de {spent_amount}",
        metadata={
            "spent_amount": str(spent_amount),
            "increment": str(rule["increment"]),
            "raw_round_up_amount": str(raw_amount),
            "capped": capped,
        },
        description=f"Arrondi epargne {goal.title}",
    )

    metadata = dict(goal.metadata_ or {})
    current_rule = dict(metadata.get("round_up_rule") or {})
    current_rule["last_applied_at"] = datetime.now(timezone.utc).isoformat()
    current_rule["updated_at"] = current_rule.get("updated_at") or datetime.now(timezone.utc).isoformat()
    metadata["round_up_rule"] = current_rule
    goal.metadata_ = metadata
    goal.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


async def configure_savings_auto_contribution(db: AsyncSession, *, current_user: Users, goal_id: UUID, payload) -> dict:
    goal = await db.scalar(
        select(SavingsGoals)
        .where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
        .with_for_update()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")

    frequency = str(payload.frequency or "").strip().lower()
    if frequency not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="Frequence automatique invalide")

    next_run_at = payload.next_run_at
    if next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=timezone.utc)

    metadata = dict(goal.metadata_ or {})
    metadata["auto_contribution_rule"] = {
        "enabled": bool(payload.enabled),
        "amount": str(payload.amount),
        "frequency": frequency,
        "next_run_at": next_run_at.isoformat(),
        "last_applied_at": (metadata.get("auto_contribution_rule") or {}).get("last_applied_at"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    goal.metadata_ = metadata
    goal.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


async def _run_goal_auto_contribution(
    db: AsyncSession,
    *,
    goal: SavingsGoals,
    current_user: Users,
    note: str | None = None,
    require_due: bool,
) -> dict:
    if goal.status != "active":
        raise HTTPException(status_code=400, detail="Objectif non actif")

    wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    if str(wallet.currency_code or "").upper() != str(goal.currency_code or "").upper():
        raise HTTPException(status_code=400, detail="Devise incompatible")

    metadata = dict(goal.metadata_ or {})
    rule = _normalize_auto_contribution_rule(metadata)
    if not rule["enabled"] or not rule["amount"] or not rule["frequency"] or not rule["next_run_at"]:
        raise HTTPException(status_code=400, detail="Contribution automatique non configuree")
    if require_due and not rule["is_due"]:
        raise HTTPException(status_code=400, detail="Aucune contribution automatique due pour cet objectif")

    applied_at = datetime.now(timezone.utc)
    await _credit_goal_from_wallet(
        db,
        goal=goal,
        wallet=wallet,
        current_user=current_user,
        amount=rule["amount"],
        source="auto_contribution",
        note=note or f"Contribution automatique {rule['frequency']}",
        metadata={
            "frequency": rule["frequency"],
            "scheduled_for": rule["next_run_at"].isoformat(),
        },
        description=f"Contribution automatique epargne {goal.title}",
    )

    current_rule = dict(metadata.get("auto_contribution_rule") or {})
    current_rule["last_applied_at"] = applied_at.isoformat()
    current_rule["next_run_at"] = _advance_auto_contribution(rule["next_run_at"], rule["frequency"]).isoformat()
    current_rule["updated_at"] = applied_at.isoformat()
    metadata["auto_contribution_rule"] = current_rule
    goal.metadata_ = metadata
    goal.updated_at = applied_at
    return _serialize_goal(goal)


async def run_savings_auto_contribution(db: AsyncSession, *, current_user: Users, goal_id: UUID, payload) -> dict:
    goal = await db.scalar(
        select(SavingsGoals)
        .where(SavingsGoals.goal_id == goal_id, SavingsGoals.user_id == current_user.user_id)
        .with_for_update()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Objectif introuvable")

    result = await _run_goal_auto_contribution(
        db,
        goal=goal,
        current_user=current_user,
        note=payload.note,
        require_due=False,
    )
    await db.commit()
    return await get_savings_goal_detail(db, current_user=current_user, goal_id=goal_id)


async def run_due_savings_auto_contributions(db: AsyncSession, *, current_user: Users) -> list[dict]:
    goals = (
        await db.execute(
            select(SavingsGoals)
            .where(SavingsGoals.user_id == current_user.user_id, SavingsGoals.status == "active")
            .order_by(SavingsGoals.created_at.desc())
            .with_for_update()
        )
    ).scalars().all()

    processed: list[dict] = []
    for goal in goals:
        rule = _normalize_auto_contribution_rule(goal.metadata_ or {})
        if not rule["is_due"]:
            continue
        try:
            await _run_goal_auto_contribution(
                db,
                goal=goal,
                current_user=current_user,
                note=None,
                require_due=True,
            )
            await db.commit()
            processed.append(await get_savings_goal_detail(db, current_user=current_user, goal_id=goal.goal_id))
        except HTTPException:
            await db.rollback()
    return processed


async def run_global_due_savings_auto_contributions(db: AsyncSession, *, limit: int = 100) -> dict:
    goals = (
        await db.execute(
            select(SavingsGoals)
            .where(SavingsGoals.status == "active")
            .order_by(SavingsGoals.updated_at.asc(), SavingsGoals.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    if not goals:
        return {"processed": 0, "succeeded": 0, "failed": 0}

    users = {
        item.user_id: item
        for item in (
            await db.execute(select(Users).where(Users.user_id.in_([goal.user_id for goal in goals])))
        ).scalars().all()
    }

    processed = 0
    succeeded = 0
    failed = 0
    for goal in goals:
        rule = _normalize_auto_contribution_rule(goal.metadata_ or {})
        if not rule["is_due"]:
            continue
        current_user = users.get(goal.user_id)
        if not current_user:
            failed += 1
            processed += 1
            continue
        try:
            await _run_goal_auto_contribution(
                db,
                goal=goal,
                current_user=current_user,
                note=None,
                require_due=True,
            )
            await db.commit()
            processed += 1
            succeeded += 1
        except HTTPException:
            await db.rollback()
            processed += 1
            failed += 1

    return {"processed": processed, "succeeded": succeeded, "failed": failed}
