from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal

from sqlalchemy import text

from app.core.database import async_session_maker
from app.services.notifiers import EmailNotifier, NotificationMessage
from app.services.paylink_ledger_service import PaylinkLedgerService

logger = logging.getLogger(__name__)


class NoAvailablePayoutAgent(RuntimeError):
    pass


async def _persist_assignment_notification(
    *,
    user_id: str | None,
    order_id: str,
    assignment_id: str,
    agent_id: str,
    amount_bif: Decimal,
) -> None:
    if not user_id:
        return

    async with async_session_maker() as db:
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO paylink.notifications (user_id, channel, subject, message, metadata)
                    VALUES (
                        CAST(:uid AS uuid),
                        'PAYOUT_ASSIGNMENT',
                        :subject,
                        :message,
                        CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    "uid": user_id,
                    "subject": "Nouvelle affectation payout",
                    "message": (
                        f"Vous avez une nouvelle affectation payout de {amount_bif} BIF "
                        f"(order {order_id})."
                    ),
                    "metadata": json.dumps(
                        {
                            "event": "PAYOUT_ASSIGNED",
                            "order_id": order_id,
                            "assignment_id": assignment_id,
                            "agent_id": agent_id,
                            "amount_bif": str(amount_bif),
                        }
                    ),
                },
            )
            await db.commit()
        except Exception:
            logger.exception(
                "Failed to persist payout assignment notification "
                "(order_id=%s, assignment_id=%s, agent_id=%s)",
                order_id,
                assignment_id,
                agent_id,
            )


async def _send_assignment_email(
    *,
    email: str | None,
    order_id: str,
    assignment_id: str,
    agent_id: str,
    amount_bif: Decimal,
) -> None:
    if not email:
        return
    try:
        notifier = EmailNotifier()
        await notifier.notify(
            recipient=email,
            message=NotificationMessage(
                subject="Nouvelle affectation payout",
                body_text=(
                    f"Nouvelle affectation payout de {amount_bif} BIF "
                    f"(order {order_id}, assignment {assignment_id}, agent {agent_id})."
                ),
            ),
        )
    except Exception:
        logger.exception(
            "Failed to send payout assignment email "
            "(order_id=%s, assignment_id=%s, agent_id=%s, email=%s)",
            order_id,
            assignment_id,
            agent_id,
            email,
        )


async def assign_agent_and_notify(order_id: str, amount_bif: float | Decimal) -> dict:
    amount = Decimal(str(amount_bif))
    if amount <= 0:
        raise ValueError("amount_bif must be > 0")

    assignment_id = str(uuid.uuid4())
    agent_email: str | None = None
    agent_user_id: str | None = None
    agent_id: str | None = None

    async with async_session_maker() as db:
        existing_assignment = await db.execute(
            text(
                """
                SELECT id, agent_id, status
                FROM payout.assignments
                WHERE order_id = CAST(:oid AS uuid)
                ORDER BY assigned_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"oid": order_id},
        )
        existing = existing_assignment.mappings().first()
        if existing and str(existing.get("status") or "").upper() in {"ASSIGNED", "CONFIRMED"}:
            return {
                "assignment_id": str(existing["id"]),
                "agent_id": str(existing["agent_id"]),
            }

        agent_res = await db.execute(
            text(
                """
                SELECT
                    agent_id,
                    display_name,
                    email,
                    phone,
                    user_id,
                    daily_limit_bif,
                    daily_used_bif
                FROM paylink.agents
                WHERE active = true
                  AND (
                    COALESCE(daily_limit_bif, 0) = 0
                    OR (COALESCE(daily_used_bif, 0) + :amt) <= COALESCE(daily_limit_bif, 0)
                  )
                ORDER BY last_assigned_at NULLS FIRST, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ),
            {"amt": amount},
        )
        agent_row = agent_res.mappings().first()
        if not agent_row:
            raise NoAvailablePayoutAgent(
                "No available payout agent (limits reached or none active)."
            )

        agent_id = str(agent_row["agent_id"])
        agent_user_id = str(agent_row["user_id"]) if agent_row.get("user_id") else None
        agent_email = str(agent_row["email"]) if agent_row.get("email") else None

        # Reserve BIF liquidity in ledger.
        await PaylinkLedgerService.post_journal(
            db,
            tx_id=uuid.uuid4(),
            description="Reserve BIF liquidity for payout assignment",
            postings=[
                {
                    "account_code": "CASH_BIF",
                    "direction": "DEBIT",
                    "amount": amount,
                    "currency": "BIF",
                },
                {
                    "account_code": "ESCROW_BIF_LIABILITY",
                    "direction": "CREDIT",
                    "amount": amount,
                    "currency": "BIF",
                },
            ],
            metadata={
                "event": "PAYOUT_ASSIGNMENT_RESERVE",
                "order_id": order_id,
                "assignment_id": assignment_id,
                "agent_id": agent_id,
            },
        )

        await db.execute(
            text(
                """
                INSERT INTO payout.assignments (id, order_id, agent_id, amount_bif, status)
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:oid AS uuid),
                    CAST(:aid AS uuid),
                    :amt,
                    'ASSIGNED'
                )
                """
            ),
            {"id": assignment_id, "oid": order_id, "aid": agent_id, "amt": amount},
        )

        await db.execute(
            text(
                """
                UPDATE paylink.agents
                SET daily_used_bif = COALESCE(daily_used_bif, 0) + :amt,
                    last_assigned_at = now()
                WHERE agent_id = CAST(:aid AS uuid)
                """
            ),
            {"amt": amount, "aid": agent_id},
        )

        await db.execute(
            text(
                """
                UPDATE escrow.orders
                SET status = 'PAYOUT_PENDING',
                    payout_initiated_at = COALESCE(payout_initiated_at, now()),
                    updated_at = now()
                WHERE id = CAST(:oid AS uuid)
                  AND status IN ('FUNDED', 'SWAPPED', 'PAYOUT_PENDING')
                """
            ),
            {"oid": order_id},
        )

        await db.commit()

    # Best-effort notification (must not fail the assignment flow).
    await _persist_assignment_notification(
        user_id=agent_user_id,
        order_id=order_id,
        assignment_id=assignment_id,
        agent_id=agent_id,
        amount_bif=amount,
    )
    await _send_assignment_email(
        email=agent_email,
        order_id=order_id,
        assignment_id=assignment_id,
        agent_id=agent_id,
        amount_bif=amount,
    )

    return {
        "assignment_id": assignment_id,
        "agent_id": agent_id,
    }
