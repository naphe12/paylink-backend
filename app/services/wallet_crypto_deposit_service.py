from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import logging

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.mailjet_service import MailjetEmailService
from app.services.wallet_service import credit_user_crypto

logger = logging.getLogger(__name__)

SUPPORTED_WALLET_TOKENS = {"USDC", "USDT"}
SUPPORTED_REQUEST_STATUSES = {"PENDING", "MATCHED", "EXPIRED", "CANCELLED"}


def normalize_wallet_token(token_symbol: str) -> str:
    normalized = str(token_symbol or "").upper()
    if normalized not in SUPPORTED_WALLET_TOKENS:
        raise ValueError("Unsupported token. Use USDC or USDT.")
    return normalized


def normalize_network(network: str | None) -> str:
    normalized = str(network or "POLYGON").upper()
    if not normalized:
        raise ValueError("Network is required")
    return normalized


def normalize_address(address: str) -> str:
    normalized = str(address or "").strip().lower()
    if not normalized:
        raise ValueError("Deposit address is required")
    return normalized


def get_paylink_deposit_address(token_symbol: str, network: str) -> str:
    normalized_token = normalize_wallet_token(token_symbol)
    normalized_network = normalize_network(network)
    if normalized_network != "POLYGON":
        raise ValueError("Only POLYGON network is supported for now")

    if normalized_token == "USDC":
        address = getattr(settings, "PAYLINK_USDC_DEPOSIT_ADDRESS", "") or ""
    else:
        address = getattr(settings, "PAYLINK_USDT_DEPOSIT_ADDRESS", "") or ""

    normalized_address = normalize_address(address)
    if normalized_address == "0x0000000000000000000000000000000000000000":
        raise ValueError(f"PayLink deposit address for {normalized_token} is not configured")
    return normalized_address


async def ensure_wallet_crypto_deposit_tables(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.wallet_crypto_deposit_requests (
              request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              token_symbol text NOT NULL,
              network text NOT NULL,
              paylink_deposit_address text NOT NULL,
              expected_amount numeric(24, 8),
              status text NOT NULL DEFAULT 'PENDING',
              expires_at timestamptz,
              tx_hash text,
              log_index integer,
              matched_amount numeric(24, 8),
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_crypto_deposit_requests_pending
            ON paylink.wallet_crypto_deposit_requests (token_symbol, network, status, created_at)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.wallet_crypto_deposits (
              deposit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              request_id uuid REFERENCES paylink.wallet_crypto_deposit_requests(request_id) ON DELETE SET NULL,
              token_symbol text NOT NULL,
              network text NOT NULL,
              deposit_address text NOT NULL,
              tx_hash text NOT NULL,
              log_index integer NOT NULL DEFAULT 0,
              from_address text,
              amount numeric(24, 8) NOT NULL,
              confirmations integer NOT NULL DEFAULT 0,
              status text NOT NULL DEFAULT 'CONFIRMED',
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE (network, token_symbol, tx_hash, log_index)
            )
            """
        )
    )


async def create_wallet_deposit_request(
    db: AsyncSession,
    *,
    user_id: str,
    token_symbol: str,
    network: str,
    expected_amount: Decimal | None = None,
    ttl_minutes: int = 30,
) -> dict:
    await ensure_wallet_crypto_deposit_tables(db)
    normalized_token = normalize_wallet_token(token_symbol)
    normalized_network = normalize_network(network)
    paylink_deposit_address = get_paylink_deposit_address(normalized_token, normalized_network)
    normalized_expected_amount = None
    if expected_amount is not None:
        normalized_expected_amount = Decimal(str(expected_amount))
        if normalized_expected_amount <= 0:
            raise ValueError("Expected amount must be > 0")

    await expire_wallet_deposit_requests(db)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO paylink.wallet_crypto_deposit_requests (
                  user_id, token_symbol, network, paylink_deposit_address,
                  expected_amount, status, expires_at, metadata
                )
                VALUES (
                  CAST(:user_id AS uuid), :token_symbol, :network, :paylink_deposit_address,
                  :expected_amount, 'PENDING', now() + make_interval(mins => :ttl_minutes),
                  CAST(:metadata AS jsonb)
                )
                RETURNING request_id, user_id, token_symbol, network, paylink_deposit_address,
                          expected_amount, status, expires_at, tx_hash, log_index,
                          matched_amount, created_at, updated_at
                """
            ),
            {
                "user_id": str(user_id),
                "token_symbol": normalized_token,
                "network": normalized_network,
                "paylink_deposit_address": paylink_deposit_address,
                "expected_amount": normalized_expected_amount,
                "ttl_minutes": int(ttl_minutes),
                "metadata": json.dumps({"source": "wallet_crypto_deposit_request"}),
            },
        )
    ).mappings().first()
    return _serialize_request_row(row)


async def expire_wallet_deposit_requests(db: AsyncSession) -> None:
    await ensure_wallet_crypto_deposit_tables(db)
    await db.execute(
        text(
            """
            UPDATE paylink.wallet_crypto_deposit_requests
            SET status = 'EXPIRED',
                updated_at = now()
            WHERE status = 'PENDING'
              AND expires_at IS NOT NULL
              AND expires_at < now()
            """
        )
    )


async def cancel_wallet_deposit_request(
    db: AsyncSession,
    *,
    user_id: str,
    request_id: str,
) -> None:
    await ensure_wallet_crypto_deposit_tables(db)
    await db.execute(
        text(
            """
            UPDATE paylink.wallet_crypto_deposit_requests
            SET status = 'CANCELLED',
                updated_at = now()
            WHERE request_id = CAST(:request_id AS uuid)
              AND user_id = CAST(:user_id AS uuid)
              AND status = 'PENDING'
            """
        ),
        {
            "request_id": str(request_id),
            "user_id": str(user_id),
        },
    )


async def get_wallet_deposit_instruction(
    db: AsyncSession,
    *,
    user_id: str,
    token_symbol: str,
    network: str,
) -> dict:
    await ensure_wallet_crypto_deposit_tables(db)
    await expire_wallet_deposit_requests(db)

    normalized_token = normalize_wallet_token(token_symbol)
    normalized_network = normalize_network(network)
    paylink_deposit_address = get_paylink_deposit_address(normalized_token, normalized_network)

    row = (
        await db.execute(
            text(
                """
                SELECT request_id, user_id, token_symbol, network, paylink_deposit_address,
                       expected_amount, status, expires_at, tx_hash, log_index,
                       matched_amount, created_at, updated_at
                FROM paylink.wallet_crypto_deposit_requests
                WHERE user_id = CAST(:user_id AS uuid)
                  AND token_symbol = :token_symbol
                  AND network = :network
                  AND status = 'PENDING'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {
                "user_id": str(user_id),
                "token_symbol": normalized_token,
                "network": normalized_network,
            },
        )
    ).mappings().first()

    return {
        "user_id": str(user_id),
        "token_symbol": normalized_token,
        "network": normalized_network,
        "paylink_deposit_address": paylink_deposit_address,
        "has_pending_request": row is not None,
        "active_request": _serialize_request_row(row) if row else None,
    }


async def list_wallet_deposit_requests(
    db: AsyncSession,
    *,
    user_id: str,
    token_symbol: str | None = None,
) -> list[dict]:
    await ensure_wallet_crypto_deposit_tables(db)
    await expire_wallet_deposit_requests(db)

    params = {"user_id": str(user_id)}
    sql = """
        SELECT request_id, user_id, token_symbol, network, paylink_deposit_address,
               expected_amount, status, expires_at, tx_hash, log_index,
               matched_amount, created_at, updated_at
        FROM paylink.wallet_crypto_deposit_requests
        WHERE user_id = CAST(:user_id AS uuid)
    """
    if token_symbol:
        params["token_symbol"] = normalize_wallet_token(token_symbol)
        sql += " AND token_symbol = :token_symbol"
    sql += " ORDER BY created_at DESC LIMIT 20"

    rows = (await db.execute(text(sql), params)).mappings().all()
    return [_serialize_request_row(row) for row in rows]


def _serialize_request_row(row) -> dict | None:
    if not row:
        return None
    return {
        "request_id": str(row["request_id"]),
        "user_id": str(row["user_id"]),
        "token_symbol": row["token_symbol"],
        "network": row["network"],
        "paylink_deposit_address": row["paylink_deposit_address"],
        "expected_amount": float(row["expected_amount"]) if row["expected_amount"] is not None else None,
        "status": row["status"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "tx_hash": row["tx_hash"],
        "log_index": row["log_index"],
        "matched_amount": float(row["matched_amount"]) if row["matched_amount"] is not None else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def _find_matching_request(
    db: AsyncSession,
    *,
    token_symbol: str,
    network: str,
    deposit_address: str,
    amount: Decimal,
) -> dict | None:
    await ensure_wallet_crypto_deposit_tables(db)
    normalized_token = normalize_wallet_token(token_symbol)
    normalized_network = normalize_network(network)
    normalized_address = normalize_address(deposit_address)
    normalized_amount = Decimal(str(amount))
    await expire_wallet_deposit_requests(db)

    rows = (
        await db.execute(
            text(
                """
                SELECT request_id, user_id, token_symbol, network, paylink_deposit_address,
                       expected_amount, status, expires_at, tx_hash, log_index,
                       matched_amount, created_at, updated_at
                FROM paylink.wallet_crypto_deposit_requests
                WHERE token_symbol = :token_symbol
                  AND network = :network
                  AND lower(paylink_deposit_address) = :deposit_address
                  AND status = 'PENDING'
                ORDER BY created_at DESC
                """
            ),
            {
                "token_symbol": normalized_token,
                "network": normalized_network,
                "deposit_address": normalized_address,
            },
        )
    ).mappings().all()

    exact_match = None
    oldest_pending = None
    for row in rows:
        if oldest_pending is None:
            oldest_pending = row
        expected = row["expected_amount"]
        if expected is not None and Decimal(str(expected)) == normalized_amount:
            exact_match = row
            break
    return exact_match or oldest_pending


async def _send_admin_deposit_email(payload: dict) -> None:
    admin_email = getattr(settings, "ADMIN_ALERT_EMAIL", None)
    if not admin_email:
        return
    try:
        mailer = MailjetEmailService()
        html = (
            "<h3>Nouveau depot wallet crypto</h3>"
            f"<p>Utilisateur: {payload['user_id']}</p>"
            f"<p>Request: {payload['request_id']}</p>"
            f"<p>Token: {payload['token_symbol']}</p>"
            f"<p>Montant attendu: {payload['expected_amount']}</p>"
            f"<p>Montant recu: {payload['amount']}</p>"
            f"<p>Adresse PayLink: {payload['deposit_address']}</p>"
            f"<p>Tx hash: {payload['tx_hash']}</p>"
        )
        await run_in_threadpool(
            mailer.send_email,
            admin_email,
            f"[PAYLINK] Depot {payload['token_symbol']} detecte",
            None,
            body_html=html,
            text=(
                f"Depot {payload['token_symbol']} detecte pour user {payload['user_id']} "
                f"request={payload['request_id']} montant={payload['amount']} tx={payload['tx_hash']}"
            ),
        )
    except Exception:
        logger.exception("Failed to send admin crypto deposit email")


async def process_wallet_crypto_webhook(
    db: AsyncSession,
    *,
    token_symbol: str,
    network: str,
    tx_hash: str,
    log_index: int,
    from_address: str | None,
    to_address: str,
    amount: Decimal,
    confirmations: int,
    metadata: dict | None = None,
) -> dict:
    await ensure_wallet_crypto_deposit_tables(db)
    normalized_token = normalize_wallet_token(token_symbol)
    normalized_network = normalize_network(network)
    normalized_address = normalize_address(to_address)
    normalized_amount = Decimal(str(amount))
    if normalized_amount <= 0:
        raise ValueError("Amount must be > 0")

    paylink_deposit_address = get_paylink_deposit_address(normalized_token, normalized_network)
    if normalized_address != paylink_deposit_address:
        raise ValueError("Deposit not sent to PayLink deposit address")

    request_row = await _find_matching_request(
        db,
        token_symbol=normalized_token,
        network=normalized_network,
        deposit_address=normalized_address,
        amount=normalized_amount,
    )
    if not request_row:
        raise ValueError("No pending wallet deposit request found")

    try:
        deposit_row = (
            await db.execute(
                text(
                    """
                    INSERT INTO paylink.wallet_crypto_deposits (
                      user_id, request_id, token_symbol, network, deposit_address, tx_hash,
                      log_index, from_address, amount, confirmations, status, metadata
                    )
                    VALUES (
                      CAST(:user_id AS uuid), CAST(:request_id AS uuid), :token_symbol, :network,
                      :deposit_address, :tx_hash, :log_index, :from_address, :amount,
                      :confirmations, 'CONFIRMED', CAST(:metadata AS jsonb)
                    )
                    RETURNING deposit_id
                    """
                ),
                {
                    "user_id": str(request_row["user_id"]),
                    "request_id": str(request_row["request_id"]),
                    "token_symbol": normalized_token,
                    "network": normalized_network,
                    "deposit_address": normalized_address,
                    "tx_hash": tx_hash,
                    "log_index": int(log_index),
                    "from_address": from_address,
                    "amount": normalized_amount,
                    "confirmations": int(confirmations),
                    "metadata": json.dumps(metadata or {}),
                },
            )
        ).mappings().first()
    except IntegrityError:
        await db.rollback()
        return {
            "status": "IGNORED_DUPLICATE",
            "user_id": str(request_row["user_id"]),
            "token_symbol": normalized_token,
            "request_id": str(request_row["request_id"]),
        }

    await credit_user_crypto(
        str(request_row["user_id"]),
        normalized_amount,
        currency=normalized_token,
        source_account_code=f"TREASURY_{normalized_token}",
        ref=f"WALLET_{normalized_token}_DEPOSIT:{tx_hash}:{int(log_index)}",
        description=f"Wallet {normalized_token} deposit credited after on-chain confirmation",
        db=db,
    )

    await db.execute(
        text(
            """
            UPDATE paylink.wallet_crypto_deposit_requests
            SET status = 'MATCHED',
                tx_hash = :tx_hash,
                log_index = :log_index,
                matched_amount = :matched_amount,
                updated_at = now()
            WHERE request_id = CAST(:request_id AS uuid)
            """
        ),
        {
            "tx_hash": tx_hash,
            "log_index": int(log_index),
            "matched_amount": normalized_amount,
            "request_id": str(request_row["request_id"]),
        },
    )

    admin_payload = {
        "deposit_id": str(deposit_row["deposit_id"]),
        "request_id": str(request_row["request_id"]),
        "user_id": str(request_row["user_id"]),
        "token_symbol": normalized_token,
        "network": normalized_network,
        "expected_amount": (
            str(request_row["expected_amount"]) if request_row["expected_amount"] is not None else None
        ),
        "amount": str(normalized_amount),
        "deposit_address": normalized_address,
        "tx_hash": tx_hash,
        "from_address": from_address,
        "confirmations": int(confirmations),
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "Wallet crypto deposit matched token=%s user_id=%s request_id=%s tx=%s amount=%s",
        normalized_token,
        request_row["user_id"],
        request_row["request_id"],
        tx_hash,
        normalized_amount,
    )
    await _send_admin_deposit_email(admin_payload)

    return {
        "status": "CREDITED",
        "user_id": str(request_row["user_id"]),
        "request_id": str(request_row["request_id"]),
        "token_symbol": normalized_token,
        "amount": str(normalized_amount),
        "tx_hash": tx_hash,
    }
