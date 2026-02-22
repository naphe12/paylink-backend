import asyncio
import json
import os
import time
from decimal import Decimal

import httpx
from web3 import Web3


USDC_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"},
    ],
    "name": "Transfer",
    "type": "event",
}]


class UnifiedPolygonWatcher:
    def __init__(self):
        self.rpc_url = os.getenv("AMOY_RPC_URL")
        self.token_address = os.getenv("USDC_TOKEN_ADDRESS")
        self.webhook_url = os.getenv("PAYLINK_WEBHOOK_URL")
        self.hmac_secret = os.getenv("HMAC_SECRET")

        self.confirmations_required = int(os.getenv("WATCHER_CONFIRMATIONS", "3"))
        self.poll_interval = int(os.getenv("WATCHER_POLL_INTERVAL", "2"))
        self.batch_size = int(os.getenv("WATCHER_BATCH_SIZE", "1500"))

        self.decimals_factor = Decimal(os.getenv("USDC_DECIMALS", "1000000"))

        if not all([self.rpc_url, self.token_address, self.webhook_url, self.hmac_secret]):
            raise RuntimeError("Missing required environment variables")

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.token_address),
            abi=USDC_ABI,
        )

        self.transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()
        self.from_block = self.w3.eth.block_number - 2

    async def run(self):
        print("🚀 Unified Polygon Watcher started")
        while True:
            try:
                await self._poll()
            except Exception as e:
                print("Watcher error:", e)
                await asyncio.sleep(5)

            await asyncio.sleep(self.poll_interval)

    async def _poll(self):
        latest = self.w3.eth.block_number
        safe_to_block = latest - self.confirmations_required

        if safe_to_block <= self.from_block:
            return

        to_block = min(self.from_block + self.batch_size, safe_to_block)

        logs = self.w3.eth.get_logs({
            "fromBlock": self.from_block,
            "toBlock": to_block,
            "address": Web3.to_checksum_address(self.token_address),
            "topics": [self.transfer_topic],
        })

        for log in logs:
            await self._process_log(log, latest)

        self.from_block = to_block + 1

    async def _process_log(self, log, latest_block):
        evt = self.contract.events.Transfer().process_log(log)

        from_addr = evt["args"]["from"]
        to_addr = evt["args"]["to"]
        value_raw = int(evt["args"]["value"])
        amount = Decimal(value_raw) / self.decimals_factor

        tx_hash = evt["transactionHash"].hex()
        block_number = int(evt["blockNumber"])
        log_index = int(evt["logIndex"])

        confirmations = latest_block - block_number
        if confirmations < self.confirmations_required:
            return

        payload = {
            "network": "POLYGON",
            "chain_id": 80002,
            "token_address": self.token_address,
            "tx_hash": tx_hash,
            "log_index": log_index,
            "from_address": from_addr,
            "to_address": to_addr,
            "amount": str(amount),
            "amount_raw": str(value_raw),
            "block_number": block_number,
            "confirmations": confirmations,
            "timestamp": int(time.time()),
        }

        await self._send_webhook(payload)

    async def _send_webhook(self, payload):
        raw = json.dumps(payload, separators=(",", ":")).encode()

        import hmac, hashlib
        signature = hmac.new(
            self.hmac_secret.encode(),
            raw,
            hashlib.sha256
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Paylink-Signature": signature,
        }

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self.webhook_url, content=raw, headers=headers)
            r.raise_for_status()