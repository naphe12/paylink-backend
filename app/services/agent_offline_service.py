from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.agent_offline_operations import AgentOfflineOperations
from app.models.agent_transactions import AgentTransactions
from app.models.agents import Agents
from app.models.countries import Countries
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.agent_ops import compute_agent_commission
from app.services.aml import update_risk_score
from app.services.cash_credit_recovery import apply_cash_deposit_with_credit_recovery
from app.config import settings
from app.services.ledger import LedgerLine, LedgerService
from app.services.limits import guard_and_increment_limits
from app.services.wallet_history import log_wallet_movement

ALLOWED_TYPES = {"cash_in", "cash_out"}
SYNCABLE_STATUSES = {"draft", "queued", "failed"}
CONFLICT_REASON_MESSAGES = {
    "stale_operation": "Operation offline devenue ancienne",
    "wallet_changed": "Le wallet client a change depuis la mise en file",
    "balance_drift": "Le solde client a evolue depuis la capture offline",
    "insufficient_funds": "Le client n'a plus assez de solde au moment de la sync",
    "wallet_missing": "Wallet client introuvable au moment de la sync",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_json_safe(nested) for nested in value]
    return value


def _to_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _queued_age_minutes(item: AgentOfflineOperations) -> int:
    queued_at = item.queued_at or item.created_at or _now()
    delta = _now() - queued_at
    return max(int(delta.total_seconds() // 60), 0)


def _is_operation_stale(item: AgentOfflineOperations) -> bool:
    threshold = max(int(getattr(settings, "AGENT_OFFLINE_STALE_MINUTES", 180) or 180), 1)
    return _queued_age_minutes(item) >= threshold


def _snapshot_payload(wallet: Wallets | None) -> dict:
    return {
        "wallet_id": str(wallet.wallet_id) if wallet else None,
        "available": str(_to_decimal(wallet.available if wallet else 0)),
        "currency_code": str((wallet.currency_code if wallet else None) or "").upper() or None,
        "captured_at": _now().isoformat(),
    }


def _classify_failure(detail: str | None) -> str | None:
    normalized = str(detail or "").strip().lower()
    if not normalized:
        return None
    if "solde insuffisant" in normalized:
        return "insufficient_funds"
    if "wallet introuvable" in normalized:
        return "wallet_missing"
    if "operation offline devenue ancienne" in normalized:
        return "stale_operation"
    return None


def _conflict_reason_label(reason: str | None) -> str | None:
    return CONFLICT_REASON_MESSAGES.get(str(reason or "").strip().lower()) if reason else None


async def _load_client_wallet_snapshot(db: AsyncSession, *, client_user_id: UUID) -> Wallets | None:
    wallet = await db.scalar(
        select(Wallets)
        .where(Wallets.user_id == client_user_id, Wallets.type == "consumer")
        .order_by(Wallets.wallet_id.asc())
        .limit(1)
    )
    if wallet:
        return wallet
    return await db.scalar(select(Wallets).where(Wallets.user_id == client_user_id).order_by(Wallets.wallet_id.asc()).limit(1))


async def _compute_precheck(db: AsyncSession, *, item: AgentOfflineOperations) -> dict:
    wallet = await _load_client_wallet_snapshot(db, client_user_id=item.client_user_id)
    metadata = dict(item.metadata_ or {})
    snapshot = dict(metadata.get("wallet_snapshot") or {})
    snapshot_available = _to_decimal(snapshot.get("available"))
    current_available = _to_decimal(wallet.available if wallet else 0) if wallet else None
    balance_delta = current_available - snapshot_available if current_available is not None else None
    wallet_changed = bool(snapshot.get("wallet_id") and wallet and snapshot.get("wallet_id") != str(wallet.wallet_id))
    is_stale = _is_operation_stale(item)
    review_recommended = is_stale or wallet_changed or (balance_delta is not None and balance_delta != 0)
    conflict_reason = None
    if is_stale:
        conflict_reason = "stale_operation"
    elif wallet_changed:
        conflict_reason = "wallet_changed"
    elif balance_delta is not None and balance_delta != 0:
        conflict_reason = "balance_drift"
    return {
        "is_stale": is_stale,
        "queued_age_minutes": _queued_age_minutes(item),
        "snapshot_available": snapshot_available,
        "current_available": current_available,
        "balance_delta": balance_delta,
        "wallet_changed": wallet_changed,
        "review_recommended": review_recommended,
        "conflict_reason": conflict_reason,
        "conflict_reason_label": _conflict_reason_label(conflict_reason),
        "checked_at": _now().isoformat(),
        "current_wallet_id": str(wallet.wallet_id) if wallet else None,
        "current_currency_code": str((wallet.currency_code if wallet else None) or "").upper() or None,
    }


def _primary_wallet_stmt(user_id):
    wallet_priority = case(
        (Wallets.type == "consumer", 0),
        (Wallets.type == "personal", 1),
        else_=2,
    )
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(wallet_priority, Wallets.wallet_id.asc())
        .limit(1)
        .with_for_update()
    )


async def _require_agent_profile(db: AsyncSession, current_agent: Users) -> Agents:
    agent = await db.scalar(select(Agents).where(Agents.user_id == current_agent.user_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Profil agent introuvable")
    return agent


def _serialize_operation(item: AgentOfflineOperations) -> dict:
    metadata = dict(item.metadata_ or {})
    precheck = dict(metadata.get("last_precheck") or {})
    snapshot = dict(metadata.get("wallet_snapshot") or {})
    failure_code = precheck.get("failure_code") or _classify_failure(item.failure_reason)
    conflict_reason = precheck.get("conflict_reason") or failure_code
    conflict_reason_label = precheck.get("conflict_reason_label") or _conflict_reason_label(conflict_reason)
    snapshot_available = precheck.get("snapshot_available", snapshot.get("available"))
    current_available = precheck.get("current_available")
    balance_delta = precheck.get("balance_delta")
    requires_review = bool(precheck.get("review_recommended")) or bool(conflict_reason)
    return {
        "operation_id": item.operation_id,
        "agent_user_id": item.agent_user_id,
        "agent_id": item.agent_id,
        "client_user_id": item.client_user_id,
        "client_label": item.client_label,
        "operation_type": item.operation_type,
        "amount": Decimal(str(item.amount or 0)),
        "currency_code": item.currency_code,
        "note": item.note,
        "offline_reference": item.offline_reference,
        "status": item.status,
        "failure_reason": item.failure_reason,
        "conflict_reason": conflict_reason,
        "conflict_reason_label": conflict_reason_label,
        "requires_review": requires_review,
        "is_stale": bool(precheck.get("is_stale")) if precheck else _is_operation_stale(item),
        "queued_age_minutes": int(precheck.get("queued_age_minutes") or _queued_age_minutes(item)),
        "snapshot_available": _to_decimal(snapshot_available) if snapshot_available is not None else None,
        "current_available": _to_decimal(current_available) if current_available is not None else None,
        "balance_delta": _to_decimal(balance_delta) if balance_delta is not None else None,
        "synced_response": dict(item.synced_response or {}) if item.synced_response else None,
        "metadata": metadata,
        "queued_at": item.queued_at,
        "synced_at": item.synced_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


async def _serialize_operation_runtime(db: AsyncSession, item: AgentOfflineOperations) -> dict:
    payload = _serialize_operation(item)
    if item.status not in SYNCABLE_STATUSES and item.status not in {"failed", "syncing"}:
        return payload
    precheck = await _compute_precheck(db, item=item)
    conflict_reason = payload.get("conflict_reason") or precheck.get("conflict_reason")
    payload.update(
        {
            "conflict_reason": conflict_reason,
            "conflict_reason_label": payload.get("conflict_reason_label")
            or precheck.get("conflict_reason_label")
            or _conflict_reason_label(conflict_reason),
            "requires_review": bool(payload.get("requires_review"))
            or bool(precheck.get("review_recommended"))
            or bool(conflict_reason),
            "is_stale": bool(precheck.get("is_stale")),
            "queued_age_minutes": int(precheck.get("queued_age_minutes") or payload.get("queued_age_minutes") or 0),
            "snapshot_available": (
                _to_decimal(precheck.get("snapshot_available"))
                if precheck.get("snapshot_available") is not None
                else payload.get("snapshot_available")
            ),
            "current_available": (
                _to_decimal(precheck.get("current_available"))
                if precheck.get("current_available") is not None
                else payload.get("current_available")
            ),
            "balance_delta": (
                _to_decimal(precheck.get("balance_delta"))
                if precheck.get("balance_delta") is not None
                else payload.get("balance_delta")
            ),
        }
    )
    return payload


def _serialize_admin_operation(
    item: AgentOfflineOperations,
    *,
    agent_user: Users | None = None,
    client_user: Users | None = None,
) -> dict:
    payload = _serialize_operation(item)
    payload.update(
        {
            "agent_label": (
                (agent_user.full_name or agent_user.email or agent_user.phone_e164)
                if agent_user
                else str(item.agent_user_id)
            ),
            "agent_email": agent_user.email if agent_user else None,
            "agent_phone_e164": agent_user.phone_e164 if agent_user else None,
            "client_email": client_user.email if client_user else None,
            "client_phone_e164": client_user.phone_e164 if client_user else None,
            "client_paytag": client_user.paytag if client_user else None,
        }
    )
    return payload


async def _serialize_admin_operation_runtime(
    db: AsyncSession,
    item: AgentOfflineOperations,
    *,
    agent_user: Users | None = None,
    client_user: Users | None = None,
) -> dict:
    payload = await _serialize_operation_runtime(db, item)
    payload.update(
        {
            "agent_label": (
                (agent_user.full_name or agent_user.email or agent_user.phone_e164)
                if agent_user
                else str(item.agent_user_id)
            ),
            "agent_email": agent_user.email if agent_user else None,
            "agent_phone_e164": agent_user.phone_e164 if agent_user else None,
            "client_email": client_user.email if client_user else None,
            "client_phone_e164": client_user.phone_e164 if client_user else None,
            "client_paytag": client_user.paytag if client_user else None,
        }
    )
    return payload


async def list_agent_offline_operations(
    db: AsyncSession,
    *,
    current_agent: Users,
    status: str | None = None,
) -> list[dict]:
    await _require_agent_profile(db, current_agent)
    stmt = (
        select(AgentOfflineOperations)
        .where(AgentOfflineOperations.agent_user_id == current_agent.user_id)
        .order_by(AgentOfflineOperations.created_at.desc())
    )
    if status and status.strip():
        stmt = stmt.where(AgentOfflineOperations.status == status.strip().lower())
    rows = (await db.execute(stmt)).scalars().all()
    payloads = []
    for item in rows:
        payloads.append(await _serialize_operation_runtime(db, item))
    return payloads


async def list_admin_agent_offline_operations(
    db: AsyncSession,
    *,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    agent_user = aliased(Users)
    client_user = aliased(Users)
    stmt = (
        select(AgentOfflineOperations, agent_user, client_user)
        .join(agent_user, agent_user.user_id == AgentOfflineOperations.agent_user_id)
        .join(client_user, client_user.user_id == AgentOfflineOperations.client_user_id)
        .order_by(AgentOfflineOperations.created_at.desc())
        .limit(limit)
    )
    if status and status.strip():
        stmt = stmt.where(AgentOfflineOperations.status == status.strip().lower())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                AgentOfflineOperations.offline_reference.ilike(term),
                AgentOfflineOperations.client_label.ilike(term),
                AgentOfflineOperations.note.ilike(term),
                agent_user.full_name.ilike(term),
                agent_user.email.ilike(term),
                agent_user.phone_e164.ilike(term),
                client_user.full_name.ilike(term),
                client_user.email.ilike(term),
                client_user.phone_e164.ilike(term),
                client_user.paytag.ilike(term),
            )
        )
    rows = (await db.execute(stmt)).all()
    payloads = []
    for item, agent_row, client_row in rows:
        payloads.append(
            await _serialize_admin_operation_runtime(
                db,
                item,
                agent_user=agent_row,
                client_user=client_row,
            )
        )
    return payloads


async def get_admin_agent_offline_operation_detail(db: AsyncSession, *, operation_id: UUID) -> dict:
    agent_user = aliased(Users)
    client_user = aliased(Users)
    row = (
        await db.execute(
            select(AgentOfflineOperations, agent_user, client_user)
            .join(agent_user, agent_user.user_id == AgentOfflineOperations.agent_user_id)
            .join(client_user, client_user.user_id == AgentOfflineOperations.client_user_id)
            .where(AgentOfflineOperations.operation_id == operation_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Operation offline introuvable")
    item, agent_row, client_row = row
    return await _serialize_admin_operation_runtime(db, item, agent_user=agent_row, client_user=client_row)


async def create_agent_offline_operation(db: AsyncSession, *, current_agent: Users, payload) -> dict:
    agent_row = await _require_agent_profile(db, current_agent)
    operation_type = str(payload.operation_type or "").strip().lower()
    if operation_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Type d'operation offline invalide")

    client = await db.scalar(select(Users).where(Users.user_id == payload.client_user_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")
    if str(client.user_id) == str(current_agent.user_id):
        raise HTTPException(status_code=400, detail="Agent et client identiques")

    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == client.user_id).order_by(Wallets.wallet_id.asc()).limit(1))
    currency_code = str((wallet.currency_code if wallet else None) or "").upper()
    if not currency_code:
        country_currency = await db.scalar(select(Countries.currency_code).where(Countries.country_code == client.country_code))
        currency_code = str(country_currency or "EUR").upper()

    item = AgentOfflineOperations(
        agent_user_id=current_agent.user_id,
        agent_id=agent_row.agent_id,
        client_user_id=client.user_id,
        client_label=client.full_name or client.email or client.phone_e164 or str(client.user_id),
        operation_type=operation_type,
        amount=payload.amount,
        currency_code=currency_code,
        note=payload.note,
        offline_reference=f"off_{secrets.token_urlsafe(10)}",
        status="queued",
        metadata_={
            "client_phone": client.phone_e164,
            "client_email": client.email,
            "wallet_snapshot": _snapshot_payload(wallet),
            "created_from": "agent_offline_queue",
        },
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await _serialize_operation_runtime(db, item)


async def cancel_agent_offline_operation(db: AsyncSession, *, current_agent: Users, operation_id: UUID) -> dict:
    await _require_agent_profile(db, current_agent)
    item = await db.scalar(
        select(AgentOfflineOperations).where(
            AgentOfflineOperations.operation_id == operation_id,
            AgentOfflineOperations.agent_user_id == current_agent.user_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Operation offline introuvable")
    if item.status == "synced":
        raise HTTPException(status_code=400, detail="Operation deja synchronisee")
    item.status = "cancelled"
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return await _serialize_operation_runtime(db, item)


async def retry_admin_agent_offline_operation(db: AsyncSession, *, operation_id: UUID) -> dict:
    item = await db.scalar(select(AgentOfflineOperations).where(AgentOfflineOperations.operation_id == operation_id))
    if not item:
        raise HTTPException(status_code=404, detail="Operation offline introuvable")
    agent_user = await db.scalar(select(Users).where(Users.user_id == item.agent_user_id))
    if not agent_user:
        raise HTTPException(status_code=404, detail="Agent introuvable")
    try:
        await sync_agent_offline_operation(db, current_agent=agent_user, operation_id=operation_id)
    except HTTPException:
        return await get_admin_agent_offline_operation_detail(db, operation_id=operation_id)
    return await get_admin_agent_offline_operation_detail(db, operation_id=operation_id)


async def cancel_admin_agent_offline_operation(db: AsyncSession, *, operation_id: UUID) -> dict:
    item = await db.scalar(select(AgentOfflineOperations).where(AgentOfflineOperations.operation_id == operation_id))
    if not item:
        raise HTTPException(status_code=404, detail="Operation offline introuvable")
    agent_user = await db.scalar(select(Users).where(Users.user_id == item.agent_user_id))
    if not agent_user:
        raise HTTPException(status_code=404, detail="Agent introuvable")
    await cancel_agent_offline_operation(db, current_agent=agent_user, operation_id=operation_id)
    return await get_admin_agent_offline_operation_detail(db, operation_id=operation_id)


async def _execute_cash_in(
    db: AsyncSession,
    *,
    current_agent: Users,
    agent_row: Agents,
    client: Users,
    item: AgentOfflineOperations,
) -> dict:
    amount = Decimal(str(item.amount))
    await guard_and_increment_limits(db, client, float(amount))
    commission = compute_agent_commission(float(amount), agent_row.commission_rate)
    score = await update_risk_score(db, client, float(amount), channel="agent")

    user_country_currency = await db.scalar(select(Countries.currency_code).where(Countries.country_code == client.country_code))
    wallet = await db.scalar(
        select(Wallets).where(Wallets.user_id == client.user_id, Wallets.type == "consumer").with_for_update()
    )
    if not wallet:
        wallet = await db.scalar(select(Wallets).where(Wallets.user_id == client.user_id).with_for_update())
    if not wallet:
        wallet = Wallets(
            user_id=client.user_id,
            type="consumer",
            currency_code=(user_country_currency or item.currency_code or "EUR"),
            available=Decimal("0"),
            pending=Decimal("0"),
        )
        db.add(wallet)
        await db.flush()

    recovery = await apply_cash_deposit_with_credit_recovery(
        db,
        user=client,
        wallet=wallet,
        amount=amount,
        credit_event_source="agent_cashin_offline_sync",
        credit_history_description="Depot cash agent offline",
    )
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=client.user_id,
        amount=amount,
        direction="credit",
        operation_type="cash_deposit_agent_offline_sync",
        reference=str(item.operation_id),
        description=f"Depot cash agent offline ({current_agent.full_name or current_agent.email or current_agent.user_id})",
    )
    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_in = await ledger.get_cash_in_account(wallet.currency_code)
    await ledger.post_journal(
        tx_id=None,
        description="Depot cash agent offline sync",
        metadata={
            "operation": "cash_deposit_agent_offline_sync",
            "offline_operation_id": str(item.operation_id),
            "target_user_id": str(client.user_id),
            "wallet_id": str(wallet.wallet_id),
            "processed_by": str(current_agent.user_id),
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(account=cash_in, direction="debit", amount=amount, currency_code=wallet.currency_code),
            LedgerLine(account=wallet_account, direction="credit", amount=amount, currency_code=wallet.currency_code),
        ],
    )
    await db.execute(
        insert(AgentTransactions).values(
            agent_id=agent_row.agent_id,
            client_user_id=client.user_id,
            direction="cashin",
            tx_type="cashin_offline_sync",
            amount=amount,
            commission=commission,
            status="completed",
        )
    )
    return {
        "message": "Cash-in synchronise",
        "commission": str(commission),
        "risk_score": score,
        "amount": float(amount),
        "currency": wallet.currency_code,
        "new_balance": float(wallet.available),
        "credit_recovered": float(recovery["credit_recovered"]),
    }


async def _execute_cash_out(
    db: AsyncSession,
    *,
    current_agent: Users,
    agent_row: Agents,
    client: Users,
    item: AgentOfflineOperations,
) -> dict:
    amount = Decimal(str(item.amount))
    await guard_and_increment_limits(db, client, float(amount))
    commission = compute_agent_commission(float(amount), agent_row.commission_rate)
    score = await update_risk_score(db, client, float(amount), channel="agent")

    wallet = await db.scalar(
        select(Wallets).where(Wallets.user_id == client.user_id, Wallets.type == "consumer").with_for_update()
    )
    if not wallet:
        wallet = await db.scalar(select(Wallets).where(Wallets.user_id == client.user_id).with_for_update())
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable")
    if Decimal(str(wallet.available or 0)) < amount:
        raise HTTPException(status_code=400, detail="Solde insuffisant pour effectuer ce retrait")

    wallet.available = Decimal(str(wallet.available or 0)) - amount
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=client.user_id,
        amount=amount,
        direction="debit",
        operation_type="cash_withdraw_agent_offline_sync",
        reference=str(item.operation_id),
        description=f"Retrait cash agent offline ({current_agent.full_name or current_agent.email or current_agent.user_id})",
    )
    ledger = LedgerService(db)
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_out = await ledger.get_cash_out_account(wallet.currency_code)
    await ledger.post_journal(
        tx_id=None,
        description="Retrait cash agent offline sync",
        metadata={
            "operation": "cash_withdraw_agent_offline_sync",
            "offline_operation_id": str(item.operation_id),
            "target_user_id": str(client.user_id),
            "wallet_id": str(wallet.wallet_id),
            "processed_by": str(current_agent.user_id),
            "movement_id": str(movement.transaction_id) if movement else None,
        },
        entries=[
            LedgerLine(account=wallet_account, direction="debit", amount=amount, currency_code=wallet.currency_code),
            LedgerLine(account=cash_out, direction="credit", amount=amount, currency_code=wallet.currency_code),
        ],
    )
    await db.execute(
        insert(AgentTransactions).values(
            agent_id=agent_row.agent_id,
            client_user_id=client.user_id,
            direction="cashout",
            tx_type="cashout_offline_sync",
            amount=amount,
            commission=commission,
            status="completed",
        )
    )
    return {
        "message": "Cash-out synchronise",
        "commission": str(commission),
        "risk_score": score,
        "amount": float(amount),
        "currency": wallet.currency_code,
        "new_balance": float(wallet.available),
    }


async def sync_agent_offline_operation(db: AsyncSession, *, current_agent: Users, operation_id: UUID) -> dict:
    agent_row = await _require_agent_profile(db, current_agent)
    item = await db.scalar(
        select(AgentOfflineOperations)
        .where(
            AgentOfflineOperations.operation_id == operation_id,
            AgentOfflineOperations.agent_user_id == current_agent.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Operation offline introuvable")
    if item.status not in SYNCABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Cette operation ne peut pas etre synchronisee")

    item.status = "syncing"
    item.failure_reason = None
    item.updated_at = _now()
    await db.commit()

    try:
        item = await db.scalar(
            select(AgentOfflineOperations)
            .where(
                AgentOfflineOperations.operation_id == operation_id,
                AgentOfflineOperations.agent_user_id == current_agent.user_id,
            )
            .with_for_update()
        )
        client = await db.scalar(select(Users).where(Users.user_id == item.client_user_id))
        if not client:
            raise HTTPException(status_code=404, detail="Client introuvable")
        precheck = await _compute_precheck(db, item=item)
        metadata = dict(item.metadata_ or {})
        metadata["last_precheck"] = _json_safe(precheck)
        item.metadata_ = metadata

        if item.operation_type == "cash_in":
            response = await _execute_cash_in(db, current_agent=current_agent, agent_row=agent_row, client=client, item=item)
        else:
            response = await _execute_cash_out(db, current_agent=current_agent, agent_row=agent_row, client=client, item=item)

        item.status = "synced"
        item.synced_response = {
            **response,
            "review_recommended": bool(precheck.get("review_recommended")),
            "conflict_reason": precheck.get("conflict_reason"),
        }
        item.synced_at = _now()
        item.updated_at = _now()
        await db.commit()
        await db.refresh(item)
        return _serialize_operation(item)
    except Exception as exc:
        await db.rollback()
        failed_item = await db.scalar(
            select(AgentOfflineOperations)
            .where(
                AgentOfflineOperations.operation_id == operation_id,
                AgentOfflineOperations.agent_user_id == current_agent.user_id,
            )
            .with_for_update()
        )
        if failed_item:
            metadata = dict(failed_item.metadata_ or {})
            precheck = dict(metadata.get("last_precheck") or {})
            failure_code = _classify_failure(getattr(exc, "detail", None) or str(exc))
            if failure_code and not precheck.get("conflict_reason"):
                precheck["conflict_reason"] = failure_code
                precheck["conflict_reason_label"] = _conflict_reason_label(failure_code)
            if failure_code:
                precheck["failure_code"] = failure_code
            if not precheck:
                precheck = await _compute_precheck(db, item=failed_item)
            metadata["last_precheck"] = _json_safe(precheck)
            failed_item.metadata_ = metadata
            failed_item.status = "failed"
            failed_item.failure_reason = str(getattr(exc, "detail", None) or str(exc))
            failed_item.updated_at = _now()
            await db.commit()
            await db.refresh(failed_item)
            if isinstance(exc, HTTPException):
                raise exc
            return await _serialize_operation_runtime(db, failed_item)
        raise


async def sync_pending_agent_offline_operations(db: AsyncSession, *, current_agent: Users) -> dict:
    await _require_agent_profile(db, current_agent)
    items = (
        await db.execute(
            select(AgentOfflineOperations.operation_id)
            .where(
                AgentOfflineOperations.agent_user_id == current_agent.user_id,
                AgentOfflineOperations.status.in_(tuple(SYNCABLE_STATUSES)),
            )
            .order_by(AgentOfflineOperations.created_at.asc())
        )
    ).scalars().all()
    synced = 0
    failed = 0
    operations = []
    for operation_id in items:
        result = await sync_agent_offline_operation(db, current_agent=current_agent, operation_id=operation_id)
        operations.append(result)
        if result["status"] == "synced":
            synced += 1
        else:
            failed += 1
    return {"synced": synced, "failed": failed, "operations": operations}
