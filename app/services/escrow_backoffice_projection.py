from app.schemas.dispute_codes import (
    ESCROW_REFUND_REASON_CODE_LABELS,
    ESCROW_REFUND_RESOLUTION_CODE_LABELS,
    PROOF_TYPE_LABELS,
)


def label_for_code(value: str | None, labels: dict[str, str]) -> str | None:
    if not value:
        return None
    return labels.get(value, value)


def order_row_to_dict(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "status": r["status"],
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "user_name": r.get("user_name"),
        "depositor_user_id": str(r["user_id"]) if r["user_id"] else None,
        "depositor_name": r.get("user_name"),
        "trader_id": str(r["trader_id"]) if r["trader_id"] else None,
        "trader_name": r.get("trader_name"),
        "payout_operator_user_id": str(r["trader_id"]) if r["trader_id"] else None,
        "payout_operator_name": r.get("trader_name"),
        "usdc_expected": float(r["usdc_expected"]) if r["usdc_expected"] is not None else None,
        "usdc_received": float(r["usdc_received"]) if r["usdc_received"] is not None else None,
        "usdt_target": float(r["usdt_target"]) if r["usdt_target"] is not None else None,
        "usdt_received": float(r["usdt_received"]) if r["usdt_received"] is not None else None,
        "bif_target": float(r["bif_target"]) if r["bif_target"] is not None else None,
        "bif_paid": float(r["bif_paid"]) if r["bif_paid"] is not None else None,
        "risk_score": int(r["risk_score"]) if r["risk_score"] is not None else 0,
        "flags": list(r.get("flags") or []),
        "deposit_network": r.get("deposit_network"),
        "deposit_address": r.get("deposit_address"),
        "deposit_tx_hash": r.get("deposit_tx_hash"),
        "payout_method": r.get("payout_method"),
        "payout_provider": r.get("payout_provider"),
        "payout_account_name": r.get("payout_account_name"),
        "payout_account_number": r.get("payout_account_number"),
        "payout_beneficiary_name": r.get("payout_account_name"),
        "payout_beneficiary_account": r.get("payout_account_number"),
        "payout_reference": r.get("payout_reference"),
        "funded_at": r.get("funded_at"),
        "swapped_at": r.get("swapped_at"),
        "payout_initiated_at": r.get("payout_initiated_at"),
        "paid_out_at": r.get("paid_out_at"),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }


ESCROW_AUDIT_CSV_HEADERS = [
    "id",
    "status",
    "user_id",
    "user_name",
    "depositor_user_id",
    "depositor_name",
    "trader_id",
    "trader_name",
    "payout_operator_user_id",
    "payout_operator_name",
    "usdc_expected",
    "usdc_received",
    "usdt_target",
    "usdt_received",
    "bif_target",
    "bif_paid",
    "risk_score",
    "deposit_network",
    "deposit_address",
    "deposit_tx_hash",
    "payout_provider",
    "payout_account_name",
    "payout_account_number",
    "payout_beneficiary_name",
    "payout_beneficiary_account",
    "payout_reference",
    "funded_at",
    "swapped_at",
    "payout_initiated_at",
    "paid_out_at",
    "created_at",
    "updated_at",
]


def serialize_escrow_order_csv_row(row) -> list:
    return list(row)


def serialize_refund_audit_item(row, after_state: dict) -> dict:
    return {
        "id": str(row["id"]),
        "action": row["action"],
        "actor_user_id": str(row["actor_user_id"]) if row.get("actor_user_id") else None,
        "actor_role": row.get("actor_role"),
        "created_at": row.get("created_at"),
        "status": after_state.get("status"),
        "reason": after_state.get("reason"),
        "reason_code": after_state.get("reason_code"),
        "reason_code_label": label_for_code(
            after_state.get("reason_code"),
            ESCROW_REFUND_REASON_CODE_LABELS,
        ),
        "resolution": after_state.get("resolution"),
        "resolution_code": after_state.get("resolution_code"),
        "resolution_code_label": label_for_code(
            after_state.get("resolution_code"),
            ESCROW_REFUND_RESOLUTION_CODE_LABELS,
        ),
        "proof_type": after_state.get("proof_type"),
        "proof_type_label": label_for_code(
            after_state.get("proof_type"),
            PROOF_TYPE_LABELS,
        ),
        "proof_ref": after_state.get("proof_ref"),
        "step_up_method": after_state.get("step_up_method"),
    }
