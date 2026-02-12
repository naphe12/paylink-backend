import asyncio
from web3 import Web3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings
from app.core.database import async_session_maker
from app.security.webhook_signing import generate_hmac_signature

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

class PolygonPollingWatcher:

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))

        if self.w3.eth.chain_id != settings.POLYGON_CHAIN_ID:
            raise Exception("Wrong chain connected")

        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.USDC_CONTRACT_ADDRESS),
            abi=USDC_ABI,
        )

        self.last_block = self.w3.eth.block_number

    async def run(self):
        print("🔎 Polygon Polling Watcher started")
        while True:
            try:
                await self.scan_new_blocks()
                await asyncio.sleep(5)
            except Exception as e:
                print("Watcher error:", e)
                await asyncio.sleep(10)

    async def scan_new_blocks(self):
        current_block = self.w3.eth.block_number

        if current_block <= self.last_block:
            return

        events = self.contract.events.Transfer().get_logs(
            fromBlock=self.last_block,
            toBlock=current_block,
        )

        async with async_session_maker() as db:
            for event in events:
                await self.process_event(db, event)

        self.last_block = current_block

    async def process_event(self, db: AsyncSession, event):
        to_address = event["args"]["to"]
        tx_hash = event["transactionHash"].hex()
        amount = event["args"]["value"] / 1e6  # USDC decimals 6

        # Check if address matches escrow order
        res = await db.execute(text("""
            SELECT id FROM escrow.orders
            WHERE deposit_address = :addr
              AND status = 'CREATED'
        """), {"addr": to_address.lower()})

        row = res.first()
        if not row:
            return

        order_id = row[0]

        # Idempotency: skip if tx already saved
        res2 = await db.execute(text("""
            SELECT 1 FROM escrow.orders
            WHERE deposit_tx_hash = :tx
        """), {"tx": tx_hash})

        if res2.first():
            return

        print(f"💰 Deposit detected for order {order_id}")

        # Update order directly (simplified)
        await db.execute(text("""
            UPDATE escrow.orders
            SET deposit_tx_hash = :tx,
                deposit_tx_amount = :amount,
                usdc_received = :amount,
                status = 'FUNDED',
                funded_at = now()
            WHERE id = :oid::uuid
        """), {
            "tx": tx_hash,
            "amount": amount,
            "oid": str(order_id),
        })

        await db.commit()
