from datetime import datetime, timezone
import json
import logging
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escrow_chain_deposit import EscrowChainDeposit
from app.models.escrow_enums import EscrowOrderStatus
from app.models.escrow_order import EscrowOrder
from schemas.escrow_chain import ChainDepositWebhook
from services.escrow_notifications import notify
from services.risk_service import RiskService
from services.escrow_ledger_hooks import post_funded_usdc_deposit_journal as on_funded
from app.models.users import Users
from app.services.aml_service import run_aml
from app.services.audit_service import audit_log
from app.services.risk_decision_log import log_risk_decision
from app.services.escrow_tracking_ws import broadcast_tracking_update
from app.services.payout_orchestrator import assign_agent_and_notify
from app.services.p2p_chain_webhook_service import process_p2p_chain_deposit_webhook
from app.services.webhook_log_service import log_webhook
from app.services.wallet_service import credit_user_usdc
from app.services.escrow_order_rules import transition_escrow_order_status

logger = logging.getLogger(__name__)


async def process_usdc_webhook(
    db: AsyncSession,
    payload: ChainDepositWebhook,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict:
    res = await db.execute(
        select(EscrowOrder)
        .where(EscrowOrder.deposit_address == payload.to_address)
        .where(EscrowOrder.deposit_network == payload.network)
    )
    order = res.scalar_one_or_none()
    if not order:
        raise ValueError("Escrow order not found")

    if order.status != EscrowOrderStatus.CREATED:
        return {"status": "IGNORED", "order_id": str(order.id)}

    deposit = EscrowChainDeposit(
        order_id=order.id,
        network=payload.network,
        tx_hash=payload.tx_hash,
        from_address=payload.from_address,
        to_address=payload.to_address,
        amount=payload.amount,
        confirmations=payload.confirmations,
        detected_at=datetime.now(timezone.utc),
    )

    try:
        db.add(deposit)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        await log_webhook(
            db,
            event_type="USDC_DEPOSIT",
            status="IGNORED_DUPLICATE",
            payload=payload.model_dump(mode="json"),
            tx_hash=payload.tx_hash,
            attempts=0,
        )
        await db.commit()
        return {"status": "IGNORED_DUPLICATE"}

    subject = None
    message = None
    before_state = {"status": str(order.status)}
    response_status = str(order.status)
    if payload.confirmations >= order.deposit_required_confirmations:
        order.usdc_received = payload.amount
        order.deposit_tx_hash = payload.tx_hash
        order.deposit_confirmations = payload.confirmations
        order.funded_at = datetime.now(timezone.utc)
        user = await db.get(Users, order.user_id)
        if not user:
            raise ValueError("User not found")

        risk = await RiskService.evaluate_funded(db, user=user, order=order)
        aml = await run_aml(
            db,
            user=user,
            order=order,
            stage="FUNDED",
            actor_user_id=None,
            actor_role="SYSTEM",
            ip=ip,
            user_agent=user_agent,
        )
        await log_risk_decision(
            db,
            user_id=str(user.user_id),
            order_id=str(order.id),
            stage="FUNDED",
            result=risk,
        )
        order.risk_score = int(risk.score or 0)

        flags = [str(f) for f in list(order.flags or [])]
        flags = [
            f
            for f in flags
            if f not in {"MANUAL_REVIEW:FUNDED", "BLOCKED:FUNDED", "MANUAL_REVIEW:AML_FUNDED", "BLOCKED:AML_FUNDED"}
        ]
        if risk.decision == "BLOCK" or aml.decision == "BLOCK":
            flags.append("BLOCKED:FUNDED")
            if aml.decision == "BLOCK":
                flags.append("BLOCKED:AML_FUNDED")
            transition_escrow_order_status(order, EscrowOrderStatus.CANCELLED)
            if "AML_REVIEW" not in flags:
                flags.append("AML_REVIEW")
            response_status = "BLOCKED"
        elif risk.decision == "REVIEW" or aml.decision == "REVIEW":
            flags.append("MANUAL_REVIEW:FUNDED")
            if aml.decision == "REVIEW":
                flags.append("MANUAL_REVIEW:AML_FUNDED")
                if "AML_REVIEW" not in flags:
                    flags.append("AML_REVIEW")
            response_status = "MANUAL_REVIEW"
        else:
            transition_escrow_order_status(order, EscrowOrderStatus.FUNDED)
            response_status = "FUNDED"
            await on_funded(db, order)
            await credit_user_usdc(
                str(order.user_id),
                Decimal(str(order.usdc_received or payload.amount)),
                db=db,
                ref=f"ESCROW_FUNDED_CREDIT:{order.id}",
                description="Escrow FUNDED: credit user USDC wallet",
            )
            subject = "USDC recus"
            message = (
                f"Nous avons recu votre paiement USDC pour la transaction {order.id}. "
                "Nous traitons la conversion."
            )
        order.flags = flags

        await audit_log(
            db,
            actor_user_id=None,
            actor_role="SYSTEM",
            action="WEBHOOK_USDC_FUNDED",
            entity_type="escrow_order",
            entity_id=str(order.id),
            before_state=before_state,
            after_state={
                "status": response_status,
                "tx_hash": payload.tx_hash,
                "risk": {
                    "score": risk.score,
                    "decision": risk.decision,
                    "reasons": risk.reasons,
                },
                "aml": {
                    "score": aml.score,
                    "decision": aml.decision,
                    "hits": aml.hits,
                },
            },
            ip=ip,
            user_agent=user_agent,
        )

    await db.commit()
    if payload.confirmations >= order.deposit_required_confirmations:
        await broadcast_tracking_update(order)

    if subject and message:
        await notify(
            db,
            user_id=order.user_id,
            subject=subject,
            message=message,
        )
    if response_status == "FUNDED":
        try:
            await assign_agent_and_notify(str(order.id), Decimal(str(order.bif_target or 0)))
        except Exception:
            logger.exception("Failed to assign agent after funded webhook for order_id=%s", order.id)

    await log_webhook(
        db,
        event_type="USDC_DEPOSIT",
        status="SUCCESS",
        payload=payload.model_dump(mode="json"),
        tx_hash=payload.tx_hash,
        attempts=0,
    )
    await db.commit()

    return {
        "status": response_status if payload.confirmations >= order.deposit_required_confirmations else "PENDING_CONFIRMATIONS",
        "order_id": str(order.id),
        "escrow_status": response_status if payload.confirmations >= order.deposit_required_confirmations else str(order.status),
    }


async def enqueue_webhook_retry(
    db: AsyncSession,
    *,
    event_type: str,
    payload: dict,
    last_error: str,
    actor_user_id: str | None = None,
    actor_role: str | None = "SYSTEM",
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS escrow.webhook_retries (
              id bigserial PRIMARY KEY,
              event_type text NOT NULL,
              payload jsonb NOT NULL,
              attempts int NOT NULL DEFAULT 0,
              last_error text,
              next_retry_at timestamptz NOT NULL DEFAULT now(),
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO escrow.webhook_retries (event_type, payload, last_error)
            VALUES (:event_type, CAST(:payload AS jsonb), :last_error)
            """
        ),
        {
            "event_type": event_type,
            "payload": json.dumps(payload),
            "last_error": last_error,
        },
    )
    await log_webhook(
        db,
        event_type=event_type,
        status="FAILED",
        payload=payload,
        tx_hash=payload.get("tx_hash"),
        attempts=0,
        error=last_error,
    )
    await audit_log(
        db,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action="WEBHOOK_RETRY_ENQUEUED",
        entity_type="escrow_webhook",
        entity_id=None,
        before_state=None,
        after_state={
            "status": "QUEUED_RETRY",
            "event_type": event_type,
            "tx_hash": payload.get("tx_hash"),
            "error": last_error,
        },
        ip=ip,
        user_agent=user_agent,
    )
    await db.commit()


async def retry_failed_webhooks(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS escrow.webhook_retries (
              id bigserial PRIMARY KEY,
              event_type text NOT NULL,
              payload jsonb NOT NULL,
              attempts int NOT NULL DEFAULT 0,
              last_error text,
              next_retry_at timestamptz NOT NULL DEFAULT now(),
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )

    rows = (
        await db.execute(
            text(
                """
                SELECT id, payload, attempts
                     , event_type
                FROM escrow.webhook_retries
                WHERE next_retry_at <= now()
                  AND attempts < 10
                ORDER BY created_at
                LIMIT 20
                """
            )
        )
    ).fetchall()

    for row in rows:
        row_map = row._mapping
        retry_id = row_map["id"]
        retry_payload = row_map["payload"]
        try:
            event_type = row_map.get("event_type") or "USDC_DEPOSIT"
            if event_type == "USDC_DEPOSIT":
                payload = ChainDepositWebhook(**retry_payload)
                await process_usdc_webhook(db, payload)
            elif event_type == "P2P_CHAIN_DEPOSIT":
                await process_p2p_chain_deposit_webhook(db, dict(retry_payload or {}))
            else:
                raise ValueError(f"Unsupported webhook retry event_type={event_type}")
            await db.execute(
                text("DELETE FROM escrow.webhook_retries WHERE id = :id"),
                {"id": retry_id},
            )
            await log_webhook(
                db,
                event_type=event_type,
                status="SUCCESS_RETRY",
                payload=retry_payload,
                tx_hash=retry_payload.get("tx_hash"),
                attempts=int(row_map.get("attempts") or 0) + 1,
            )
        except Exception as exc:
            await db.execute(
                text(
                    """
                    UPDATE escrow.webhook_retries
                    SET attempts = attempts + 1,
                        last_error = :err,
                        next_retry_at = now() + interval '5 minutes'
                    WHERE id = :id
                    """
                ),
                {"id": retry_id, "err": str(exc)},
            )
            await log_webhook(
                db,
                event_type=row_map.get("event_type") or "USDC_DEPOSIT",
                status="FAILED_RETRY",
                payload=retry_payload,
                tx_hash=retry_payload.get("tx_hash"),
                attempts=int(row_map.get("attempts") or 0) + 1,
                error=str(exc),
            )

    await db.commit()
