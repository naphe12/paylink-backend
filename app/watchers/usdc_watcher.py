from decimal import Decimal

import requests
from web3 import Web3

from app.config import settings

USDC_DECIMALS = 6
ESCROW_WEBHOOK_URL = "https://api.pesapaid.com/escrow/webhooks/usdc"

w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
USDC_ADDRESS = Web3.to_checksum_address(settings.USDC_CONTRACT_ADDRESS)

_network_checked = False


def _validate_network_settings() -> None:
    network = str(settings.ESCROW_NETWORK or "").lower()
    if network == "polygon_mumbai" and settings.POLYGON_CHAIN_ID != 80001:
        raise ValueError(
            f"Invalid POLYGON_CHAIN_ID for {settings.ESCROW_NETWORK}: "
            f"expected 80001, got {settings.POLYGON_CHAIN_ID}"
        )
    if network == "polygon_mainnet" and settings.POLYGON_CHAIN_ID != 137:
        raise ValueError(
            f"Invalid POLYGON_CHAIN_ID for {settings.ESCROW_NETWORK}: "
            f"expected 137, got {settings.POLYGON_CHAIN_ID}"
        )


def _ensure_network() -> None:
    global _network_checked
    if _network_checked:
        return
    _validate_network_settings()
    chain_id = w3.eth.chain_id
    print(f"Connected to chain: {chain_id}")
    if chain_id != settings.POLYGON_CHAIN_ID:
        raise Exception(
            f"Wrong network. Expected {settings.POLYGON_CHAIN_ID}, got {chain_id}"
        )
    _network_checked = True


def watch_tx(tx_hash: str):
    _ensure_network()
    tx = w3.eth.get_transaction(tx_hash)
    receipt = w3.eth.get_transaction_receipt(tx_hash)

    confirmations = w3.eth.block_number - receipt.blockNumber

    amount = Decimal(int(tx["value"])) / (10 ** USDC_DECIMALS)

    payload = {
        "network": "POLYGON",
        "tx_hash": tx_hash,
        "from_address": tx["from"],
        "to_address": tx["to"],
        "amount": str(amount),
        "confirmations": confirmations
    }

    requests.post(ESCROW_WEBHOOK_URL, json=payload)
