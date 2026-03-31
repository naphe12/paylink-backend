from decimal import Decimal


ZERO = Decimal("0")


def effective_external_transfer_capacity(
    wallet_available: Decimal,
    credit_available: Decimal,
) -> Decimal:
    wallet = Decimal(wallet_available or 0)
    credit = max(Decimal(credit_available or 0), ZERO)
    return credit if wallet < 0 else wallet + credit


def compute_external_transfer_funding(
    *,
    wallet_available: Decimal,
    credit_available: Decimal,
    total_required: Decimal,
) -> dict[str, Decimal]:
    wallet = Decimal(wallet_available or 0)
    credit = max(Decimal(credit_available or 0), ZERO)
    total = max(Decimal(total_required or 0), ZERO)

    wallet_debit_amount = min(max(wallet, ZERO), total)
    remaining_after_wallet = total - wallet_debit_amount
    credit_used = min(credit, remaining_after_wallet)
    residual_after_credit = remaining_after_wallet - credit_used

    return {
        "wallet_debit_amount": wallet_debit_amount,
        "wallet_after": wallet - wallet_debit_amount,
        "credit_used": credit_used,
        "credit_available_after": credit - credit_used,
        "residual_after_credit": residual_after_credit,
    }
