import asyncio
from web3 import Web3
from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import async_session_maker

class PolygonEventListener:

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))

        if self.w3.eth.chain_id != settings.POLYGON_CHAIN_ID:
            raise Exception("Wrong chain connected")

        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.USDC_CONTRACT_ADDRESS),
            abi=[{
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "from", "type": "address"},
                    {"indexed": True, "name": "to", "type": "address"},
                    {"indexed": False, "name": "value", "type": "uint256"},
                ],
                "name": "Transfer",
                "type": "event",
            }]
        )

    async def run(self):
        print("⚡ Polygon Event Listener started")

        event_filter = self.contract.events.Transfer.create_filter(
            fromBlock="latest"
        )

        while True:
            for event in event_filter.get_new_entries():
                await self.process_event(event)

            await asyncio.sleep(2)

    async def process_event(self, event):
        to_address = event["args"]["to"]
        tx_hash = event["transactionHash"].hex()
        amount = event["args"]["value"] / 1e6

        async with async_session_maker() as db:
            res = await db.execute(text("""
                SELECT id FROM escrow.orders
                WHERE deposit_address = :addr
                  AND status = 'CREATED'
            """), {"addr": to_address.lower()})

            row = res.first()
            if not row:
                return

            order_id = row[0]

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
