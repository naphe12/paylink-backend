from app.schemas.dispute_codes import (
    P2P_DISPUTE_REASON_CODE_LABELS,
    P2P_DISPUTE_RESOLUTION_CODE_LABELS,
    PROOF_TYPE_LABELS,
)


def label_for_code(value: str | None, labels: dict[str, str]) -> str | None:
    if not value:
        return None
    return labels.get(value, value)


def serialize_admin_trade_summary(row) -> dict:
    return {
        "trade_id": str(row["trade_id"]),
        "offer_id": str(row["offer_id"]) if row["offer_id"] else None,
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "token": row["token"],
        "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
        "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
        "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
        "payment_method": row["payment_method"],
        "risk_score": int(row["risk_score"]) if row["risk_score"] is not None else 0,
        "flags": list(row["flags"] or []),
        "escrow_deposit_ref": row["escrow_deposit_ref"],
        "escrow_provider": row["escrow_provider"],
        "escrow_tx_hash": row["escrow_tx_hash"],
        "escrow_lock_log_index": row["escrow_lock_log_index"],
        "fiat_sent_at": row["fiat_sent_at"],
        "fiat_confirmed_at": row["fiat_confirmed_at"],
        "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
        "buyer_name": row["buyer_name"],
        "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
        "seller_name": row["seller_name"],
        "offer_side": row["offer_side"],
        "offer_owner_user_id": str(row["offer_owner_id"]) if row["offer_owner_id"] else None,
        "offer_owner_name": row["offer_owner_name"],
        "disputes_count": int(row["disputes_count"] or 0),
    }


def serialize_admin_trade_detail(row) -> dict:
    return {
        "trade_id": str(row["trade_id"]),
        "offer_id": str(row["offer_id"]) if row["offer_id"] else None,
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "token": row["token"],
        "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
        "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
        "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
        "payment_method": row["payment_method"],
        "risk_score": int(row["risk_score"]) if row["risk_score"] is not None else 0,
        "flags": list(row["flags"] or []),
        "escrow_network": row["escrow_network"],
        "escrow_deposit_addr": row["escrow_deposit_addr"],
        "escrow_deposit_ref": row["escrow_deposit_ref"],
        "escrow_provider": row["escrow_provider"],
        "escrow_tx_hash": row["escrow_tx_hash"],
        "escrow_lock_log_index": row["escrow_lock_log_index"],
        "escrow_locked_at": row["escrow_locked_at"],
        "fiat_sent_at": row["fiat_sent_at"],
        "fiat_confirmed_at": row["fiat_confirmed_at"],
        "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
        "buyer_name": row["buyer_name"],
        "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
        "seller_name": row["seller_name"],
        "offer_side": row["offer_side"],
        "offer_owner_user_id": str(row["offer_owner_id"]) if row["offer_owner_id"] else None,
        "offer_owner_name": row["offer_owner_name"],
        "disputes_count": int(row["disputes_count"] or 0),
    }


ADMIN_TRADE_CSV_HEADERS = [
    "trade_id",
    "offer_id",
    "status",
    "created_at",
    "updated_at",
    "expires_at",
    "buyer_user_id",
    "buyer_name",
    "seller_user_id",
    "seller_name",
    "offer_owner_user_id",
    "offer_owner_name",
    "offer_side",
    "payment_method",
    "token",
    "token_amount",
    "price_bif_per_usd",
    "bif_amount",
    "risk_score",
    "disputes_count",
    "escrow_deposit_ref",
    "escrow_provider",
    "escrow_tx_hash",
    "escrow_lock_log_index",
    "fiat_sent_at",
    "fiat_confirmed_at",
    "flags",
]


def serialize_admin_trade_csv_row(item: dict) -> list:
    return [
        item.get("trade_id"),
        item.get("offer_id"),
        item.get("status"),
        item.get("created_at"),
        item.get("updated_at"),
        item.get("expires_at"),
        item.get("buyer_user_id"),
        item.get("buyer_name"),
        item.get("seller_user_id"),
        item.get("seller_name"),
        item.get("offer_owner_user_id"),
        item.get("offer_owner_name"),
        item.get("offer_side"),
        item.get("payment_method"),
        item.get("token"),
        item.get("token_amount"),
        item.get("price_bif_per_usd"),
        item.get("bif_amount"),
        item.get("risk_score"),
        item.get("disputes_count"),
        item.get("escrow_deposit_ref"),
        item.get("escrow_provider"),
        item.get("escrow_tx_hash"),
        item.get("escrow_lock_log_index"),
        item.get("fiat_sent_at"),
        item.get("fiat_confirmed_at"),
        "|".join([str(flag) for flag in list(item.get("flags") or [])]),
    ]


def serialize_p2p_dispute_row(row) -> dict:
    return {
        "dispute_id": str(row["dispute_id"]),
        "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
        "tx_id": str(row["tx_id"]) if row["tx_id"] else None,
        "status": row["status"],
        "reason": row["reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
        "opened_by_user_id": str(row["opened_by_user_id"]) if row["opened_by_user_id"] else None,
        "opened_by_name": row["opened_by_name"],
        "resolved_by_user_id": str(row["resolved_by_user_id"]) if row["resolved_by_user_id"] else None,
        "resolved_by_name": row["resolved_by_name"],
        "resolution": row["resolution"],
        "resolution_code": None,
        "reason_code": None,
        "proof_type": None,
        "proof_ref": None,
        "evidence_url": row["evidence_url"],
        "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
        "buyer_name": row["buyer_name"],
        "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
        "seller_name": row["seller_name"],
        "token": row["token"],
        "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
        "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
        "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
        "payment_method": row["payment_method"],
        "trade_status": row["trade_status"],
        "tx_amount": float(row["tx_amount"]) if row["tx_amount"] is not None else None,
        "tx_currency": row["tx_currency"],
        "source": "p2p",
    }


def serialize_legacy_dispute_row(row) -> dict:
    return {
        "dispute_id": str(row["dispute_id"]),
        "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
        "tx_id": str(row["tx_id"]) if row["tx_id"] else None,
        "status": row["status"],
        "reason": row["reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
        "opened_by_user_id": str(row["opened_by_user_id"]) if row["opened_by_user_id"] else None,
        "opened_by_name": row["opened_by_name"],
        "resolved_by_user_id": str(row["resolved_by_user_id"]) if row["resolved_by_user_id"] else None,
        "resolved_by_name": row["resolved_by_name"],
        "resolution": row["resolution"],
        "resolution_code": None,
        "reason_code": None,
        "proof_type": None,
        "proof_ref": None,
        "evidence_url": row["evidence_url"],
        "buyer_user_id": str(row["buyer_id"]) if row["buyer_id"] else None,
        "buyer_name": row["buyer_name"],
        "seller_user_id": str(row["seller_id"]) if row["seller_id"] else None,
        "seller_name": row["seller_name"],
        "token": row["token"],
        "token_amount": float(row["token_amount"]) if row["token_amount"] is not None else None,
        "price_bif_per_usd": float(row["price_bif_per_usd"]) if row["price_bif_per_usd"] is not None else None,
        "bif_amount": float(row["bif_amount"]) if row["bif_amount"] is not None else None,
        "payment_method": row["payment_method"],
        "trade_status": row["trade_status"],
        "tx_amount": float(row["tx_amount"]) if row["tx_amount"] is not None else None,
        "tx_currency": row["tx_currency"],
        "source": "paylink",
    }


ADMIN_DISPUTE_CSV_HEADERS = [
    "dispute_id",
    "source",
    "trade_id",
    "tx_id",
    "status",
    "trade_status",
    "created_at",
    "updated_at",
    "resolved_at",
    "opened_by_name",
    "resolved_by_name",
    "buyer_name",
    "seller_name",
    "token",
    "token_amount",
    "price_bif_per_usd",
    "bif_amount",
    "tx_amount",
    "tx_currency",
    "payment_method",
    "reason",
    "reason_code",
    "reason_code_label",
    "resolution",
    "resolution_code",
    "resolution_code_label",
    "proof_type",
    "proof_type_label",
    "proof_ref",
    "evidence_url",
]


def serialize_admin_dispute_csv_row(item: dict) -> list:
    return [
        item.get("dispute_id"),
        item.get("source"),
        item.get("trade_id"),
        item.get("tx_id"),
        item.get("status"),
        item.get("trade_status"),
        item.get("created_at"),
        item.get("updated_at"),
        item.get("resolved_at"),
        item.get("opened_by_name") or item.get("opened_by_user_id"),
        item.get("resolved_by_name") or item.get("resolved_by_user_id"),
        item.get("buyer_name") or item.get("buyer_user_id"),
        item.get("seller_name") or item.get("seller_user_id"),
        item.get("token"),
        item.get("token_amount"),
        item.get("price_bif_per_usd"),
        item.get("bif_amount"),
        item.get("tx_amount"),
        item.get("tx_currency"),
        item.get("payment_method"),
        item.get("reason"),
        item.get("reason_code"),
        item.get("reason_code_label"),
        item.get("resolution"),
        item.get("resolution_code"),
        item.get("resolution_code_label"),
        item.get("proof_type"),
        item.get("proof_type_label"),
        item.get("proof_ref"),
        item.get("evidence_url"),
    ]


ADMIN_CHAIN_DEPOSIT_CSV_HEADERS = [
    "deposit_id",
    "status",
    "resolution",
    "network",
    "token",
    "amount",
    "tx_hash",
    "log_index",
    "to_address",
    "from_address",
    "escrow_deposit_ref",
    "trade_id",
    "trade_status",
    "matched_at",
    "matched_by",
    "block_number",
    "confirmations",
    "chain_id",
    "source",
    "source_ref",
    "provider",
    "provider_event_id",
    "suggestion_count",
    "suggested_trade_ids",
    "created_at",
    "updated_at",
]


def serialize_admin_chain_deposit_csv_row(item: dict) -> list:
    return [
        item.get("deposit_id"),
        item.get("status"),
        item.get("resolution"),
        item.get("network"),
        item.get("token"),
        item.get("amount"),
        item.get("tx_hash"),
        item.get("log_index"),
        item.get("to_address"),
        item.get("from_address"),
        item.get("escrow_deposit_ref"),
        item.get("trade_id"),
        item.get("trade_status"),
        item.get("matched_at"),
        item.get("matched_by"),
        item.get("block_number"),
        item.get("confirmations"),
        item.get("chain_id"),
        item.get("source"),
        item.get("source_ref"),
        item.get("provider"),
        item.get("provider_event_id"),
        item.get("suggestion_count"),
        "|".join([str(s.get("trade_id")) for s in list(item.get("suggested_trades") or [])]),
        item.get("created_at"),
        item.get("updated_at"),
    ]


def enrich_dispute_labels(item: dict) -> dict:
    source = str(item.get("source", "")).lower()
    if source != "p2p":
        item.setdefault("reason_code_label", None)
        item.setdefault("resolution_code_label", None)
        item.setdefault("proof_type_label", None)
        return item

    item["reason_code_label"] = label_for_code(
        item.get("reason_code"),
        P2P_DISPUTE_REASON_CODE_LABELS,
    )
    item["resolution_code_label"] = label_for_code(
        item.get("resolution_code"),
        P2P_DISPUTE_RESOLUTION_CODE_LABELS,
    )
    item["proof_type_label"] = label_for_code(
        item.get("proof_type"),
        PROOF_TYPE_LABELS,
    )
    return item


def enrich_timeline_item_labels(item: dict) -> dict:
    item["reason_code_label"] = label_for_code(
        item.get("reason_code"),
        P2P_DISPUTE_REASON_CODE_LABELS,
    )
    item["resolution_code_label"] = label_for_code(
        item.get("resolution_code"),
        P2P_DISPUTE_RESOLUTION_CODE_LABELS,
    )
    item["proof_type_label"] = label_for_code(
        item.get("proof_type"),
        PROOF_TYPE_LABELS,
    )
    return item


def serialize_p2p_dispute_opened_timeline_row(row, after_state: dict) -> dict:
    return {
        "id": str(row["id"]),
        "action": row["action"],
        "actor_user_id": str(row["actor_user_id"]) if row.get("actor_user_id") else None,
        "actor_role": row.get("actor_role"),
        "created_at": row.get("created_at"),
        "trade_status": after_state.get("trade_status"),
        "dispute_status": after_state.get("dispute_status"),
        "reason": after_state.get("reason"),
        "reason_code": after_state.get("reason_code"),
        "proof_type": after_state.get("proof_type"),
        "proof_ref": after_state.get("proof_ref"),
        "step_up_method": after_state.get("step_up_method"),
    }


def serialize_p2p_dispute_resolved_timeline_row(row, before_state: dict, after_state: dict) -> dict:
    return {
        "id": str(row["id"]),
        "action": row["action"],
        "actor_user_id": str(row["actor_user_id"]) if row.get("actor_user_id") else None,
        "actor_role": row.get("actor_role"),
        "created_at": row.get("created_at"),
        "trade_status_before": before_state.get("trade_status"),
        "trade_status": after_state.get("trade_status"),
        "dispute_status_before": before_state.get("dispute_status"),
        "dispute_status": after_state.get("dispute_status"),
        "outcome": after_state.get("outcome"),
        "resolution": after_state.get("resolution"),
        "resolution_code": after_state.get("resolution_code"),
        "proof_type": after_state.get("proof_type"),
        "proof_ref": after_state.get("proof_ref"),
        "step_up_method": after_state.get("step_up_method"),
    }


def serialize_legacy_dispute_timeline_item(
    *,
    item_id: str,
    action: str,
    actor_user_id: str | None,
    actor_role: str,
    created_at,
    dispute_status: str | None,
    reason: str | None = None,
    resolution: str | None = None,
    evidence_url: str | None = None,
) -> dict:
    return {
        "id": item_id,
        "action": action,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "created_at": created_at,
        "dispute_status": dispute_status,
        "reason": reason,
        "resolution": resolution,
        "evidence_url": evidence_url,
        "reason_code_label": None,
        "resolution_code_label": None,
        "proof_type_label": None,
    }
