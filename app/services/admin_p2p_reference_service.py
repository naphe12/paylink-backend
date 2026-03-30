from app.schemas.dispute_codes import (
    ESCROW_REFUND_REASON_CODE_LABELS,
    ESCROW_REFUND_REASON_CODE_VALUES,
    ESCROW_REFUND_RESOLUTION_CODE_LABELS,
    ESCROW_REFUND_RESOLUTION_CODE_VALUES,
    P2P_DISPUTE_REASON_CODE_LABELS,
    P2P_DISPUTE_REASON_CODE_VALUES,
    P2P_DISPUTE_RESOLUTION_CODE_LABELS,
    P2P_DISPUTE_RESOLUTION_CODE_VALUES,
    PROOF_TYPE_LABELS,
    PROOF_TYPE_VALUES,
    build_labeled_options,
)


def get_dispute_code_catalog() -> dict:
    return {
        "proof_types": build_labeled_options(PROOF_TYPE_VALUES, PROOF_TYPE_LABELS),
        "escrow_refund_reason_codes": build_labeled_options(
            ESCROW_REFUND_REASON_CODE_VALUES,
            ESCROW_REFUND_REASON_CODE_LABELS,
        ),
        "escrow_refund_resolution_codes": build_labeled_options(
            ESCROW_REFUND_RESOLUTION_CODE_VALUES,
            ESCROW_REFUND_RESOLUTION_CODE_LABELS,
        ),
        "p2p_dispute_reason_codes": build_labeled_options(
            P2P_DISPUTE_REASON_CODE_VALUES,
            P2P_DISPUTE_REASON_CODE_LABELS,
        ),
        "p2p_dispute_resolution_codes": build_labeled_options(
            P2P_DISPUTE_RESOLUTION_CODE_VALUES,
            P2P_DISPUTE_RESOLUTION_CODE_LABELS,
        ),
    }
