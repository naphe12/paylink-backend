import asyncio
import json
import os
import time
from decimal import Decimal

import httpx
from sqlalchemy import text
from web3 import Web3

from app.core.database import async_session_maker
from app.security.webhook_hmac import compute_signature
from app.watchers.p2p_watcher import P2PWatcher


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
    """
    Railway-friendly watcher:
    - Poll logs range (fromBlock -> latest) instead of create_filter('latest')
      because some providers are flaky with filters.
    - Confirms blocks (WATCHER_CONFIRMATIONS).
    - Idempotency: relies on backend to be idempotent by tx_hash/log_index.
    """

    def __init__(self):
        # --- ENV ---
        self.rpc_url = os.getenv("AMOY_RPC_URL", "https://rpc-amoy.polygon.technology")
        self.escrow_webhook_url = os.getenv("PAYLINK_WEBHOOK_URL")
        self.wallet_webhook_url = os.getenv("PAYLINK_WALLET_WEBHOOK_URL")

        self.poll_interval = float(os.getenv("WATCHER_POLL_INTERVAL", "2"))
        self.confirmations_required = int(os.getenv("WATCHER_CONFIRMATIONS", "3"))

        # Where to start if no state:
        # - "latest" means start at current chain head
        # - or set WATCHER_START_BLOCK=123456
        self.start_block_env = os.getenv("WATCHER_START_BLOCK", "latest")

        self.token_configs = []
        for symbol in ("USDC", "USDT"):
            token_address = os.getenv(f"{symbol}_TOKEN_ADDRESS")
            if not token_address:
                continue
            self.token_configs.append(
                {
                    "symbol": symbol,
                    "address": token_address,
                    "decimals_factor": Decimal(os.getenv(f"{symbol}_DECIMALS", "1000000")),
                }
            )
        if not self.token_configs:
            raise RuntimeError("Missing env USDC_TOKEN_ADDRESS or USDT_TOKEN_ADDRESS")
        if not self.escrow_webhook_url and not self.wallet_webhook_url:
            raise RuntimeError("Missing env PAYLINK_WEBHOOK_URL and PAYLINK_WALLET_WEBHOOK_URL")

        # --- Web3 ---
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 30}))

        self.contracts = {
            cfg["symbol"]: self.w3.eth.contract(
                address=Web3.to_checksum_address(cfg["address"]),
                abi=USDC_ABI,
            )
            for cfg in self.token_configs
        }
        usdc_cfg = next((cfg for cfg in self.token_configs if cfg["symbol"] == "USDC"), None)
        self.p2p = P2PWatcher(self.rpc_url, usdc_cfg["address"]) if usdc_cfg else None

        # Event signature topic must be 0x-prefixed for eth_getLogs
        self.transfer_topic = Web3.to_hex(Web3.keccak(text="Transfer(address,address,uint256)"))

        # Runtime state
        self._from_block = None  # will be initialized in run()

    async def run(self):
        print("[watcher] started")
        print("[watcher] rpc:", self.rpc_url)
        print("[watcher] tokens:", [cfg["symbol"] for cfg in self.token_configs])
        print("[watcher] escrow webhook:", self.escrow_webhook_url)
        print("[watcher] wallet webhook:", self.wallet_webhook_url)
        print("[watcher] confirmations_required:", self.confirmations_required)
        print("[watcher] poll_interval:", self.poll_interval)

        self._from_block = self._initial_from_block()
        print("[watcher] starting from block:", self._from_block)

        while True:
            try:
                await self._poll()
            except Exception as exc:
                print("[watcher] ERROR:", repr(exc))
                await asyncio.sleep(5)

            await asyncio.sleep(self.poll_interval)

    def _initial_from_block(self) -> int:
        latest = self.w3.eth.block_number
        if self.start_block_env.lower() == "latest":
            # Start slightly behind latest to avoid missing due to reorg/provider delay
            return max(latest - 2, 0)

        try:
            n = int(self.start_block_env)
            return max(n, 0)
        except ValueError:
            return max(latest - 2, 0)

    async def _poll(self):
        latest = self.w3.eth.block_number
        safe_to_block = latest - self.confirmations_required
        if safe_to_block < self._from_block:
            return  # not enough confirmations yet

        # Batch blocks to avoid provider limits
        batch_size = int(os.getenv("WATCHER_BATCH_SIZE", "1500"))
        to_block = min(self._from_block + batch_size - 1, safe_to_block)

        for token_cfg in self.token_configs:
            logs = self.w3.eth.get_logs(
                {
                    "fromBlock": self._from_block,
                    "toBlock": to_block,
                    "address": Web3.to_checksum_address(token_cfg["address"]),
                    "topics": [self.transfer_topic],
                }
            )

            if logs:
                print(
                    f"[watcher] {token_cfg['symbol']} logs found: {len(logs)} "
                    f"(blocks {self._from_block}..{to_block})"
                )

            for log in logs:
                await self._handle_transfer_log(log, latest_block=latest, token_cfg=token_cfg)

        # Move forward
        self._from_block = to_block + 1

    async def _handle_transfer_log(self, log, latest_block: int, token_cfg: dict):
        # Decode with contract event
        try:
            evt = self.contracts[token_cfg["symbol"]].events.Transfer().process_log(log)
        except Exception as exc:
            print("[watcher] failed to decode log:", repr(exc))
            return

        from_addr = Web3.to_checksum_address(evt["args"]["from"])
        to_addr = Web3.to_checksum_address(evt["args"]["to"])
        value_raw = int(evt["args"]["value"])

        amount = (Decimal(value_raw) / token_cfg["decimals_factor"]).quantize(Decimal("0.000001"))
        tx_hash = evt["transactionHash"].hex()
        block_number = int(evt["blockNumber"])
        log_index = int(evt["logIndex"])
        confirmations = max(latest_block - block_number, 0)
        block_timestamp = int(self.w3.eth.get_block(block_number)["timestamp"])

        print("[watcher] Transfer:", {
            "tx": tx_hash,
            "log_index": log_index,
            "from": from_addr,
            "to": to_addr,
            "value_raw": value_raw,
            "amount": str(amount),
            "block": block_number,
            "confirmations": confirmations,
        })

        # Confirmations guard (extra safety)
        if confirmations < self.confirmations_required:
            return

        payload = {
            "network": "POLYGON",
            "chain_id": int(os.getenv("CHAIN_ID", "80002")),
            "token_symbol": token_cfg["symbol"],
            "token_address": token_cfg["address"],
            "tx_hash": tx_hash,
            "log_index": log_index,  # important for idempotency
            "from_address": from_addr,
            "to_address": to_addr,
            "amount": str(amount),
            "amount_raw": str(value_raw),
            "block_number": block_number,
            "block_timestamp": block_timestamp,
            "confirmations": confirmations,
            "ts": int(time.time()),
        }

        async with async_session_maker() as db:
            is_escrow_deposit = await self._is_escrow_deposit_address(to_addr, db=db)
            wallet_target = await self._is_paylink_wallet_deposit_address(
                to_addr,
                token_cfg["symbol"],
                db=db,
            )

            # ESCROW
            if is_escrow_deposit and self.escrow_webhook_url:
                await self._send_webhook(payload)

            # WALLET CRYPTO
            if wallet_target and self.wallet_webhook_url:
                await self._send_wallet_webhook(payload)

            # P2P
            if token_cfg["symbol"] == "USDC" and self.p2p is not None:
                await self.p2p.process_transfer(
                    db=db,
                    tx_hash=tx_hash,
                    to_address=to_addr,
                    amount=amount,
                    block_number=block_number,
                    block_timestamp=block_timestamp,
                )

    async def _is_escrow_deposit_address(self, address: str, db=None) -> bool:
        # DB check: escrow.orders has deposit_address and status CREATED
        query = text(
            """
            SELECT 1
            FROM escrow.orders
            WHERE lower(deposit_address) = :addr
              AND status = 'CREATED'
            LIMIT 1
            """
        )
        params = {"addr": address.lower()}

        if db is not None:
            res = await db.execute(query, params)
            return res.first() is not None

        async with async_session_maker() as session:
            res = await session.execute(query, params)
            return res.first() is not None

    async def _is_paylink_wallet_deposit_address(self, address: str, token_symbol: str, db=None) -> bool:
        env_address = os.getenv(f"PAYLINK_{str(token_symbol).upper()}_DEPOSIT_ADDRESS")
        if not env_address:
            return False
        return address.lower() == str(env_address).lower()

    async def _send_webhook(self, payload: dict) -> None:
        raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = compute_signature(raw_body)

        headers = {
            "Content-Type": "application/json",
            "X-Paylink-Signature": signature,
        }

        # Retry simple
        retries = int(os.getenv("WATCHER_WEBHOOK_RETRIES", "3"))
        backoff = float(os.getenv("WATCHER_WEBHOOK_BACKOFF", "1.5"))

        async with httpx.AsyncClient(timeout=15) as client:
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    r = await client.post(self.escrow_webhook_url, content=raw_body, headers=headers)
                    r.raise_for_status()
                    print("[watcher] webhook OK:", r.status_code)
                    return
                except Exception as exc:
                    last_exc = exc
                    print(f"[watcher] webhook FAIL attempt {attempt}/{retries}:", repr(exc))
                    await asyncio.sleep(backoff * attempt)

            # after retries
            raise last_exc

    async def _send_wallet_webhook(self, payload: dict) -> None:
        raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = compute_signature(raw_body)
        headers = {
            "Content-Type": "application/json",
            "X-Paylink-Signature": signature,
        }
        retries = int(os.getenv("WATCHER_WEBHOOK_RETRIES", "3"))
        backoff = float(os.getenv("WATCHER_WEBHOOK_BACKOFF", "1.5"))

        async with httpx.AsyncClient(timeout=15) as client:
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    r = await client.post(self.wallet_webhook_url, content=raw_body, headers=headers)
                    r.raise_for_status()
                    print("[watcher] wallet webhook OK:", r.status_code)
                    return
                except Exception as exc:
                    last_exc = exc
                    print(f"[watcher] wallet webhook FAIL attempt {attempt}/{retries}:", repr(exc))
                    await asyncio.sleep(backoff * attempt)

            raise last_exc
