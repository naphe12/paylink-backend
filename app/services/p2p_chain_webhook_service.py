from decimal import Decimal

from app.config import settings
from app.services.p2p_chain_deposit_service import get_chain_deposit_by_provider_event
from app.watchers.p2p_watcher import P2PWatcher


async def process_p2p_chain_deposit_webhook(db, payload: dict) -> dict:
    token_symbol = str(payload.get("token_symbol") or "").upper()
    if not token_symbol:
        token_address = str(payload.get("token_address") or "").lower()
        if token_address and token_address == str(settings.USDC_CONTRACT_ADDRESS or "").lower():
            token_symbol = "USDC"
        elif token_address and token_address == str(settings.USDT_CONTRACT_ADDRESS or "").lower():
            token_symbol = "USDT"
    if token_symbol not in {"USDC", "USDT"}:
        raise ValueError("Missing or unsupported token_symbol")

    amount = payload.get("amount")
    if amount is None:
        raise ValueError("Missing amount")

    provider = str(payload.get("provider") or "").strip().lower() or None
    provider_event_id = str(payload.get("provider_event_id") or "").strip() or None
    source = str(payload.get("source") or "").strip().lower() or provider or "provider_webhook"
    source_ref = str(payload.get("source_ref") or "").strip() or provider_event_id
    tx_hash = str(payload.get("tx_hash") or "")
    log_index = int(payload.get("log_index") or 0)

    if provider and provider_event_id:
        existing = await get_chain_deposit_by_provider_event(
            db,
            provider=provider,
            provider_event_id=provider_event_id,
        )
        if existing:
            same_transfer = str(existing.get("tx_hash") or "") == tx_hash and int(existing.get("log_index") or 0) == log_index
            if same_transfer:
                return {
                    "status": "DUPLICATE",
                    "duplicate": True,
                    "deposit_id": existing.get("deposit_id"),
                    "trade_id": existing.get("trade_id"),
                    "tx_hash": tx_hash,
                    "log_index": log_index,
                    "token_symbol": token_symbol,
                    "provider": provider,
                    "provider_event_id": provider_event_id,
                    "source": source,
                    "source_ref": source_ref,
                }
            raise ValueError(
                f"provider_event_id already linked to another transfer (deposit_id={existing.get('deposit_id')})"
            )

    await P2PWatcher(settings.POLYGON_RPC_URL or "").process_transfer(
        db=db,
        tx_hash=tx_hash,
        log_index=log_index,
        to_address=str(payload.get("to_address") or ""),
        from_address=payload.get("from_address"),
        token_symbol=token_symbol,
        amount=Decimal(str(amount)),
        escrow_deposit_ref=payload.get("escrow_deposit_ref"),
        block_number=payload.get("block_number"),
        block_timestamp=payload.get("block_timestamp"),
        confirmations=payload.get("confirmations"),
        chain_id=payload.get("chain_id"),
        metadata={
            **dict(payload),
            "provider": provider,
            "provider_event_id": provider_event_id,
            "source": source,
            "source_ref": source_ref,
        },
    )
    return {
        "status": "OK",
        "tx_hash": tx_hash,
        "log_index": log_index,
        "token_symbol": token_symbol,
        "provider": provider,
        "provider_event_id": provider_event_id,
        "source": source,
        "source_ref": source_ref,
    }
