from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def fetch_admin_trade_rows(db: AsyncSession):
    return await db.execute(
        text(
            """
            SELECT
              t.trade_id,
              t.offer_id,
              t.status::text AS status,
              t.created_at,
              t.updated_at,
              t.expires_at,
              t.token::text AS token,
              t.token_amount,
              t.price_bif_per_usd,
              t.bif_amount,
              t.payment_method::text AS payment_method,
              t.risk_score,
              t.flags,
              t.escrow_deposit_ref,
              t.escrow_provider,
              t.escrow_tx_hash,
              t.escrow_lock_log_index,
              t.fiat_sent_at,
              t.fiat_confirmed_at,
              t.buyer_id,
              ub.full_name AS buyer_name,
              t.seller_id,
              us.full_name AS seller_name,
              o.side::text AS offer_side,
              o.user_id AS offer_owner_id,
              uo.full_name AS offer_owner_name,
              COALESCE(d.disputes_count, 0) AS disputes_count
            FROM p2p.trades t
            LEFT JOIN p2p.offers o ON o.offer_id = t.offer_id
            LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
            LEFT JOIN paylink.users us ON us.user_id = t.seller_id
            LEFT JOIN paylink.users uo ON uo.user_id = o.user_id
            LEFT JOIN (
              SELECT trade_id, COUNT(*)::int AS disputes_count
              FROM p2p.disputes
              GROUP BY trade_id
            ) d ON d.trade_id = t.trade_id
            ORDER BY t.created_at DESC
            """
        )
    )


async def fetch_admin_trade_detail_row(db: AsyncSession, trade_id: str):
    return await db.execute(
        text(
            """
            SELECT
              t.trade_id,
              t.offer_id,
              t.status::text AS status,
              t.created_at,
              t.updated_at,
              t.expires_at,
              t.token::text AS token,
              t.token_amount,
              t.price_bif_per_usd,
              t.bif_amount,
              t.payment_method::text AS payment_method,
              t.risk_score,
              t.flags,
              t.escrow_network,
              t.escrow_deposit_addr,
              t.escrow_deposit_ref,
              t.escrow_provider,
              t.escrow_tx_hash,
              t.escrow_lock_log_index,
              t.escrow_locked_at,
              t.fiat_sent_at,
              t.fiat_confirmed_at,
              t.buyer_id,
              ub.full_name AS buyer_name,
              t.seller_id,
              us.full_name AS seller_name,
              o.side::text AS offer_side,
              o.user_id AS offer_owner_id,
              uo.full_name AS offer_owner_name,
              COALESCE(d.disputes_count, 0) AS disputes_count
            FROM p2p.trades t
            LEFT JOIN p2p.offers o ON o.offer_id = t.offer_id
            LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
            LEFT JOIN paylink.users us ON us.user_id = t.seller_id
            LEFT JOIN paylink.users uo ON uo.user_id = o.user_id
            LEFT JOIN (
              SELECT trade_id, COUNT(*)::int AS disputes_count
              FROM p2p.disputes
              GROUP BY trade_id
            ) d ON d.trade_id = t.trade_id
            WHERE t.trade_id = CAST(:trade_id AS uuid)
            """
        ),
        {"trade_id": trade_id},
    )


async def fetch_p2p_dispute_rows(db: AsyncSession):
    return await db.execute(
        text(
            """
            SELECT
              d.dispute_id,
              d.trade_id,
              NULL::uuid AS tx_id,
              d.status::text AS status,
              d.reason,
              d.created_at,
              NULL::timestamptz AS updated_at,
              d.resolved_at,
              d.opened_by AS opened_by_user_id,
              uo.full_name AS opened_by_name,
              d.resolved_by AS resolved_by_user_id,
              ur.full_name AS resolved_by_name,
              d.resolution,
              NULL::text AS evidence_url,
              t.buyer_id,
              ub.full_name AS buyer_name,
              t.seller_id,
              us.full_name AS seller_name,
              t.token::text AS token,
              t.token_amount,
              t.price_bif_per_usd,
              t.bif_amount,
              t.payment_method::text AS payment_method,
              t.status::text AS trade_status,
              NULL::numeric AS tx_amount,
              NULL::text AS tx_currency
            FROM p2p.disputes d
            LEFT JOIN p2p.trades t ON t.trade_id = d.trade_id
            LEFT JOIN paylink.users uo ON uo.user_id = d.opened_by
            LEFT JOIN paylink.users ur ON ur.user_id = d.resolved_by
            LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
            LEFT JOIN paylink.users us ON us.user_id = t.seller_id
            ORDER BY created_at DESC
            """
        )
    )


async def fetch_legacy_dispute_rows(db: AsyncSession):
    return await db.execute(
        text(
            """
            SELECT
              d.dispute_id,
              NULL::uuid AS trade_id,
              d.tx_id,
              d.status::text AS status,
              d.reason,
              d.created_at,
              d.updated_at,
              NULL::timestamptz AS resolved_at,
              d.opened_by AS opened_by_user_id,
              uo.full_name AS opened_by_name,
              NULL::uuid AS resolved_by_user_id,
              NULL::text AS resolved_by_name,
              NULL::text AS resolution,
              d.evidence_url,
              NULL::uuid AS buyer_id,
              NULL::text AS buyer_name,
              NULL::uuid AS seller_id,
              NULL::text AS seller_name,
              NULL::text AS token,
              NULL::numeric AS token_amount,
              NULL::numeric AS price_bif_per_usd,
              NULL::numeric AS bif_amount,
              NULL::text AS payment_method,
              NULL::text AS trade_status,
              t.amount AS tx_amount,
              t.currency_code::text AS tx_currency
            FROM paylink.disputes d
            LEFT JOIN paylink.users uo ON uo.user_id = d.opened_by
            LEFT JOIN paylink.transactions t ON t.tx_id = d.tx_id
            ORDER BY created_at DESC
            """
        )
    )


async def fetch_p2p_dispute_opened_audit_rows(db: AsyncSession, trade_id: str):
    return await db.execute(
        text(
            """
            SELECT id, action, actor_user_id, actor_role, before_state, after_state, created_at
            FROM paylink.audit_log
            WHERE entity_type = 'p2p_trade'
              AND entity_id = CAST(:trade_id AS uuid)
              AND action = 'P2P_DISPUTE_OPENED'
            ORDER BY created_at ASC
            """
        ),
        {"trade_id": trade_id},
    )


async def fetch_p2p_dispute_resolved_audit_rows(db: AsyncSession, dispute_id: str):
    return await db.execute(
        text(
            """
            SELECT id, action, actor_user_id, actor_role, before_state, after_state, created_at
            FROM paylink.audit_log
            WHERE entity_type = 'p2p_dispute'
              AND entity_id = CAST(:dispute_id AS uuid)
              AND action = 'P2P_DISPUTE_RESOLVED'
            ORDER BY created_at ASC
            """
        ),
        {"dispute_id": dispute_id},
    )


async def fetch_latest_p2p_dispute_opened_state(db: AsyncSession, trade_id: str):
    return await db.execute(
        text(
            """
            SELECT after_state
            FROM paylink.audit_log
            WHERE entity_type = 'p2p_trade'
              AND entity_id = CAST(:trade_id AS uuid)
              AND action = 'P2P_DISPUTE_OPENED'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"trade_id": trade_id},
    )


async def fetch_latest_p2p_dispute_resolved_state(db: AsyncSession, dispute_id: str):
    return await db.execute(
        text(
            """
            SELECT after_state
            FROM paylink.audit_log
            WHERE entity_type = 'p2p_dispute'
              AND entity_id = CAST(:dispute_id AS uuid)
              AND action = 'P2P_DISPUTE_RESOLVED'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"dispute_id": dispute_id},
    )
