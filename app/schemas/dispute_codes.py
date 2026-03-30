from typing import Literal, TypeAlias


PROOF_TYPE_VALUES = (
    "screenshot",
    "pdf",
    "receipt_id",
    "bank_reference",
    "mobile_money_reference",
    "other",
)

ESCROW_REFUND_REASON_CODE_VALUES = (
    "payout_failed",
    "customer_cancelled",
    "compliance_hold",
    "operator_error",
    "other",
)

ESCROW_REFUND_RESOLUTION_CODE_VALUES = (
    "refund_approved",
    "refund_rejected",
    "manual_operator_decision",
    "other",
)

P2P_DISPUTE_REASON_CODE_VALUES = (
    "payment_not_received",
    "wrong_amount",
    "fraud_suspected",
    "timeout",
    "other",
)

P2P_DISPUTE_RESOLUTION_CODE_VALUES = (
    "payment_proof_validated",
    "payment_not_proven",
    "seller_confirmed_non_receipt",
    "manual_operator_decision",
    "other",
)

ProofTypeCode: TypeAlias = Literal[
    "screenshot",
    "pdf",
    "receipt_id",
    "bank_reference",
    "mobile_money_reference",
    "other",
]

EscrowRefundReasonCode: TypeAlias = Literal[
    "payout_failed",
    "customer_cancelled",
    "compliance_hold",
    "operator_error",
    "other",
]

EscrowRefundResolutionCode: TypeAlias = Literal[
    "refund_approved",
    "refund_rejected",
    "manual_operator_decision",
    "other",
]

P2PDisputeReasonCode: TypeAlias = Literal[
    "payment_not_received",
    "wrong_amount",
    "fraud_suspected",
    "timeout",
    "other",
]

P2PDisputeResolutionCode: TypeAlias = Literal[
    "payment_proof_validated",
    "payment_not_proven",
    "seller_confirmed_non_receipt",
    "manual_operator_decision",
    "other",
]

PROOF_TYPE_LABELS = {
    "screenshot": "Screenshot",
    "pdf": "PDF",
    "receipt_id": "Receipt ID",
    "bank_reference": "Bank reference",
    "mobile_money_reference": "Mobile money reference",
    "other": "Other",
}

ESCROW_REFUND_REASON_CODE_LABELS = {
    "payout_failed": "Payout failed",
    "customer_cancelled": "Customer cancelled",
    "compliance_hold": "Compliance hold",
    "operator_error": "Operator error",
    "other": "Other",
}

ESCROW_REFUND_RESOLUTION_CODE_LABELS = {
    "refund_approved": "Refund approved",
    "refund_rejected": "Refund rejected",
    "manual_operator_decision": "Manual operator decision",
    "other": "Other",
}

P2P_DISPUTE_REASON_CODE_LABELS = {
    "payment_not_received": "Payment not received",
    "wrong_amount": "Wrong amount",
    "fraud_suspected": "Fraud suspected",
    "timeout": "Timeout",
    "other": "Other",
}

P2P_DISPUTE_RESOLUTION_CODE_LABELS = {
    "payment_proof_validated": "Payment proof validated",
    "payment_not_proven": "Payment not proven",
    "seller_confirmed_non_receipt": "Seller confirmed non receipt",
    "manual_operator_decision": "Manual operator decision",
    "other": "Other",
}


def build_labeled_options(values: tuple[str, ...], labels: dict[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": labels.get(value, value)} for value in values]
