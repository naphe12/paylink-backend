from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin

router = APIRouter(prefix="/admin/wallet-analysis", tags=["Admin Wallet Analysis"])


async def _relation_exists(db: AsyncSession, relation_name: str) -> bool:
    result = await db.execute(
        text("SELECT to_regclass(:relation_name) IS NOT NULL AS exists"),
        {"relation_name": relation_name},
    )
    return bool(result.scalar())


@router.get("")
@router.get("/")
async def get_wallet_analysis(
    user_id: str = Query(...),
    cutoff_date: date = Query(default=date(2025, 12, 20)),
    limit: int = Query(100, ge=10, le=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user_row = (
        await db.execute(
            text(
                """
                SELECT
                  u.user_id,
                  u.full_name,
                  u.email,
                  u.phone_e164,
                  u.username,
                  u.credit_used,
                  u.credit_limit
                FROM paylink.users u
                WHERE u.user_id = CAST(:user_id AS uuid)
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()

    if not user_row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    params = {
        "user_id": user_id,
        "cutoff_date": cutoff_date,
        "limit": limit,
    }
    legacy_clients_exists = await _relation_exists(db, "legacy.clients")
    legacy_credit_du_exists = await _relation_exists(db, "legacy.client_credit_du")
    paylink_credit_payments_exists = await _relation_exists(db, "paylink.credit_line_payments")
    legacy_sending_logs_exists = await _relation_exists(db, "legacy.sending_logs")

    legacy_clients = []
    if legacy_clients_exists:
        legacy_clients = (
            await db.execute(
                text(
                    """
                    WITH target_user AS (
                      SELECT
                        user_id,
                        lower(coalesce(email, '')) AS email_norm,
                        regexp_replace(coalesce(phone_e164, ''), '\\D', '', 'g') AS phone_norm,
                        lower(coalesce(username, '')) AS username_norm
                      FROM paylink.users
                      WHERE user_id = CAST(:user_id AS uuid)
                    )
                    SELECT
                      c.id,
                      c.name,
                      c.email,
                      c.phone,
                      c.username,
                      c.balance,
                      CASE
                        WHEN lower(coalesce(c.email, '')) = tu.email_norm AND tu.email_norm <> '' THEN 'email'
                        WHEN regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g') = tu.phone_norm AND tu.phone_norm <> '' THEN 'phone'
                        WHEN lower(coalesce(c.username, '')) = tu.username_norm AND tu.username_norm <> '' THEN 'username'
                        ELSE 'unknown'
                      END AS match_type
                    FROM legacy.clients c
                    CROSS JOIN target_user tu
                    WHERE
                      (lower(coalesce(c.email, '')) = tu.email_norm AND tu.email_norm <> '')
                      OR (regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g') = tu.phone_norm AND tu.phone_norm <> '')
                      OR (lower(coalesce(c.username, '')) = tu.username_norm AND tu.username_norm <> '')
                    ORDER BY c.id
                    """
                ),
                params,
            )
        ).mappings().all()

    wallet_rows = (
        await db.execute(
            text(
                """
                SELECT
                  wallet_id,
                  type,
                  currency_code,
                  available,
                  pending,
                  bonus_balance
                FROM paylink.wallets
                WHERE user_id = CAST(:user_id AS uuid)
                ORDER BY currency_code, type
                """
            ),
            params,
        )
    ).mappings().all()

    balance_event_summary = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*)::int AS total_events,
                  COALESCE(SUM(amount_delta), 0) AS total_delta,
                  MIN(occurred_at) AS first_event_at,
                  MAX(occurred_at) AS last_event_at,
                  COUNT(*) FILTER (WHERE occurred_at >= CAST(:cutoff_date AS timestamptz))::int AS events_after_cutoff,
                  COALESCE(SUM(amount_delta) FILTER (WHERE occurred_at >= CAST(:cutoff_date AS timestamptz)), 0) AS delta_after_cutoff
                FROM paylink.client_balance_events
                WHERE user_id = CAST(:user_id AS uuid)
                """
            ),
            params,
        )
    ).mappings().first()

    credit_due_summary = {
        "total_rows": 0,
        "total_credit_used": 0,
        "total_credit_repaid": 0,
        "net_credit_delta": 0,
        "rows_after_cutoff": 0,
    }
    if legacy_clients_exists and legacy_credit_du_exists:
        credit_due_summary = (
            await db.execute(
                text(
                    """
                    WITH matched_clients AS (
                      SELECT c.id
                      FROM legacy.clients c
                      JOIN paylink.users u
                        ON (
                          lower(coalesce(c.email, '')) = lower(coalesce(u.email, ''))
                          OR regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g') = regexp_replace(coalesce(u.phone_e164, ''), '\\D', '', 'g')
                          OR lower(coalesce(c.username, '')) = lower(coalesce(u.username, ''))
                        )
                      WHERE u.user_id = CAST(:user_id AS uuid)
                    )
                    SELECT
                      COUNT(*)::int AS total_rows,
                      COALESCE(SUM(CASE WHEN montant > 0 THEN montant ELSE 0 END), 0) AS total_credit_used,
                      COALESCE(SUM(CASE WHEN montant < 0 THEN ABS(montant) ELSE 0 END), 0) AS total_credit_repaid,
                      COALESCE(SUM(montant), 0) AS net_credit_delta,
                      COUNT(*) FILTER (WHERE created_at >= CAST(:cutoff_date AS timestamptz))::int AS rows_after_cutoff
                    FROM legacy.client_credit_du
                    WHERE clientid IN (SELECT id FROM matched_clients)
                    """
                ),
                params,
            )
        ).mappings().first() or credit_due_summary

    credit_payment_summary = {
        "total_rows": 0,
        "total_amount": 0,
        "total_amount_eur": 0,
        "first_payment_at": None,
        "last_payment_at": None,
        "rows_after_cutoff": 0,
    }
    if paylink_credit_payments_exists:
        credit_payment_summary = (
            await db.execute(
                text(
                    """
                    SELECT
                      COUNT(*)::int AS total_rows,
                      COALESCE(SUM(amount), 0) AS total_amount,
                      COALESCE(SUM(amount_eur), 0) AS total_amount_eur,
                      MIN(COALESCE(occurred_at, created_at)) AS first_payment_at,
                      MAX(COALESCE(occurred_at, created_at)) AS last_payment_at,
                      COUNT(*) FILTER (WHERE COALESCE(occurred_at, created_at) >= CAST(:cutoff_date AS timestamptz))::int AS rows_after_cutoff
                    FROM paylink.credit_line_payments
                    WHERE user_id = CAST(:user_id AS uuid)
                    """
                ),
                params,
            )
        ).mappings().first() or credit_payment_summary

    sending_summary = {
        "total_rows": 0,
        "total_amount": 0,
        "total_amount_with_fees": 0,
        "total_sending_amount": 0,
        "total_receiving_amount": 0,
        "total_charge": 0,
        "first_sending_at": None,
        "last_sending_at": None,
        "rows_after_cutoff": 0,
    }
    if legacy_clients_exists and legacy_sending_logs_exists:
        sending_summary = (
            await db.execute(
                text(
                    """
                    WITH matched_clients AS (
                      SELECT c.id
                      FROM legacy.clients c
                      JOIN paylink.users u
                        ON (
                          lower(coalesce(c.email, '')) = lower(coalesce(u.email, ''))
                          OR regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g') = regexp_replace(coalesce(u.phone_e164, ''), '\\D', '', 'g')
                          OR lower(coalesce(c.username, '')) = lower(coalesce(u.username, ''))
                        )
                      WHERE u.user_id = CAST(:user_id AS uuid)
                    )
                    SELECT
                      COUNT(*)::int AS total_rows,
                      COALESCE(SUM(amount), 0) AS total_amount,
                      COALESCE(SUM(total_amount), 0) AS total_amount_with_fees,
                      COALESCE(SUM(sending_amount), 0) AS total_sending_amount,
                      COALESCE(SUM(receiving_amount), 0) AS total_receiving_amount,
                      COALESCE(SUM(charge), 0) AS total_charge,
                      MIN(created_at) AS first_sending_at,
                      MAX(created_at) AS last_sending_at,
                      COUNT(*) FILTER (WHERE created_at >= CAST(:cutoff_date AS timestamptz))::int AS rows_after_cutoff
                    FROM legacy.sending_logs
                    WHERE user_id IN (SELECT id FROM matched_clients)
                    """
                ),
                params,
            )
        ).mappings().first() or sending_summary

    timeline_rows = []
    if legacy_clients_exists:
        timeline_parts = [
            """
            SELECT
              occurred_at AS event_at,
              'client_balance_event'::text AS source,
              amount_delta::numeric AS amount,
              currency::text AS currency,
              source AS subtype,
              legacy_id::text AS reference
            FROM paylink.client_balance_events
            WHERE user_id = CAST(:user_id AS uuid)
            """
        ]
        if legacy_credit_du_exists:
            timeline_parts.append(
                """
                SELECT
                  created_at AS event_at,
                  'legacy_credit_du'::text AS source,
                  montant::numeric AS amount,
                  currency::text AS currency,
                  CASE WHEN montant > 0 THEN 'credit_used' WHEN montant < 0 THEN 'credit_repaid' ELSE 'neutral' END AS subtype,
                  id::text AS reference
                FROM legacy.client_credit_du
                WHERE clientid IN (SELECT id FROM matched_clients)
                """
            )
        if paylink_credit_payments_exists:
            timeline_parts.append(
                """
                SELECT
                  COALESCE(occurred_at, created_at) AS event_at,
                  'credit_line_payment'::text AS source,
                  amount::numeric AS amount,
                  currency_code::text AS currency,
                  'payment'::text AS subtype,
                  payment_id::text AS reference
                FROM paylink.credit_line_payments
                WHERE user_id = CAST(:user_id AS uuid)
                """
            )
        if legacy_sending_logs_exists:
            timeline_parts.append(
                """
                SELECT
                  created_at AS event_at,
                  'legacy_sending'::text AS source,
                  amount::numeric AS amount,
                  currency::text AS currency,
                  status::text AS subtype,
                  id::text AS reference
                FROM legacy.sending_logs
                WHERE user_id IN (SELECT id FROM matched_clients)
                """
            )
        timeline_rows = (
            await db.execute(
                text(
                    f"""
                    WITH matched_clients AS (
                      SELECT c.id
                      FROM legacy.clients c
                      JOIN paylink.users u
                        ON (
                          lower(coalesce(c.email, '')) = lower(coalesce(u.email, ''))
                          OR regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g') = regexp_replace(coalesce(u.phone_e164, ''), '\\D', '', 'g')
                          OR lower(coalesce(c.username, '')) = lower(coalesce(u.username, ''))
                        )
                      WHERE u.user_id = CAST(:user_id AS uuid)
                    ),
                    unioned AS (
                      {" UNION ALL ".join(timeline_parts)}
                    )
                    SELECT
                      event_at,
                      source,
                      amount,
                      currency,
                      subtype,
                      reference
                    FROM unioned
                    ORDER BY event_at DESC NULLS LAST
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).mappings().all()
    else:
        timeline_rows = (
            await db.execute(
                text(
                    """
                    SELECT
                      occurred_at AS event_at,
                      'client_balance_event'::text AS source,
                      amount_delta::numeric AS amount,
                      currency::text AS currency,
                      source AS subtype,
                      legacy_id::text AS reference
                    FROM paylink.client_balance_events
                    WHERE user_id = CAST(:user_id AS uuid)
                    ORDER BY occurred_at DESC NULLS LAST
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).mappings().all()

    gap_summary = {
        "cutoff_date": cutoff_date,
        "legacy_activity_after_cutoff": int(
            (credit_due_summary["rows_after_cutoff"] or 0)
            + (credit_payment_summary["rows_after_cutoff"] or 0)
            + (sending_summary["rows_after_cutoff"] or 0)
        ),
        "client_balance_events_after_cutoff": int(balance_event_summary["events_after_cutoff"] or 0),
    }

    return {
        "user": {
            "user_id": str(user_row["user_id"]),
            "full_name": user_row["full_name"],
            "email": user_row["email"],
            "phone_e164": user_row["phone_e164"],
            "username": user_row["username"],
            "credit_used": float(user_row["credit_used"] or 0),
            "credit_limit": float(user_row["credit_limit"] or 0),
        },
        "legacy_clients": [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "username": row["username"],
                "balance": float(row["balance"] or 0),
                "match_type": row["match_type"],
            }
            for row in legacy_clients
        ],
        "wallets": [
            {
                "wallet_id": str(row["wallet_id"]),
                "type": row["type"],
                "currency_code": row["currency_code"],
                "available": float(row["available"] or 0),
                "pending": float(row["pending"] or 0),
                "bonus_balance": float(row["bonus_balance"] or 0),
            }
            for row in wallet_rows
        ],
        "client_balance_events": {
            "total_events": int(balance_event_summary["total_events"] or 0),
            "total_delta": float(balance_event_summary["total_delta"] or 0),
            "first_event_at": balance_event_summary["first_event_at"].isoformat() if balance_event_summary["first_event_at"] else None,
            "last_event_at": balance_event_summary["last_event_at"].isoformat() if balance_event_summary["last_event_at"] else None,
            "events_after_cutoff": int(balance_event_summary["events_after_cutoff"] or 0),
            "delta_after_cutoff": float(balance_event_summary["delta_after_cutoff"] or 0),
        },
        "legacy_credit_du": {
            "total_rows": int(credit_due_summary["total_rows"] or 0),
            "total_credit_used": float(credit_due_summary["total_credit_used"] or 0),
            "total_credit_repaid": float(credit_due_summary["total_credit_repaid"] or 0),
            "net_credit_delta": float(credit_due_summary["net_credit_delta"] or 0),
            "rows_after_cutoff": int(credit_due_summary["rows_after_cutoff"] or 0),
        },
        "legacy_credit_payments": {
            "total_rows": int(credit_payment_summary["total_rows"] or 0),
            "total_amount": float(credit_payment_summary["total_amount"] or 0),
            "total_amount_eur": float(credit_payment_summary["total_amount_eur"] or 0),
            "first_payment_at": credit_payment_summary["first_payment_at"].isoformat() if credit_payment_summary["first_payment_at"] else None,
            "last_payment_at": credit_payment_summary["last_payment_at"].isoformat() if credit_payment_summary["last_payment_at"] else None,
            "rows_after_cutoff": int(credit_payment_summary["rows_after_cutoff"] or 0),
        },
        "legacy_sending_logs": {
            "total_rows": int(sending_summary["total_rows"] or 0),
            "total_amount": float(sending_summary["total_amount"] or 0),
            "total_amount_with_fees": float(sending_summary["total_amount_with_fees"] or 0),
            "total_sending_amount": float(sending_summary["total_sending_amount"] or 0),
            "total_receiving_amount": float(sending_summary["total_receiving_amount"] or 0),
            "total_charge": float(sending_summary["total_charge"] or 0),
            "first_sending_at": sending_summary["first_sending_at"].isoformat() if sending_summary["first_sending_at"] else None,
            "last_sending_at": sending_summary["last_sending_at"].isoformat() if sending_summary["last_sending_at"] else None,
            "rows_after_cutoff": int(sending_summary["rows_after_cutoff"] or 0),
        },
        "gap_summary": gap_summary,
        "timeline": [
            {
                "event_at": row["event_at"].isoformat() if row["event_at"] else None,
                "source": row["source"],
                "amount": float(row["amount"] or 0),
                "currency": row["currency"],
                "subtype": row["subtype"],
                "reference": row["reference"],
            }
            for row in timeline_rows
        ],
    }
