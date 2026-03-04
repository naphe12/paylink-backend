from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.p2p_enums import TokenCode, TradeStatus
from app.models.p2p_trade import P2PTrade
from app.services.alerts import deliver_alerts
from app.services.aml_engine import AMLEngine
from app.services.metrics import inc
from app.services.p2p_chain_deposit_service import upsert_chain_deposit
from app.services.p2p_risk_service import P2PRiskService
from app.services.p2p_trade_state import set_trade_status

class P2PWatcher:
    def __init__(self, rpc_url: str, contract_address: str | None = None):
        self.rpc_url = rpc_url
        self.contract_address = contract_address

    async def _resolve_trade(
        self,
        db: AsyncSession,
        *,
        to_addr_norm: str,
        token_symbol: str,
        amount: Decimal,
        escrow_deposit_ref: str | None = None,
    ) -> tuple[P2PTrade | None, str]:
        normalized_ref = str(escrow_deposit_ref or "").strip().upper()
        token_code = TokenCode(str(token_symbol or "").upper())
        if normalized_ref:
            ref_stmt = select(P2PTrade).where(
                func.upper(P2PTrade.escrow_deposit_ref) == normalized_ref,
                P2PTrade.status == TradeStatus.AWAITING_CRYPTO,
                P2PTrade.token == token_code,
            )
            ref_candidates = list((await db.execute(ref_stmt.order_by(P2PTrade.created_at.asc()))).scalars().all())
            if len(ref_candidates) == 1:
                return ref_candidates[0], "reference_match"
            if len(ref_candidates) > 1:
                return None, "ambiguous_reference"

        stmt = select(P2PTrade).where(
            func.lower(P2PTrade.escrow_deposit_addr) == to_addr_norm,
            P2PTrade.status == TradeStatus.AWAITING_CRYPTO,
            P2PTrade.token == token_code,
        )
        candidates = list((await db.execute(stmt.order_by(P2PTrade.created_at.asc()))).scalars().all())
        if not candidates:
            return None, "not_found"
        if len(candidates) == 1:
            return candidates[0], "single_candidate"

        exact_amount_matches = [
            trade
            for trade in candidates
            if Decimal(str(trade.token_amount or 0)).quantize(Decimal("0.000001")) == amount.quantize(Decimal("0.000001"))
        ]
        if len(exact_amount_matches) == 1:
            return exact_amount_matches[0], "exact_amount_match"
        if len(exact_amount_matches) > 1:
            return None, "ambiguous_exact_amount"
        return None, "ambiguous_shared_address"

    async def process_transfer(
        self,
        db: AsyncSession,
        tx_hash: str,
        to_address: str,
        token_symbol: str,
        amount,
        log_index: int = 0,
        escrow_deposit_ref: str | None = None,
        block_number: int | None = None,
        block_timestamp: int | None = None,
        from_address: str | None = None,
        confirmations: int | None = None,
        chain_id: int | None = None,
        metadata: dict | None = None,
    ):
        to_addr_norm = to_address.lower()
        normalized_amount = Decimal(str(amount))
        deposit_metadata = dict(metadata or {})
        if escrow_deposit_ref:
            deposit_metadata["escrow_deposit_ref"] = escrow_deposit_ref
        if from_address:
            deposit_metadata["from_address"] = from_address
        if confirmations is not None:
            deposit_metadata["confirmations"] = int(confirmations)
        if chain_id is not None:
            deposit_metadata["chain_id"] = int(chain_id)

        trade, resolution = await self._resolve_trade(
            db,
            to_addr_norm=to_addr_norm,
            token_symbol=str(token_symbol or "").upper(),
            amount=normalized_amount,
            escrow_deposit_ref=escrow_deposit_ref,
        )
        if not trade and resolution == "not_found":
            await upsert_chain_deposit(
                db,
                tx_hash=tx_hash,
                log_index=log_index,
                network="POLYGON",
                token=str(token_symbol or "").upper(),
                to_address=to_address,
                amount=normalized_amount,
                block_number=block_number,
                block_timestamp=block_timestamp,
                status="UNMATCHED",
                resolution=resolution,
                metadata=deposit_metadata,
            )
            await db.commit()
            return
        if not trade:
            await upsert_chain_deposit(
                db,
                tx_hash=tx_hash,
                log_index=log_index,
                network="POLYGON",
                token=str(token_symbol or "").upper(),
                to_address=to_address,
                amount=normalized_amount,
                block_number=block_number,
                block_timestamp=block_timestamp,
                status="AMBIGUOUS",
                resolution=resolution,
                metadata=deposit_metadata,
            )
            if resolution.startswith("ambiguous"):
                inc("p2p.trade.crypto_lock_ambiguous")
                await deliver_alerts(
                    db,
                    subject="P2P deposit requires manual review",
                    message=f"Deposit {tx_hash} could not be matched unambiguously to a P2P trade.",
                    metadata={
                        "tx_hash": tx_hash,
                        "to_address": to_address,
                        "token": str(token_symbol or "").upper(),
                        "amount": str(normalized_amount),
                        "escrow_deposit_ref": escrow_deposit_ref,
                        "resolution": resolution,
                        "block_number": block_number,
                    },
                )
                await db.commit()
            return

        # Idempotency guard for duplicate log detection/replay.
        if trade.escrow_tx_hash:
            return

        await upsert_chain_deposit(
            db,
            tx_hash=tx_hash,
            log_index=log_index,
            network="POLYGON",
            token=str(token_symbol or "").upper(),
            to_address=to_address,
            amount=normalized_amount,
            block_number=block_number,
            block_timestamp=block_timestamp,
            status="MATCHED",
            resolution=resolution,
            trade_id=str(trade.trade_id),
            metadata=deposit_metadata,
        )
        trade.escrow_lock_log_index = int(log_index)
        trade.escrow_tx_hash = tx_hash

        if block_timestamp is not None:
            ts = int(block_timestamp)
            trade.escrow_locked_at = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            trade.escrow_locked_at = datetime.now(timezone.utc)

        await set_trade_status(
            db,
            trade,
            TradeStatus.CRYPTO_LOCKED,
            actor_user_id=None,
            actor_role="SYSTEM",
            note="Crypto deposit detected",
        )
        await P2PRiskService.apply(db, trade)
        aml = await AMLEngine.evaluate_p2p(db, trade, event="P2P_CRYPTO_LOCKED")
        trade.risk_score = aml["final_score"]
        trade.flags = sorted(set(list(trade.flags or []) + [h["code"] for h in aml["hits"]]))

        metadata = {
            "trade_id": str(trade.trade_id),
            "event": "P2P_CRYPTO_LOCKED",
            "hits": aml["hits"],
            "match_resolution": resolution,
        }
        if block_number is not None:
            metadata["block_number"] = block_number

        if aml["should_alert"]:
            await deliver_alerts(
                db,
                subject="AML Alert (P2P_CRYPTO_LOCKED)",
                message=f"Trade {trade.trade_id} AML score {aml['final_score']}",
                metadata=metadata,
            )
        inc("p2p.trade.crypto_locked")

        await db.commit()
