from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_transfers import ScheduledTransfers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets
from app.schemas.external_transfers import ExternalTransferCreate
from app.services.ledger import LedgerLine, LedgerService
from app.services.wallet_history import log_wallet_movement


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _advance_next_run(next_run_at: datetime, frequency: str) -> datetime:
    if frequency == "daily":
        return next_run_at + timedelta(days=1)
    if frequency == "weekly":
        return next_run_at + timedelta(days=7)
    if frequency == "monthly":
        return next_run_at + timedelta(days=30)
    raise ValueError("Unsupported frequency")


def _schedule_is_due(item: ScheduledTransfers) -> bool:
    next_run_at = item.next_run_at
    if next_run_at and next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=timezone.utc)
    return bool(next_run_at and next_run_at <= _utcnow() and item.status in {"active", "failed"})


def _schedule_metadata(item: ScheduledTransfers) -> dict:
    metadata = getattr(item, "metadata_", {}) or {}
    return dict(metadata)


def _schedule_transfer_type(item: ScheduledTransfers) -> str:
    transfer_type = str(_schedule_metadata(item).get("transfer_type") or "internal").strip().lower()
    return "external" if transfer_type == "external" else "internal"


def _schedule_external_payload(item: ScheduledTransfers) -> dict | None:
    payload = _schedule_metadata(item).get("external_transfer")
    return dict(payload) if isinstance(payload, dict) else None


def _serialize_schedule(item: ScheduledTransfers) -> dict:
    metadata = _schedule_metadata(item)
    transfer_type = _schedule_transfer_type(item)
    external_transfer = _schedule_external_payload(item)
    receiver_identifier = str(getattr(item, "receiver_identifier", "") or "").strip()
    if transfer_type == "external" and not receiver_identifier:
        receiver_identifier = (
            str((external_transfer or {}).get("recipient_phone") or "").strip()
            or str((external_transfer or {}).get("recipient_name") or "").strip()
            or "-"
        )
    return {
        "schedule_id": item.schedule_id,
        "user_id": item.user_id,
        "receiver_user_id": item.receiver_user_id,
        "receiver_identifier": receiver_identifier,
        "transfer_type": transfer_type,
        "external_transfer": external_transfer,
        "amount": Decimal(str(item.amount)),
        "currency_code": item.currency_code,
        "frequency": item.frequency,
        "status": item.status,
        "note": item.note,
        "next_run_at": item.next_run_at,
        "last_run_at": item.last_run_at,
        "last_result": item.last_result,
        "remaining_runs": item.remaining_runs,
        "metadata": metadata,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "is_due": _schedule_is_due(item),
    }


async def _resolve_receiver(db: AsyncSession, identifier: str) -> Users:
    normalized = str(identifier or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Destinataire manquant")
    receiver = await db.scalar(
        select(Users).where(or_(Users.email == normalized, Users.paytag == normalized))
    )
    if not receiver:
        raise HTTPException(status_code=404, detail="Destinataire introuvable")
    return receiver


async def _execute_internal_transfer(
    db: AsyncSession,
    *,
    sender: Users,
    receiver_identifier: str,
    amount: Decimal,
    note: str | None = None,
    schedule_id: UUID | None = None,
) -> dict:
    receiver = await _resolve_receiver(db, receiver_identifier)
    if receiver.user_id == sender.user_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous envoyer a vous-meme")

    sender_wallet = await db.scalar(_primary_wallet_stmt(sender.user_id))
    receiver_wallet = await db.scalar(_primary_wallet_stmt(receiver.user_id))
    if not sender_wallet or not receiver_wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")
    if str(sender_wallet.currency_code or "").upper() != str(receiver_wallet.currency_code or "").upper():
        raise HTTPException(status_code=400, detail="Transfert interne impossible entre devises differentes.")
    if Decimal(str(sender_wallet.available or 0)) < amount:
        raise HTTPException(status_code=400, detail="Solde insuffisant")

    sender_wallet.available = Decimal(str(sender_wallet.available or 0)) - amount
    receiver_wallet.available = Decimal(str(receiver_wallet.available or 0)) + amount

    sender_movement = await log_wallet_movement(
        db,
        wallet=sender_wallet,
        user_id=sender.user_id,
        amount=amount,
        direction="debit",
        operation_type="scheduled_transfer_send" if schedule_id else "transfer_send",
        reference=receiver.email or receiver.paytag,
        description=note or f"Transfert programme vers {receiver.email or receiver.paytag}",
    )
    receiver_movement = await log_wallet_movement(
        db,
        wallet=receiver_wallet,
        user_id=receiver.user_id,
        amount=amount,
        direction="credit",
        operation_type="scheduled_transfer_receive" if schedule_id else "transfer_receive",
        reference=sender.email or sender.paytag,
        description=note or f"Transfert programme de {sender.email or sender.paytag}",
    )

    tx = Transactions(
        initiated_by=sender.user_id,
        sender_wallet=sender_wallet.wallet_id,
        receiver_wallet=receiver_wallet.wallet_id,
        amount=amount,
        currency_code=sender_wallet.currency_code,
        channel="internal",
        status="succeeded",
        description=note or f"Transfert programme vers {receiver.email or receiver.paytag}",
    )
    db.add(tx)
    await db.flush()

    ledger = LedgerService(db)
    sender_account = await ledger.ensure_wallet_account(sender_wallet)
    receiver_account = await ledger.ensure_wallet_account(receiver_wallet)
    metadata = {
        "operation": "scheduled_internal_transfer" if schedule_id else "internal_transfer",
        "sender_wallet_id": str(sender_wallet.wallet_id),
        "receiver_wallet_id": str(receiver_wallet.wallet_id),
        "sender_user_id": str(sender.user_id),
        "receiver_user_id": str(receiver.user_id),
        "transaction_id": str(tx.tx_id),
        "receiver_identifier": receiver_identifier,
    }
    if schedule_id:
        metadata["schedule_id"] = str(schedule_id)
    if sender_movement:
        metadata["sender_movement_id"] = str(sender_movement.transaction_id)
    if receiver_movement:
        metadata["receiver_movement_id"] = str(receiver_movement.transaction_id)
    await ledger.post_journal(
        tx_id=tx.tx_id,
        description=note or f"Transfert programme vers {receiver.email or receiver.paytag}",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=amount,
                currency_code=sender_wallet.currency_code,
            ),
            LedgerLine(
                account=receiver_account,
                direction="credit",
                amount=amount,
                currency_code=receiver_wallet.currency_code,
            ),
        ],
    )
    return {
        "receiver_user_id": receiver.user_id,
        "currency_code": str(sender_wallet.currency_code or "").upper(),
        "tx_id": tx.tx_id,
    }


async def _execute_external_transfer(
    db: AsyncSession,
    *,
    sender: Users,
    item: ScheduledTransfers,
) -> dict:
    from app.routers.wallet.transfer import _external_transfer_core

    payload_data = _schedule_external_payload(item)
    if not payload_data:
        raise HTTPException(status_code=400, detail="Configuration du transfert externe manquante")

    try:
        payload = ExternalTransferCreate(
            partner_name=payload_data.get("partner_name"),
            country_destination=payload_data.get("country_destination"),
            recipient_name=payload_data.get("recipient_name"),
            recipient_phone=payload_data.get("recipient_phone"),
            recipient_email=payload_data.get("recipient_email"),
            amount=Decimal(str(item.amount)),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Configuration du transfert externe invalide") from exc

    background_tasks = BackgroundTasks()
    return await _external_transfer_core(
        data=payload,
        background_tasks=background_tasks,
        idempotency_key=None,
        db=db,
        current_user=sender,
    )


async def _run_scheduled_transfer_item(
    db: AsyncSession,
    *,
    current_user: Users,
    item: ScheduledTransfers,
    raise_on_failure: bool,
) -> dict:
    try:
        transfer_type = _schedule_transfer_type(item)
        if transfer_type == "external":
            result = await _execute_external_transfer(
                db,
                sender=current_user,
                item=item,
            )
        else:
            result = await _execute_internal_transfer(
                db,
                sender=current_user,
                receiver_identifier=item.receiver_identifier,
                amount=Decimal(str(item.amount)),
                note=item.note,
                schedule_id=item.schedule_id,
            )
        now = _utcnow()
        item.status = "active"
        item.last_run_at = now
        item.updated_at = now
        if transfer_type == "external":
            reference_code = str(result.get("reference_code") or result.get("transfer_id") or "").strip()
            item.last_result = (
                f"Transfert externe planifie: {result.get('status', 'created')}"
                f"{f' ({reference_code})' if reference_code else ''}"
            )
            item.receiver_user_id = None
            item.currency_code = str(result.get("currency") or item.currency_code or "").upper() or item.currency_code
        else:
            item.last_result = "Execution reussie"
            item.receiver_user_id = result["receiver_user_id"]
            item.currency_code = result["currency_code"]
        if item.remaining_runs is not None:
            item.remaining_runs = max(int(item.remaining_runs) - 1, 0)
            if item.remaining_runs == 0:
                item.status = "completed"
                item.next_run_at = now
            else:
                item.next_run_at = _advance_next_run(item.next_run_at, item.frequency)
        else:
            item.next_run_at = _advance_next_run(item.next_run_at, item.frequency)
        await db.commit()
        await db.refresh(item)
        return _serialize_schedule(item)
    except HTTPException as exc:
        item.status = "failed"
        item.updated_at = _utcnow()
        item.last_result = str(exc.detail)
        await db.commit()
        await db.refresh(item)
        if raise_on_failure:
            raise
        return _serialize_schedule(item)


async def create_scheduled_transfer(
    db: AsyncSession,
    *,
    current_user: Users,
    payload,
):
    next_run_at = payload.next_run_at
    if next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=timezone.utc)
    if next_run_at < _utcnow():
        raise HTTPException(status_code=400, detail="La prochaine execution doit etre dans le futur")

    sender_wallet = await db.scalar(_primary_wallet_stmt(current_user.user_id))
    if not sender_wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    receiver_user_id = None
    receiver_identifier = ""
    metadata: dict = {"transfer_type": payload.transfer_type}
    if payload.transfer_type == "external":
        external_transfer = payload.external_transfer.model_dump(mode="json", exclude_none=True)
        receiver_identifier = (
            str(payload.external_transfer.recipient_phone or "").strip()
            or str(payload.external_transfer.recipient_name or "").strip()
        )
        metadata["external_transfer"] = external_transfer
    else:
        receiver = await _resolve_receiver(db, payload.receiver_identifier)
        receiver_wallet = await db.scalar(_primary_wallet_stmt(receiver.user_id))
        if not receiver_wallet:
            raise HTTPException(status_code=404, detail="Portefeuille introuvable")
        if str(sender_wallet.currency_code or "").upper() != str(receiver_wallet.currency_code or "").upper():
            raise HTTPException(status_code=400, detail="Transfert programme impossible entre devises differentes.")
        receiver_user_id = receiver.user_id
        receiver_identifier = payload.receiver_identifier

    item = ScheduledTransfers(
        user_id=current_user.user_id,
        receiver_user_id=receiver_user_id,
        receiver_identifier=receiver_identifier,
        amount=payload.amount,
        currency_code=str(sender_wallet.currency_code or "").upper(),
        frequency=payload.frequency,
        status="active",
        note=payload.note,
        next_run_at=next_run_at,
        remaining_runs=payload.remaining_runs,
        metadata_=metadata,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def list_scheduled_transfers(db: AsyncSession, *, current_user: Users):
    rows = (
        await db.execute(
            select(ScheduledTransfers)
            .where(ScheduledTransfers.user_id == current_user.user_id)
            .order_by(ScheduledTransfers.created_at.desc())
        )
    ).scalars().all()
    return [_serialize_schedule(item) for item in rows]


async def pause_scheduled_transfer(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status in {"cancelled", "completed"}:
        raise HTTPException(status_code=400, detail="Ce transfert programme ne peut pas etre mis en pause")
    item.status = "paused"
    item.updated_at = _utcnow()
    item.last_result = "Mis en pause par l'utilisateur"
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def resume_scheduled_transfer(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status != "paused":
        raise HTTPException(status_code=400, detail="Ce transfert programme n'est pas en pause")
    now = _utcnow()
    item.status = "active"
    item.updated_at = now
    item.last_result = "Repris par l'utilisateur"
    if item.next_run_at and item.next_run_at < now:
        item.next_run_at = now
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def cancel_scheduled_transfer(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    item.status = "cancelled"
    item.updated_at = _utcnow()
    item.last_result = "Annule par l'utilisateur"
    await db.commit()
    await db.refresh(item)
    return _serialize_schedule(item)


async def run_due_scheduled_transfers(db: AsyncSession, *, current_user: Users):
    rows = (
        await db.execute(
            select(ScheduledTransfers)
            .where(
                ScheduledTransfers.user_id == current_user.user_id,
                ScheduledTransfers.status.in_(("active", "failed")),
                ScheduledTransfers.next_run_at <= _utcnow(),
            )
            .order_by(ScheduledTransfers.next_run_at.asc())
            .with_for_update()
        )
    ).scalars().all()
    processed = []
    for item in rows:
        processed.append(
            await _run_scheduled_transfer_item(
                db,
                current_user=current_user,
                item=item,
                raise_on_failure=False,
            )
        )
    return processed


async def run_scheduled_transfer_now(db: AsyncSession, *, current_user: Users, schedule_id: UUID):
    item = await db.scalar(
        select(ScheduledTransfers)
        .where(
            ScheduledTransfers.schedule_id == schedule_id,
            ScheduledTransfers.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Transfert programme introuvable")
    if item.status not in {"active", "failed"}:
        raise HTTPException(status_code=400, detail="Ce transfert programme ne peut pas etre execute")
    return await _run_scheduled_transfer_item(
        db,
        current_user=current_user,
        item=item,
        raise_on_failure=True,
    )


async def run_global_due_scheduled_transfers(db: AsyncSession, *, limit: int = 100) -> dict:
    rows = (
        await db.execute(
            select(ScheduledTransfers)
            .where(
                ScheduledTransfers.status.in_(("active", "failed")),
                ScheduledTransfers.next_run_at <= _utcnow(),
            )
            .order_by(ScheduledTransfers.next_run_at.asc(), ScheduledTransfers.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    if not rows:
        return {"processed": 0, "succeeded": 0, "failed": 0}

    users = {
        item.user_id: item
        for item in (
            await db.execute(select(Users).where(Users.user_id.in_([row.user_id for row in rows])))
        ).scalars().all()
    }

    processed = 0
    succeeded = 0
    failed = 0
    for item in rows:
        current_user = users.get(item.user_id)
        if not current_user:
            item.status = "failed"
            item.updated_at = _utcnow()
            item.last_result = "Utilisateur emetteur introuvable"
            await db.commit()
            processed += 1
            failed += 1
            continue
        result = await _run_scheduled_transfer_item(
            db,
            current_user=current_user,
            item=item,
            raise_on_failure=False,
        )
        processed += 1
        if result["status"] in {"active", "completed"}:
            succeeded += 1
        else:
            failed += 1

    return {"processed": processed, "succeeded": succeeded, "failed": failed}
