from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def fetch_escrow_order_rows(
    db: AsyncSession,
    *,
    status: str | None,
    min_risk: int | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int = 200,
):
    return await db.execute(
        text(
            f"""
            SELECT
              o.id,
              o.status::text AS status,
              o.user_id,
              u.full_name AS user_name,
              o.trader_id,
              t.full_name AS trader_name,
              o.usdc_expected,
              o.usdc_received,
              o.usdt_target,
              o.usdt_received,
              o.bif_target,
              o.bif_paid,
              o.risk_score,
              o.flags,
              o.deposit_network,
              o.deposit_address,
              o.deposit_tx_hash,
              o.payout_method::text AS payout_method,
              o.payout_provider,
              o.payout_account_name,
              o.payout_account_number,
              o.payout_reference,
              o.funded_at,
              o.swapped_at,
              o.payout_initiated_at,
              o.paid_out_at,
              o.created_at,
              o.updated_at
            FROM escrow.orders o
            LEFT JOIN paylink.users u ON u.user_id = o.user_id
            LEFT JOIN paylink.users t ON t.user_id = o.trader_id
            WHERE (:status IS NULL OR o.status::text = :status)
              AND (:min_risk IS NULL OR COALESCE(o.risk_score, 0) >= :min_risk)
              AND (:created_from IS NULL OR o.created_at >= :created_from)
              AND (:created_to IS NULL OR o.created_at <= :created_to)
            ORDER BY o.created_at DESC
            LIMIT {int(limit)}
            """
        ),
        {
            "status": status,
            "min_risk": min_risk,
            "created_from": created_from,
            "created_to": created_to,
        },
    )


async def fetch_escrow_order_detail_row(db: AsyncSession, order_id: str):
    return await db.execute(
        text(
            """
            SELECT
              o.id,
              o.status::text AS status,
              o.user_id,
              u.full_name AS user_name,
              o.trader_id,
              t.full_name AS trader_name,
              o.usdc_expected,
              o.usdc_received,
              o.usdt_target,
              o.usdt_received,
              o.bif_target,
              o.bif_paid,
              o.risk_score,
              o.flags,
              o.deposit_network,
              o.deposit_address,
              o.deposit_tx_hash,
              o.payout_method::text AS payout_method,
              o.payout_provider,
              o.payout_account_name,
              o.payout_account_number,
              o.payout_reference,
              o.funded_at,
              o.swapped_at,
              o.payout_initiated_at,
              o.paid_out_at,
              o.created_at,
              o.updated_at
            FROM escrow.orders o
            LEFT JOIN paylink.users u ON u.user_id = o.user_id
            LEFT JOIN paylink.users t ON t.user_id = o.trader_id
            WHERE o.id = :order_id
            LIMIT 1
            """
        ),
        {"order_id": order_id},
    )


async def fetch_escrow_refund_audit_rows(db: AsyncSession, order_id: str):
    return await db.execute(
        text(
            """
            SELECT
              id,
              action,
              actor_user_id,
              actor_role,
              after_state,
              created_at
            FROM paylink.audit_log
            WHERE entity_type = 'escrow_order'
              AND entity_id = CAST(:order_id AS uuid)
              AND action IN ('ESCROW_REFUND_REQUESTED', 'ESCROW_REFUNDED')
            ORDER BY created_at DESC
            """
        ),
        {"order_id": str(order_id)},
    )
