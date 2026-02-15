from datetime import datetime, timezone
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.config import settings
from app.models.p2p_enums import TradeStatus
from app.models.p2p_trade import P2PTrade
from app.services.circuit_breaker import CircuitBreaker, BreakerConfig
from app.services.metrics import inc
from app.services.p2p_risk_service import P2PRiskService
from app.services.p2p_trade_state import set_trade_status

logger = logging.getLogger("paylink")

rpc_breaker = CircuitBreaker(
    "polygon_rpc",
    settings.REDIS_URL,
    BreakerConfig(
        fail_threshold=settings.CB_FAIL_THRESHOLD,
        open_seconds=settings.CB_OPEN_SECONDS,
        halfopen_max_calls=settings.CB_HALFOPEN_MAX_CALLS,
    ),
)

USDC_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]


class P2PWatcher:
    def __init__(self, rpc_url: str, contract_address: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=USDC_ABI,
        )

    async def process_transfer(self, db: AsyncSession, tx_hash: str, to_address: str, amount):
        to_addr_norm = to_address.lower()

        trade = await db.scalar(
            select(P2PTrade).where(
                func.lower(P2PTrade.escrow_deposit_addr) == to_addr_norm,
                P2PTrade.status == TradeStatus.AWAITING_CRYPTO,
            )
        )

        if not trade:
            return

        trade.escrow_tx_hash = tx_hash

        if not await rpc_breaker.allow():
            logger.warning("Circuit breaker OPEN/HALF full for polygon_rpc; skipping tx %s", tx_hash)
            return

        try:
            block = self.w3.eth.get_block("latest")
            ts = int(block["timestamp"])
            trade.escrow_locked_at = datetime.fromtimestamp(ts, tz=timezone.utc)
            await rpc_breaker.record_success()
        except Exception:
            await rpc_breaker.record_failure()
            raise

        await set_trade_status(
            db,
            trade,
            TradeStatus.CRYPTO_LOCKED,
            actor_user_id=None,
            actor_role="SYSTEM",
            note="Crypto deposit detected",
        )
        await P2PRiskService.apply(db, trade)
        inc("p2p.trade.crypto_locked")

        await db.commit()
