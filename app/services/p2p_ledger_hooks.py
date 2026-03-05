import json

from sqlalchemy import text

from app.services.paylink_ledger_service import PaylinkLedgerService


async def _ensure_ledger_account(db, *, code: str, name: str, currency: str, metadata: dict | None = None):
    existing = await db.execute(
        text(
            """
            SELECT account_id
            FROM paylink.ledger_accounts
            WHERE code = :code
            LIMIT 1
            """
        ),
        {"code": code},
    )
    if existing.first():
        return

    await db.execute(
        text(
            """
            INSERT INTO paylink.ledger_accounts (code, name, currency_code, metadata)
            VALUES (:code, :name, :currency, CAST(:metadata AS jsonb))
            """
        ),
        {
            "code": code,
            "name": name,
            "currency": str(currency or "USD").upper(),
            "metadata": json.dumps(metadata or {}),
        },
    )


async def _ensure_p2p_ledger_accounts(db, trade):
    token = str(getattr(getattr(trade, "token", None), "value", getattr(trade, "token", "USD")) or "USD").upper()
    await _ensure_ledger_account(
        db,
        code="P2P_ESCROW_ASSET",
        name="P2P Escrow Asset",
        currency=token,
        metadata={"scope": "P2P", "type": "ASSET"},
    )
    await _ensure_ledger_account(
        db,
        code="P2P_USER_LIABILITY",
        name="P2P User Liability",
        currency=token,
        metadata={"scope": "P2P", "type": "LIABILITY"},
    )
    await _ensure_ledger_account(
        db,
        code="REVENUE_FEES_USD",
        name="Revenue Fees USD",
        currency="USD",
        metadata={"scope": "P2P", "type": "REVENUE"},
    )


async def ledger_lock(db, trade):
    await _ensure_p2p_ledger_accounts(db, trade)
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
    await _ensure_p2p_ledger_accounts(db, trade)
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
    await _ensure_p2p_ledger_accounts(db, trade)
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
