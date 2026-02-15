from app.services.paylink_ledger_service import PaylinkLedgerService


async def ledger_lock(db, trade):
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=trade.trade_id,
        description="P2P Crypto Locked",
        postings=[
            {
                "account_code": "P2P_ESCROW_ASSET",
                "direction": "DEBIT",
                "amount": trade.token_amount,
                "currency": trade.token.value,
            },
            {
                "account_code": "P2P_USER_LIABILITY",
                "direction": "CREDIT",
                "amount": trade.token_amount,
                "currency": trade.token.value,
            },
        ],
    )


async def ledger_release(db, trade, amount_token=None):
    release_amount = amount_token if amount_token is not None else trade.token_amount
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=trade.trade_id,
        description="P2P Crypto Released",
        postings=[
            {
                "account_code": "P2P_USER_LIABILITY",
                "direction": "DEBIT",
                "amount": release_amount,
                "currency": trade.token.value,
            },
            {
                "account_code": "P2P_ESCROW_ASSET",
                "direction": "CREDIT",
                "amount": release_amount,
                "currency": trade.token.value,
            },
        ],
    )


async def ledger_fee(db, trade, fee_token, fee_bif, fee_rate):
    await PaylinkLedgerService.post_journal(
        db,
        tx_id=trade.trade_id,
        description="P2P Fee",
        postings=[
            {
                "account_code": "P2P_USER_LIABILITY",
                "direction": "DEBIT",
                "amount": fee_token,
                "currency": "USD",
            },
            {
                "account_code": "REVENUE_FEES_USD",
                "direction": "CREDIT",
                "amount": fee_token,
                "currency": "USD",
            },
        ],
        metadata={
            "event": "P2P_FEE",
            "trade_id": str(trade.trade_id),
            "token": str(trade.token.value),
            "fee_rate": str(fee_rate),
            "fee_token": str(fee_token),
            "fee_bif": str(fee_bif),
        },
    )
