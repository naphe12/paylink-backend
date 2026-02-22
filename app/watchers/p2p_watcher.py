from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.p2p_enums import TradeStatus
from app.models.p2p_trade import P2PTrade
from app.services.alerts import deliver_alerts
from app.services.aml_engine import AMLEngine
from app.services.metrics import inc
from app.services.p2p_risk_service import P2PRiskService
from app.services.p2p_trade_state import set_trade_status

class P2PWatcher:
    def __init__(self, rpc_url: str, contract_address: str):
        self.rpc_url = rpc_url
        self.contract_address = contract_address

    async def process_transfer(
        self,
        db: AsyncSession,
        tx_hash: str,
        to_address: str,
        amount,
        block_number: int | None = None,
        block_timestamp: int | None = None,
    ):
        to_addr_norm = to_address.lower()

        trade = await db.scalar(
            select(P2PTrade).where(
                func.lower(P2PTrade.escrow_deposit_addr) == to_addr_norm,
                P2PTrade.status == TradeStatus.AWAITING_CRYPTO,
            )
        )

        if not trade:
            return

        # Idempotency guard for duplicate log detection/replay.
        if trade.escrow_tx_hash:
            return

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
