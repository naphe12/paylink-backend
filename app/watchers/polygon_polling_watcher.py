import asyncio
import json
from decimal import Decimal

import requests
from sqlalchemy import text
from web3 import Web3

from app.core.database import async_session_maker
from app.security.webhook_hmac import compute_signature

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
USDC_DECIMALS = Decimal("1000000")
LOCAL_RPC_URL = "http://127.0.0.1:8545"
MOCK_USDC_ADDRESS = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
DEFAULT_WEBHOOK_URL = "http://127.0.0.1:8000/escrow/webhooks/usdc"


class PolygonPollingWatcher:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(LOCAL_RPC_URL))

        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(MOCK_USDC_ADDRESS),
            abi=USDC_ABI,
        )
        self.webhook_url = DEFAULT_WEBHOOK_URL
        self.event_filter = self.contract.events.Transfer.create_filter(fromBlock="latest")

    async def run(self):
        print("Polygon watcher started")
        while True:
            try:
                await self.poll_transfers()
                await asyncio.sleep(2)
            except Exception as exc:
                print("Watcher error:", exc)
                await asyncio.sleep(5)

    async def poll_transfers(self):
        for event in self.event_filter.get_new_entries():
            await self.process_event(event)

    async def process_event(self, event):
        to_address = Web3.to_checksum_address(event["args"]["to"])
        amount_raw = int(event["args"]["value"])
        amount = Decimal(amount_raw) / USDC_DECIMALS
        tx_hash = event["transactionHash"].hex()
        confirmations = max(self.w3.eth.block_number - int(event["blockNumber"]), 0)

        print("Transfer detecte :", to_address, amount_raw)

        if not await self._is_escrow_deposit_address(to_address):
            return

        payload = {
            "network": "POLYGON",
            "tx_hash": tx_hash,
            "from_address": event["args"]["from"],
            "to_address": to_address,
            "amount": str(amount),
            "confirmations": confirmations,
        }
        await self._send_webhook(payload)

    async def _is_escrow_deposit_address(self, address: str) -> bool:
        async with async_session_maker() as db:
            res = await db.execute(
                text(
                    """
                    SELECT 1
                    FROM escrow.orders
                    WHERE lower(deposit_address) = :addr
                      AND status = 'CREATED'
                    LIMIT 1
                    """
                ),
                {"addr": address.lower()},
            )
            return res.first() is not None

    async def _send_webhook(self, payload: dict) -> None:
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = compute_signature(raw_body)
        headers = {
            "Content-Type": "application/json",
            "X-Paylink-Signature": signature,
        }
        response = requests.post(
            self.webhook_url,
            data=raw_body,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
