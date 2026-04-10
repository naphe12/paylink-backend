from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bonus_history import BonusHistory
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.transaction_notifications import send_transaction_emails
from app.utils.notify import send_notification

BONUS_CURRENCY_CODE = "BIF"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _display_user(user: Users | None) -> str | None:
    if not user:
        return None
    return user.paytag or user.username or user.email or user.full_name


def _normalized_role(user: Users | None) -> str:
    return str(getattr(user, "role", "") or "").strip().lower()


def _wallet_priority_case():
    return case(
        (Wallets.type == "personal", 0),
        (Wallets.type == "consumer", 1),
        else_=2,
    )


async def _get_primary_wallet(db: AsyncSession, user_id: UUID) -> Wallets | None:
    return await db.scalar(
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(_wallet_priority_case(), Wallets.wallet_id.asc())
        .limit(1)
    )


def _normalize_identifier(identifier: str) -> tuple[str, str]:
    ident = " ".join(str(identifier or "").strip().split())
    normalized = ident.lower()
    paytag = normalized if normalized.startswith("@") else f"@{normalized}"
    return normalized, paytag


async def find_user_by_identifier(db: AsyncSession, identifier: str) -> Users | None:
    normalized, paytag = _normalize_identifier(identifier)
    raw = str(identifier or "").strip()
    if not normalized:
        return None
    return await db.scalar(
        select(Users).where(
            or_(
                func.lower(Users.email) == normalized,
                func.lower(Users.username) == normalized,
                func.lower(Users.paytag) == paytag,
                Users.phone_e164 == raw,
            )
        )
    )


def _validate_bonus_amount(amount_bif: Decimal) -> Decimal:
    amount = Decimal(str(amount_bif or 0)).quantize(Decimal("0.01"))
    if amount <= Decimal("0"):
        raise HTTPException(status_code=400, detail="Montant bonus invalide.")
    return amount


async def _execute_bonus_transfer(
    db: AsyncSession,
    *,
    sender_user: Users,
    recipient_user: Users,
    amount_bif: Decimal,
    actor_user: Users | None = None,
) -> dict:
    if sender_user.user_id == recipient_user.user_id:
        raise HTTPException(status_code=400, detail="Impossible de s'envoyer un bonus a soi-meme.")
    if _normalized_role(sender_user) not in {"client", "user"}:
        raise HTTPException(status_code=400, detail="Emetteur bonus invalide.")
    if _normalized_role(recipient_user) not in {"client", "user"}:
        raise HTTPException(status_code=400, detail="Destinataire bonus invalide.")

    amount = _validate_bonus_amount(amount_bif)
    sender_wallet = await _get_primary_wallet(db, sender_user.user_id)
    recipient_wallet = await _get_primary_wallet(db, recipient_user.user_id)
    if not sender_wallet:
        raise HTTPException(status_code=404, detail="Wallet bonus emetteur introuvable.")
    if not recipient_wallet:
        raise HTTPException(status_code=404, detail="Wallet bonus destinataire introuvable.")

    sender_bonus_before = Decimal(sender_wallet.bonus_balance or 0)
    if sender_bonus_before < amount:
        raise HTTPException(status_code=400, detail="Solde bonus insuffisant.")

    sender_wallet.bonus_balance = sender_bonus_before - amount
    recipient_wallet.bonus_balance = Decimal(recipient_wallet.bonus_balance or 0) + amount

    transfer_id = uuid4()
    created_at = _utcnow()
    db.add(
        BonusHistory(
            user_id=sender_user.user_id,
            amount_bif=amount,
            source="sent",
            reference_id=transfer_id,
            created_at=created_at,
        )
    )
    db.add(
        BonusHistory(
            user_id=recipient_user.user_id,
            amount_bif=amount,
            source="received",
            reference_id=transfer_id,
            created_at=created_at,
        )
    )
    await db.commit()
    await db.refresh(sender_wallet)
    await db.refresh(recipient_wallet)

    sender_label = _display_user(sender_user) or "utilisateur"
    recipient_label = _display_user(recipient_user) or "utilisateur"
    actor_label = _display_user(actor_user) if actor_user else None

    sender_message = (
        f"Bonus envoye: {amount} {BONUS_CURRENCY_CODE} vers {recipient_label}."
        if not actor_label or actor_user.user_id == sender_user.user_id
        else f"Un agent a envoye {amount} {BONUS_CURRENCY_CODE} de votre bonus vers {recipient_label}."
    )
    recipient_message = (
        f"Vous avez recu {amount} {BONUS_CURRENCY_CODE} de bonus depuis {sender_label}."
        if not actor_label or actor_user.user_id == sender_user.user_id
        else f"Vous avez recu {amount} {BONUS_CURRENCY_CODE} de bonus depuis {sender_label} via un agent."
    )

    await send_notification(str(sender_user.user_id), sender_message)
    await send_notification(str(recipient_user.user_id), recipient_message)

    email_lines = [
        f"Transfert bonus effectue.",
        f"Montant: {amount} {BONUS_CURRENCY_CODE}",
        f"Emetteur: {sender_label}",
        f"Destinataire: {recipient_label}",
    ]
    if actor_label and actor_user and actor_user.user_id != sender_user.user_id:
        email_lines.append(f"Operation realisee par: {actor_label}")
    await send_transaction_emails(
        db,
        initiator=sender_user,
        receiver=recipient_user,
        subject=f"Transfert bonus {amount} {BONUS_CURRENCY_CODE}",
        body="<br>".join(email_lines),
    )

    return {
        "transfer_id": transfer_id,
        "amount_bif": amount,
        "currency_code": BONUS_CURRENCY_CODE,
        "sender_user_id": sender_user.user_id,
        "recipient_user_id": recipient_user.user_id,
        "sender_label": sender_label,
        "recipient_label": recipient_label,
        "sender_bonus_balance": Decimal(sender_wallet.bonus_balance or 0),
        "recipient_bonus_balance": Decimal(recipient_wallet.bonus_balance or 0),
        "initiated_by_agent_user_id": actor_user.user_id if actor_user and actor_user.user_id != sender_user.user_id else None,
        "created_at": created_at,
    }


async def send_bonus_by_identifier(
    db: AsyncSession,
    *,
    sender_user: Users,
    recipient_identifier: str,
    amount_bif: Decimal,
) -> dict:
    recipient_user = await find_user_by_identifier(db, recipient_identifier)
    if not recipient_user:
        raise HTTPException(status_code=404, detail="Destinataire bonus introuvable.")
    return await _execute_bonus_transfer(
        db,
        sender_user=sender_user,
        recipient_user=recipient_user,
        amount_bif=amount_bif,
        actor_user=sender_user,
    )


async def send_bonus_by_user_ids(
    db: AsyncSession,
    *,
    sender_user_id: UUID,
    recipient_user_id: UUID,
    amount_bif: Decimal,
    actor_user: Users,
) -> dict:
    sender_user = await db.scalar(select(Users).where(Users.user_id == sender_user_id))
    if not sender_user:
        raise HTTPException(status_code=404, detail="Client emetteur introuvable.")
    recipient_user = await db.scalar(select(Users).where(Users.user_id == recipient_user_id))
    if not recipient_user:
        raise HTTPException(status_code=404, detail="Destinataire bonus introuvable.")
    return await _execute_bonus_transfer(
        db,
        sender_user=sender_user,
        recipient_user=recipient_user,
        amount_bif=amount_bif,
        actor_user=actor_user,
    )


async def get_bonus_balance_payload(db: AsyncSession, *, user: Users) -> dict:
    wallet = await _get_primary_wallet(db, user.user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet bonus introuvable.")
    return {
        "bonus_balance": Decimal(wallet.bonus_balance or 0),
        "currency_code": BONUS_CURRENCY_CODE,
    }


async def get_agent_bonus_user_summary(db: AsyncSession, *, user_id: UUID) -> dict:
    user = await db.scalar(select(Users).where(Users.user_id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Client introuvable.")
    if _normalized_role(user) not in {"client", "user"}:
        raise HTTPException(status_code=400, detail="Utilisateur bonus invalide.")
    wallet = await _get_primary_wallet(db, user.user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet bonus introuvable.")
    return {
        "user_id": user.user_id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_e164": user.phone_e164,
        "bonus_balance": Decimal(wallet.bonus_balance or 0),
        "currency_code": BONUS_CURRENCY_CODE,
    }


async def list_bonus_history_payload(db: AsyncSession, *, user: Users) -> list[dict]:
    rows = (
        await db.execute(
            select(BonusHistory)
            .where(BonusHistory.user_id == user.user_id)
            .order_by(BonusHistory.created_at.desc())
        )
    ).scalars().all()

    reference_ids = [row.reference_id for row in rows if row.reference_id]
    counterpart_map: dict[UUID, Users] = {}
    if reference_ids:
        related_rows = (
            await db.execute(
                select(BonusHistory)
                .where(
                    BonusHistory.reference_id.in_(reference_ids),
                    BonusHistory.user_id != user.user_id,
                )
            )
        ).scalars().all()
        user_ids = {row.user_id for row in related_rows if row.user_id}
        if user_ids:
            users = (
                await db.execute(select(Users).where(Users.user_id.in_(user_ids)))
            ).scalars().all()
            users_map = {item.user_id: item for item in users}
            for row in related_rows:
                counterpart = users_map.get(row.user_id)
                if counterpart and row.reference_id:
                    counterpart_map[row.reference_id] = counterpart

    items = []
    for row in rows:
        label = {
            "sent": "Bonus envoye",
            "received": "Bonus recu",
            "earned": "Bonus gagne",
            "used": "Bonus utilise",
        }.get(str(row.source or "").lower(), str(row.source or "").strip() or "Bonus")
        counterpart = counterpart_map.get(row.reference_id) if row.reference_id else None
        items.append(
            {
                "id": row.id,
                "user_id": row.user_id,
                "amount_bif": Decimal(row.amount_bif or 0),
                "currency_code": BONUS_CURRENCY_CODE,
                "source": row.source,
                "label": label,
                "reference_id": row.reference_id,
                "counterparty_label": _display_user(counterpart),
                "created_at": row.created_at,
            }
        )
    return items
