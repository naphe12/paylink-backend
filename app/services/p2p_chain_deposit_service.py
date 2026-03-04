from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.p2p_enums import TokenCode, TradeStatus
from app.models.p2p_trade import P2PTrade
from app.services.audit import audit
from app.services.p2p_trade_state import set_trade_status


async def upsert_chain_deposit(
    db: AsyncSession,
    *,
    tx_hash: str,
    log_index: int,
    network: str,
    token: str,
    to_address: str,
    amount: Decimal,
    block_number: int | None,
    block_timestamp: int | None,
    status: str,
    resolution: str,
    trade_id: str | None = None,
    matched_by: str | None = None,
    metadata: dict | None = None,
) -> None:
    block_dt = (
        datetime.fromtimestamp(int(block_timestamp), tz=timezone.utc)
        if block_timestamp is not None
        else None
    )
    matched_at = datetime.now(timezone.utc) if trade_id else None
    await db.execute(
        text(
            """
            INSERT INTO p2p.chain_deposits (
              trade_id, tx_hash, log_index, network, token, to_address, amount,
              block_number, block_timestamp, status, resolution, matched_at, matched_by, metadata, updated_at
            )
            VALUES (
              CAST(:trade_id AS uuid), :tx_hash, :log_index, :network, :token, :to_address, :amount,
              :block_number, :block_timestamp, :status, :resolution, :matched_at, CAST(:matched_by AS uuid), CAST(:metadata AS jsonb), now()
            )
            ON CONFLICT (network, token, tx_hash, log_index)
            DO UPDATE SET
              trade_id = EXCLUDED.trade_id,
              to_address = EXCLUDED.to_address,
              amount = EXCLUDED.amount,
              block_number = EXCLUDED.block_number,
              block_timestamp = EXCLUDED.block_timestamp,
              status = EXCLUDED.status,
              resolution = EXCLUDED.resolution,
              matched_at = EXCLUDED.matched_at,
              matched_by = EXCLUDED.matched_by,
              metadata = EXCLUDED.metadata,
              updated_at = now()
            """
        ),
        {
            "trade_id": trade_id,
            "tx_hash": tx_hash,
            "log_index": int(log_index),
            "network": str(network or "").upper(),
            "token": str(token or "").upper(),
            "to_address": str(to_address or "").lower(),
            "amount": Decimal(str(amount)),
            "block_number": block_number,
            "block_timestamp": block_dt,
            "status": status,
            "resolution": resolution,
            "matched_at": matched_at,
            "matched_by": matched_by,
            "metadata": json.dumps(metadata or {}),
        },
    )


async def get_chain_deposit_by_provider_event(
    db: AsyncSession,
    *,
    provider: str,
    provider_event_id: str,
) -> dict | None:
    row = (
        await db.execute(
            text(
                """
                SELECT
                  deposit_id,
                  trade_id,
                  tx_hash,
                  log_index,
                  status,
                  resolution,
                  token,
                  network,
                  metadata,
                  created_at,
                  updated_at
                FROM p2p.chain_deposits
                WHERE lower(COALESCE(metadata->>'provider', '')) = :provider
                  AND COALESCE(metadata->>'provider_event_id', '') = :provider_event_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {
                "provider": str(provider or "").strip().lower(),
                "provider_event_id": str(provider_event_id or "").strip(),
            },
        )
    ).mappings().first()
    if not row:
        return None

    metadata = row["metadata"] or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    return {
        "deposit_id": str(row["deposit_id"]),
        "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
        "tx_hash": row["tx_hash"],
        "log_index": int(row["log_index"] or 0),
        "status": row["status"],
        "resolution": row["resolution"],
        "token": row["token"],
        "network": row["network"],
        "metadata": metadata,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def _suggest_trade_candidates(
    db: AsyncSession,
    *,
    token: str,
    to_address: str,
    amount: float | None,
    metadata: dict | None,
) -> list[dict]:
    normalized_token = str(token or "").upper()
    normalized_address = str(to_address or "").lower()
    ref = str((metadata or {}).get("escrow_deposit_ref") or "").strip().upper()
    token_code = TokenCode(normalized_token)

    candidates: list[P2PTrade]
    if ref:
        stmt = select(P2PTrade).where(
            func.upper(P2PTrade.escrow_deposit_ref) == ref,
            P2PTrade.status == TradeStatus.AWAITING_CRYPTO,
            P2PTrade.token == token_code,
        )
        candidates = list((await db.execute(stmt.order_by(P2PTrade.created_at.asc()))).scalars().all())
    else:
        stmt = select(P2PTrade).where(
            func.lower(P2PTrade.escrow_deposit_addr) == normalized_address,
            P2PTrade.status == TradeStatus.AWAITING_CRYPTO,
            P2PTrade.token == token_code,
        )
        candidates = list((await db.execute(stmt.order_by(P2PTrade.created_at.asc()))).scalars().all())

    amount_decimal = Decimal(str(amount)) if amount is not None else None
    suggestions = []
    for trade in candidates[:5]:
        expected_amount = Decimal(str(trade.token_amount or 0))
        exact_amount = amount_decimal is not None and expected_amount.quantize(Decimal("0.000001")) == amount_decimal.quantize(Decimal("0.000001"))
        amount_delta = None
        if amount_decimal is not None:
            amount_delta = float((expected_amount - amount_decimal).copy_abs())
        ref_match = bool(ref and trade.escrow_deposit_ref and str(trade.escrow_deposit_ref).upper() == ref)
        match_reason = "reference_match" if ref_match else "exact_amount_match" if exact_amount else "shared_address_candidate"
        suggestions.append(
            {
                "trade_id": str(trade.trade_id),
                "escrow_deposit_ref": trade.escrow_deposit_ref,
                "escrow_provider": trade.escrow_provider,
                "escrow_deposit_addr": trade.escrow_deposit_addr,
                "token": str(getattr(trade.token, "value", trade.token)),
                "token_amount": float(expected_amount),
                "status": str(getattr(trade.status, "value", trade.status)),
                "exact_amount_match": exact_amount,
                "match_reason": match_reason,
                "amount_delta": amount_delta,
                "created_at": trade.created_at,
                "expires_at": trade.expires_at,
                "score": 100 if ref_match else 80 if exact_amount else 50,
            }
        )
    return suggestions


async def list_chain_deposits(
    db: AsyncSession,
    status: str | None = None,
    query_text: str | None = None,
    token: str | None = None,
    source: str | None = None,
    provider: str | None = None,
    assignment_mode: str | None = None,
    sort_by: str | None = None,
    score_min: int | None = None,
) -> list[dict]:
    query = """
        SELECT
          d.deposit_id,
          d.trade_id,
          d.tx_hash,
          d.log_index,
          d.network,
          d.token,
          d.to_address,
          d.amount,
          d.block_number,
          d.block_timestamp,
          d.status,
          d.resolution,
          d.matched_at,
          d.matched_by,
          d.metadata,
          d.created_at,
          d.updated_at,
          t.status::text AS trade_status
        FROM p2p.chain_deposits d
        LEFT JOIN p2p.trades t ON t.trade_id = d.trade_id
    """
    params = {}
    where = []
    if status:
        where.append("upper(d.status) = :status")
        params["status"] = str(status).upper()
    if query_text:
        where.append(
            """
            (
              COALESCE(d.tx_hash, '') ILIKE :pattern
              OR COALESCE(d.to_address, '') ILIKE :pattern
              OR COALESCE(CAST(d.trade_id AS text), '') ILIKE :pattern
              OR COALESCE(CAST(d.deposit_id AS text), '') ILIKE :pattern
              OR COALESCE(CAST(d.metadata->>'escrow_deposit_ref' AS text), '') ILIKE :pattern
              OR COALESCE(CAST(d.metadata->>'from_address' AS text), '') ILIKE :pattern
              OR COALESCE(CAST(d.metadata->>'source_ref' AS text), '') ILIKE :pattern
              OR COALESCE(CAST(d.metadata->>'provider' AS text), '') ILIKE :pattern
              OR COALESCE(CAST(d.metadata->>'provider_event_id' AS text), '') ILIKE :pattern
            )
            """
        )
        params["pattern"] = f"%{query_text.strip()}%"
    if token:
        where.append("upper(d.token) = :token")
        params["token"] = str(token).upper()
    if source:
        where.append("upper(COALESCE(d.metadata->>'source', 'watcher')) = :source")
        params["source"] = str(source).upper()
    if provider:
        where.append("upper(COALESCE(d.metadata->>'provider', '')) = :provider")
        params["provider"] = str(provider).upper()
    if assignment_mode:
        normalized_mode = str(assignment_mode).strip().lower()
        if normalized_mode == "auto":
            where.append("lower(COALESCE(d.resolution, '')) = 'auto_assignment'")
        elif normalized_mode == "manual":
            where.append("lower(COALESCE(d.resolution, '')) = 'manual_assignment'")
    if where:
        query += " WHERE " + " AND ".join(where)
    sort_key = str(sort_by or "recent").strip().lower()
    if sort_key == "oldest":
        query += " ORDER BY d.created_at ASC"
    elif sort_key == "amount_desc":
        query += " ORDER BY d.amount DESC, d.created_at DESC"
    else:
        query += " ORDER BY d.created_at DESC"
    rows = (await db.execute(text(query), params)).mappings().all()
    items = []
    for row in rows:
        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        suggestions = await _suggest_trade_candidates(
            db,
            token=row["token"],
            to_address=row["to_address"],
            amount=float(row["amount"]) if row["amount"] is not None else None,
            metadata=metadata,
        )
        items.append(
            {
                "deposit_id": str(row["deposit_id"]),
                "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
                "tx_hash": row["tx_hash"],
                "log_index": row["log_index"],
                "network": row["network"],
                "token": row["token"],
                "to_address": row["to_address"],
                "amount": float(row["amount"]) if row["amount"] is not None else None,
                "block_number": row["block_number"],
                "block_timestamp": row["block_timestamp"],
                "status": row["status"],
                "resolution": row["resolution"],
                "matched_at": row["matched_at"],
                "matched_by": str(row["matched_by"]) if row["matched_by"] else None,
                "metadata": metadata,
                "escrow_deposit_ref": metadata.get("escrow_deposit_ref"),
                "from_address": metadata.get("from_address"),
                "confirmations": metadata.get("confirmations"),
                "chain_id": metadata.get("chain_id"),
                "source": metadata.get("source"),
                "source_ref": metadata.get("source_ref"),
                "provider": metadata.get("provider"),
                "provider_event_id": metadata.get("provider_event_id"),
                "suggested_trades": suggestions,
                "suggestion_count": len(suggestions),
                "best_suggested_trade": suggestions[0] if suggestions else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "trade_status": row["trade_status"],
            }
        )
    min_score = int(score_min or 0)
    if min_score > 0:
        items = [
            item
            for item in items
            if int((item.get("best_suggested_trade") or {}).get("score") or 0) >= min_score
        ]
    if sort_key == "best_match":
        items.sort(
            key=lambda item: (
                -int((item.get("best_suggested_trade") or {}).get("score") or 0),
                item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
    elif sort_key == "most_ambiguous":
        items.sort(
            key=lambda item: (
                -int(item.get("suggestion_count") or 0),
                -int((item.get("best_suggested_trade") or {}).get("score") or 0),
            ),
        )
    return items


async def get_chain_deposit_stats(db: AsyncSession) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*)::int AS total,
                  COUNT(*) FILTER (WHERE upper(status) = 'MATCHED')::int AS matched,
                  COUNT(*) FILTER (WHERE upper(status) = 'UNMATCHED')::int AS unmatched,
                  COUNT(*) FILTER (WHERE upper(status) = 'AMBIGUOUS')::int AS ambiguous,
                  COUNT(*) FILTER (WHERE lower(COALESCE(resolution, '')) = 'auto_assignment')::int AS auto,
                  COUNT(*) FILTER (WHERE lower(COALESCE(resolution, '')) = 'manual_assignment')::int AS manual,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDC')::int AS usdc_count,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDT')::int AS usdt_count,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDC' AND upper(status) = 'MATCHED')::int AS usdc_matched,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDC' AND upper(status) = 'AMBIGUOUS')::int AS usdc_ambiguous,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDC' AND upper(status) = 'UNMATCHED')::int AS usdc_unmatched,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDT' AND upper(status) = 'MATCHED')::int AS usdt_matched,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDT' AND upper(status) = 'AMBIGUOUS')::int AS usdt_ambiguous,
                  COUNT(*) FILTER (WHERE upper(token) = 'USDT' AND upper(status) = 'UNMATCHED')::int AS usdt_unmatched
                FROM p2p.chain_deposits
                """
            )
        )
    ).mappings().first()
    provider_rows = (
        await db.execute(
            text(
                """
                SELECT
                  TRIM(COALESCE(metadata->>'provider', '')) AS provider,
                  COUNT(*)::int AS total,
                  COUNT(*) FILTER (WHERE upper(status) = 'MATCHED')::int AS matched,
                  COUNT(*) FILTER (WHERE upper(status) = 'AMBIGUOUS')::int AS ambiguous,
                  COUNT(*) FILTER (WHERE upper(status) = 'UNMATCHED')::int AS unmatched
                FROM p2p.chain_deposits
                WHERE TRIM(COALESCE(metadata->>'provider', '')) <> ''
                GROUP BY TRIM(COALESCE(metadata->>'provider', ''))
                ORDER BY total DESC, provider ASC
                """
            )
        )
    ).mappings().all()
    return {
        "total": int((row or {}).get("total") or 0),
        "matched": int((row or {}).get("matched") or 0),
        "unmatched": int((row or {}).get("unmatched") or 0),
        "ambiguous": int((row or {}).get("ambiguous") or 0),
        "auto": int((row or {}).get("auto") or 0),
        "manual": int((row or {}).get("manual") or 0),
        "by_token": {
            "USDC": {
                "total": int((row or {}).get("usdc_count") or 0),
                "matched": int((row or {}).get("usdc_matched") or 0),
                "ambiguous": int((row or {}).get("usdc_ambiguous") or 0),
                "unmatched": int((row or {}).get("usdc_unmatched") or 0),
            },
            "USDT": {
                "total": int((row or {}).get("usdt_count") or 0),
                "matched": int((row or {}).get("usdt_matched") or 0),
                "ambiguous": int((row or {}).get("usdt_ambiguous") or 0),
                "unmatched": int((row or {}).get("usdt_unmatched") or 0),
            },
        },
        "by_provider": [
            {
                "provider": str(item["provider"]),
                "total": int(item["total"] or 0),
                "matched": int(item["matched"] or 0),
                "ambiguous": int(item["ambiguous"] or 0),
                "unmatched": int(item["unmatched"] or 0),
            }
            for item in provider_rows
        ],
    }


async def get_chain_deposit_timeline(db: AsyncSession, deposit_id: str) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                  d.deposit_id,
                  d.trade_id,
                  d.tx_hash,
                  d.log_index,
                  d.network,
                  d.token,
                  d.to_address,
                  d.amount,
                  d.block_number,
                  d.block_timestamp,
                  d.status,
                  d.resolution,
                  d.matched_at,
                  d.matched_by,
                  d.metadata,
                  d.created_at,
                  d.updated_at,
                  t.status::text AS trade_status,
                  t.escrow_deposit_ref,
                  t.escrow_provider,
                  t.escrow_tx_hash,
                  t.escrow_lock_log_index,
                  t.escrow_locked_at
                FROM p2p.chain_deposits d
                LEFT JOIN p2p.trades t ON t.trade_id = d.trade_id
                WHERE d.deposit_id = CAST(:deposit_id AS uuid)
                """
            ),
            {"deposit_id": deposit_id},
        )
    ).mappings().first()
    if not row:
        raise ValueError("Deposit not found")

    metadata = row["metadata"] or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    timeline = [
        {
            "kind": "deposit_recorded",
            "at": row["created_at"],
            "title": f"Deposit {row['status']}",
            "details": {
                "resolution": row["resolution"],
                "tx_hash": row["tx_hash"],
                "log_index": row["log_index"],
                "network": row["network"],
                "token": row["token"],
                "amount": float(row["amount"]) if row["amount"] is not None else None,
                "to_address": row["to_address"],
                "escrow_deposit_ref": metadata.get("escrow_deposit_ref"),
                "provider": metadata.get("provider"),
                "provider_event_id": metadata.get("provider_event_id"),
                "source": metadata.get("source"),
                "source_ref": metadata.get("source_ref"),
            },
        }
    ]

    webhook_rows = (
        await db.execute(
            text(
                """
                SELECT id, event_type, status, payload, error, created_at
                FROM escrow.webhook_logs
                WHERE event_type = 'P2P_CHAIN_DEPOSIT'
                  AND tx_hash = :tx_hash
                ORDER BY created_at ASC
                """
            ),
            {"tx_hash": row["tx_hash"]},
        )
    ).mappings().all()
    for item in webhook_rows:
        payload = item["payload"] or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if str(payload.get("log_index", 0)) != str(row["log_index"]):
            continue
        timeline.append(
            {
                "kind": "webhook",
                "at": item["created_at"],
                "title": f"Webhook {item['status']}",
                "details": {
                    "log_id": item["id"],
                    "event_type": item["event_type"],
                    "error": item["error"],
                    "payload": payload,
                },
            }
        )

    audit_rows = (
        await db.execute(
            text(
                """
                SELECT id, created_at, actor_user_id, actor_role, action, entity_type, entity_id, after_state
                FROM paylink.audit_log
                WHERE (
                  entity_type = 'P2P_CHAIN_DEPOSIT'
                  AND CAST(entity_id AS text) = :deposit_id
                )
                OR (
                  action IN ('P2P_CHAIN_DEPOSIT_MANUAL_ASSIGN', 'P2P_CHAIN_DEPOSIT_AUTO_ASSIGN')
                  AND COALESCE(after_state->>'deposit_id', '') = :deposit_id
                )
                ORDER BY created_at ASC
                """
            ),
            {"deposit_id": deposit_id},
        )
    ).mappings().all()
    for item in audit_rows:
        after_state = item["after_state"] or {}
        if isinstance(after_state, str):
            try:
                after_state = json.loads(after_state)
            except Exception:
                after_state = {}
        timeline.append(
            {
                "kind": "audit",
                "at": item["created_at"],
                "title": (
                    "Assignation auto"
                    if str(after_state.get("assignment_mode") or "").lower() == "auto"
                    else "Assignation manuelle"
                    if str(after_state.get("assignment_mode") or "").lower() == "manual"
                    else item["action"]
                ),
                "details": {
                    "audit_id": item["id"],
                    "actor_user_id": str(item["actor_user_id"]) if item["actor_user_id"] else None,
                    "actor_role": item["actor_role"],
                    "entity_type": item["entity_type"],
                    "entity_id": str(item["entity_id"]) if item["entity_id"] else None,
                    "assignment_mode": after_state.get("assignment_mode"),
                    "after_state": after_state,
                },
            }
        )

    trade_history = []
    if row["trade_id"]:
        history_rows = (
            await db.execute(
                text(
                    """
                    SELECT history_id, created_at, old_status::text AS old_status, new_status::text AS new_status,
                           actor_user_id, actor_role, note
                    FROM p2p.trade_history
                    WHERE trade_id = CAST(:trade_id AS uuid)
                    ORDER BY created_at ASC
                    """
                ),
                {"trade_id": str(row["trade_id"])},
            )
        ).mappings().all()
        for item in history_rows:
            trade_history.append(
                {
                    "history_id": str(item["history_id"]),
                    "created_at": item["created_at"],
                    "old_status": item["old_status"],
                    "new_status": item["new_status"],
                    "actor_user_id": str(item["actor_user_id"]) if item["actor_user_id"] else None,
                    "actor_role": item["actor_role"],
                    "note": item["note"],
                }
            )
            timeline.append(
                {
                    "kind": "trade_status",
                    "at": item["created_at"],
                    "title": f"Trade -> {item['new_status']}",
                    "details": {
                        "old_status": item["old_status"],
                        "new_status": item["new_status"],
                        "actor_user_id": str(item["actor_user_id"]) if item["actor_user_id"] else None,
                        "actor_role": item["actor_role"],
                        "note": item["note"],
                    },
                }
            )

    timeline.sort(key=lambda item: item.get("at") or datetime.min.replace(tzinfo=timezone.utc))
    return {
        "deposit": {
            "deposit_id": str(row["deposit_id"]),
            "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
            "tx_hash": row["tx_hash"],
            "log_index": row["log_index"],
            "network": row["network"],
            "token": row["token"],
            "to_address": row["to_address"],
            "amount": float(row["amount"]) if row["amount"] is not None else None,
            "block_number": row["block_number"],
            "block_timestamp": row["block_timestamp"],
            "status": row["status"],
            "resolution": row["resolution"],
            "matched_at": row["matched_at"],
            "matched_by": str(row["matched_by"]) if row["matched_by"] else None,
            "metadata": metadata,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "trade_status": row["trade_status"],
            "escrow_deposit_ref": metadata.get("escrow_deposit_ref"),
            "provider": metadata.get("provider"),
            "provider_event_id": metadata.get("provider_event_id"),
            "source": metadata.get("source"),
            "source_ref": metadata.get("source_ref"),
            "escrow_provider": row["escrow_provider"],
            "escrow_tx_hash": row["escrow_tx_hash"],
            "escrow_lock_log_index": row["escrow_lock_log_index"],
            "escrow_locked_at": row["escrow_locked_at"],
        },
        "timeline": timeline,
        "trade_history": trade_history,
    }


async def assign_chain_deposit_to_trade(
    db: AsyncSession,
    *,
    deposit_id: str,
    trade_id: str,
    actor_user_id: str | None,
) -> dict:
    return await _assign_chain_deposit_to_trade(
        db,
        deposit_id=deposit_id,
        trade_id=trade_id,
        actor_user_id=actor_user_id,
        mode="manual",
    )


async def _assign_chain_deposit_to_trade(
    db: AsyncSession,
    *,
    deposit_id: str,
    trade_id: str,
    actor_user_id: str | None,
    mode: str,
) -> dict:
    deposit = (
        await db.execute(
            text(
                """
                SELECT deposit_id, trade_id, status, resolution, tx_hash, log_index, network, token, to_address, amount, block_timestamp, metadata
                FROM p2p.chain_deposits
                WHERE deposit_id = CAST(:deposit_id AS uuid)
                """
            ),
            {"deposit_id": deposit_id},
        )
    ).mappings().first()
    if not deposit:
        raise ValueError("Deposit not found")

    trade = await db.scalar(select(P2PTrade).where(P2PTrade.trade_id == trade_id))
    if not trade:
        raise ValueError("Trade not found")
    if deposit["trade_id"] and str(deposit["trade_id"]) == str(trade.trade_id):
        return {
            "status": "ALREADY_MATCHED",
            "deposit_id": deposit_id,
            "trade_id": trade_id,
            "tx_hash": deposit["tx_hash"],
        }
    if deposit["trade_id"] and str(deposit["trade_id"]) != str(trade.trade_id):
        raise ValueError("Deposit is already assigned to another trade")
    if trade.status != TradeStatus.AWAITING_CRYPTO:
        raise ValueError(f"Trade not in AWAITING_CRYPTO (current={trade.status.value})")
    if str(getattr(trade.token, "value", trade.token)).upper() != str(deposit["token"]).upper():
        raise ValueError("Deposit token does not match trade token")
    deposit_ref = str((deposit["metadata"] or {}).get("escrow_deposit_ref") or "").strip()
    if deposit_ref and str(trade.escrow_deposit_ref or "").strip().upper() != deposit_ref.upper():
        raise ValueError("Deposit reference does not match trade escrow reference")
    if str(trade.escrow_deposit_addr or "").lower() != str(deposit["to_address"]).lower():
        raise ValueError("Deposit address does not match trade escrow address")
    if trade.escrow_tx_hash:
        raise ValueError("Trade already has an escrow tx hash")

    trade.escrow_tx_hash = deposit["tx_hash"]
    trade.escrow_lock_log_index = int(deposit["log_index"] or 0)
    trade.escrow_locked_at = deposit["block_timestamp"] or datetime.now(timezone.utc)
    is_auto = str(mode).lower() == "auto"
    assignment_note = "Auto chain deposit assignment" if is_auto else "Manual chain deposit assignment"
    resolution = "auto_assignment" if is_auto else "manual_assignment"
    audit_action = "P2P_CHAIN_DEPOSIT_AUTO_ASSIGN" if is_auto else "P2P_CHAIN_DEPOSIT_MANUAL_ASSIGN"
    await set_trade_status(
        db,
        trade,
        TradeStatus.CRYPTO_LOCKED,
        actor_user_id=actor_user_id,
        actor_role="ADMIN",
        note=assignment_note,
    )

    await db.execute(
        text(
            """
            UPDATE p2p.chain_deposits
            SET
              trade_id = CAST(:trade_id AS uuid),
              status = 'MATCHED',
              resolution = :resolution,
              matched_at = now(),
              matched_by = CAST(:matched_by AS uuid),
              updated_at = now()
            WHERE deposit_id = CAST(:deposit_id AS uuid)
            """
        ),
        {
            "deposit_id": deposit_id,
            "trade_id": trade_id,
            "matched_by": actor_user_id,
            "resolution": resolution,
        },
    )
    await audit(
        db,
        actor_user_id=actor_user_id,
        actor_role="ADMIN",
        action=audit_action,
        entity_type="P2P_CHAIN_DEPOSIT",
        entity_id=deposit_id,
        metadata={
            "assignment_mode": "auto" if is_auto else "manual",
            "deposit_id": deposit_id,
            "previous_trade_id": str(deposit["trade_id"]) if deposit["trade_id"] else None,
            "previous_status": deposit["status"],
            "previous_resolution": deposit["resolution"],
            "assigned_trade_id": trade_id,
            "tx_hash": deposit["tx_hash"],
            "log_index": int(deposit["log_index"] or 0),
            "token": deposit["token"],
            "amount": str(deposit["amount"]),
            "to_address": deposit["to_address"],
            "escrow_deposit_ref": deposit_ref or None,
        },
    )
    await db.commit()
    return {
        "status": "OK",
        "deposit_id": deposit_id,
        "trade_id": trade_id,
        "tx_hash": deposit["tx_hash"],
    }


async def auto_assign_chain_deposit(
    db: AsyncSession,
    *,
    deposit_id: str,
    actor_user_id: str | None,
) -> dict:
    deposit = (
        await db.execute(
            text(
                """
                SELECT deposit_id, status, token, to_address, amount, metadata
                FROM p2p.chain_deposits
                WHERE deposit_id = CAST(:deposit_id AS uuid)
                """
            ),
            {"deposit_id": deposit_id},
        )
    ).mappings().first()
    if not deposit:
        raise ValueError("Deposit not found")
    if str(deposit["status"] or "").upper() == "MATCHED":
        raise ValueError("Deposit already matched")

    metadata = deposit["metadata"] or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    suggestions = await _suggest_trade_candidates(
        db,
        token=deposit["token"],
        to_address=deposit["to_address"],
        amount=float(deposit["amount"]) if deposit["amount"] is not None else None,
        metadata=metadata,
    )
    best = suggestions[0] if suggestions else None
    threshold = int(settings.P2P_CHAIN_AUTO_ASSIGN_MIN_SCORE or 90)
    score = int((best or {}).get("score") or 0)
    if not best or not best.get("trade_id") or score < threshold:
        raise ValueError(
            f"No candidate reached auto-assignment threshold (score={score}, threshold={threshold})"
        )

    result = await _assign_chain_deposit_to_trade(
        db,
        deposit_id=deposit_id,
        trade_id=str(best["trade_id"]),
        actor_user_id=actor_user_id,
        mode="auto",
    )
    result["auto_assigned"] = True
    result["score"] = score
    result["threshold"] = threshold
    return result
