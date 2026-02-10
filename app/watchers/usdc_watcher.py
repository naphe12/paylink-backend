from web3 import Web3
from decimal import Decimal
import requests

USDC_DECIMALS = 6
ESCROW_WEBHOOK_URL = "https://api.pesapaid.com/escrow/webhooks/usdc"

w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))

def watch_tx(tx_hash: str):
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
