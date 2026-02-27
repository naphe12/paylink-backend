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


def _build_assignment_email_html(
    *,
    order_id: str,
    assignment_id: str,
    agent_id: str,
    amount_bif: Decimal,
    usdc_amount: Decimal | None,
    client_name: str | None,
    client_email: str | None,
    client_phone: str | None,
    recipient_name: str | None,
    recipient_phone: str | None,
    payout_method: str | None,
) -> str:
    rows = [
        ("Commande escrow", order_id),
        ("Affectation", assignment_id),
        ("Agent", agent_id),
        ("Montant a payer", f"{amount_bif} BIF"),
    ]
    if usdc_amount is not None and usdc_amount > 0:
        rows.append(("Depot detecte", f"{usdc_amount} USD"))
    if client_name or client_email:
        rows.append(
            (
                "Client",
                " ".join(
                    p for p in [client_name or None, f"({client_email})" if client_email else None] if p
                ),
            )
        )
    if client_phone:
        rows.append(("Telephone client", client_phone))
    if recipient_name:
        rows.append(("Beneficiaire", recipient_name))
    if recipient_phone:
        rows.append(("Telephone beneficiaire", recipient_phone))
    if payout_method:
        rows.append(("Mode de payout", payout_method))

    rows_html = "".join(
        f"<p><strong>{label}:</strong> {value}</p>"
        for label, value in rows
        if value
    )
    return (
        "<div>"
        "<p>Une demande escrow PayLink vient d'etre detectee apres depot USD.</p>"
        "<p>Merci de preparer le paiement BIF correspondant.</p>"
        f"{rows_html}"
        "</div>"
    )


async def _persist_assignment_notification(
    *,
    user_id: str | None,
    order_id: str,
    assignment_id: str,
    agent_id: str,
    amount_bif: Decimal,
    client_name: str | None,
    recipient_name: str | None,
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
                        f"pour {recipient_name or 'le beneficiaire'} "
                        f"(client {client_name or 'inconnu'}, order {order_id})."
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
    usdc_amount: Decimal | None,
    client_name: str | None,
    client_email: str | None,
    client_phone: str | None,
    recipient_name: str | None,
    recipient_phone: str | None,
    payout_method: str | None,
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
                body_html=_build_assignment_email_html(
                    order_id=order_id,
                    assignment_id=assignment_id,
                    agent_id=agent_id,
                    amount_bif=amount_bif,
                    usdc_amount=usdc_amount,
                    client_name=client_name,
                    client_email=client_email,
                    client_phone=client_phone,
                    recipient_name=recipient_name,
                    recipient_phone=recipient_phone,
                    payout_method=payout_method,
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
    client_name: str | None = None
    client_email: str | None = None
    client_phone: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    payout_method: str | None = None
    usdc_amount: Decimal | None = None

    async with async_session_maker() as db:
        order_res = await db.execute(
            text(
                """
                SELECT
                    o.status::text AS order_status,
                    o.payout_account_name,
                    o.payout_account_number,
                    o.payout_method::text AS payout_method,
                    o.usdc_received,
                    o.usdc_expected,
                    u.full_name AS client_name,
                    u.email AS client_email,
                    u.phone_e164 AS client_phone
                FROM escrow.orders o
                LEFT JOIN paylink.users u ON u.user_id = o.user_id
                WHERE o.id = CAST(:oid AS uuid)
                LIMIT 1
                """
            ),
            {"oid": order_id},
        )
        order_row = order_res.mappings().first()
        if not order_row:
            raise ValueError("Order not found")

        order_status = str(order_row.get("order_status") or "").upper()
        recipient_name = str(order_row["payout_account_name"]) if order_row.get("payout_account_name") else None
        recipient_phone = str(order_row["payout_account_number"]) if order_row.get("payout_account_number") else None
        payout_method = str(order_row["payout_method"]) if order_row.get("payout_method") else None
        client_name = str(order_row["client_name"]) if order_row.get("client_name") else None
        client_email = str(order_row["client_email"]) if order_row.get("client_email") else None
        client_phone = str(order_row["client_phone"]) if order_row.get("client_phone") else None

        usdc_value = order_row.get("usdc_received") or order_row.get("usdc_expected")
        if usdc_value is not None:
            usdc_amount = Decimal(str(usdc_value))

        existing_assignment = await db.execute(
            text(
                """
                SELECT id, agent_id, status
                FROM paylink.assignments
                WHERE order_id = CAST(:oid AS uuid)
                ORDER BY assigned_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"oid": order_id},
        )
        existing = existing_assignment.mappings().first()
        if existing and str(existing.get("status") or "").upper() in {"ASSIGNED", "CONFIRMED"}:
            if order_status in {"SWAPPED", "PAYOUT_PENDING"}:
                await db.execute(
                    text(
                        """
                        UPDATE escrow.orders
                        SET status = 'PAYOUT_PENDING',
                            payout_initiated_at = COALESCE(payout_initiated_at, now()),
                            updated_at = now()
                        WHERE id = CAST(:oid AS uuid)
                          AND status IN ('SWAPPED', 'PAYOUT_PENDING')
                        """
                    ),
                    {"oid": order_id},
                )
                await db.commit()
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
                INSERT INTO paylink.assignments (id, order_id, agent_id, amount_bif, status)
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
                  AND status IN ('SWAPPED', 'PAYOUT_PENDING')
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
        client_name=client_name,
        recipient_name=recipient_name,
    )
    await _send_assignment_email(
        email=agent_email,
        order_id=order_id,
        assignment_id=assignment_id,
        agent_id=agent_id,
        amount_bif=amount,
        usdc_amount=usdc_amount,
        client_name=client_name,
        client_email=client_email,
        client_phone=client_phone,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        payout_method=payout_method,
    )

    return {
        "assignment_id": assignment_id,
        "agent_id": agent_id,
    }
