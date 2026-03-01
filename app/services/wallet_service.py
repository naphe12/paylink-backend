from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.services.paylink_ledger_service import PaylinkLedgerService

USDC_CURRENCY = "USDC"
USDT_CURRENCY = "USDT"
BIF_CURRENCY = "BIF"
USDC_WALLET_SOURCE_ACCOUNT = "ESCROW_USDC_LIABILITY"
USDT_WALLET_SOURCE_ACCOUNT = "TREASURY_USDT"
FX_POOL_USDC_ACCOUNT = "FX_POOL_USDC"
FX_POOL_BIF_ACCOUNT = "FX_POOL_BIF"
DEFAULT_USDC_BIF_RATE = Decimal("2800")
SUPPORTED_CRYPTO_CURRENCIES = {USDC_CURRENCY, USDT_CURRENCY}


def _wallet_account_code(user_id: str) -> str:
    return _crypto_wallet_account_code(user_id, USDC_CURRENCY)


def _usdt_wallet_account_code(user_id: str) -> str:
    return _crypto_wallet_account_code(user_id, USDT_CURRENCY)


def _crypto_wallet_account_code(user_id: str, currency: str) -> str:
    normalized_currency = str(currency or "").upper()
    if normalized_currency not in SUPPORTED_CRYPTO_CURRENCIES:
        raise ValueError(f"Unsupported crypto currency: {currency}")
    return f"USER_{user_id}_{normalized_currency}"


def _bif_wallet_account_code(user_id: str) -> str:
    return f"USER_{user_id}_BIF"


async def _resolve_account_id(db: AsyncSession, account_code: str):
    res = await db.execute(
        text("SELECT account_id FROM paylink.ledger_accounts WHERE code = :code"),
        {"code": account_code},
    )
    account_id = res.scalar_one_or_none()
    if not account_id:
        raise ValueError(f"Ledger account not found: {account_code}")
    return account_id


async def _get_or_create_wallet_account_code(db: AsyncSession, user_id: str) -> str:
    return await _get_or_create_crypto_wallet_account_code(db, user_id, USDC_CURRENCY)


async def _get_or_create_crypto_wallet_account_code(
    db: AsyncSession,
    user_id: str,
    currency: str,
) -> str:
    normalized_currency = str(currency or "").upper()
    account_code = _crypto_wallet_account_code(user_id, normalized_currency)
    exists = await db.execute(
        text(
            """
            SELECT account_id
            FROM paylink.ledger_accounts
            WHERE code = :code
            LIMIT 1
            """
        ),
        {"code": account_code},
    )
    if exists.first():
        return account_code

    await db.execute(
        text(
            """
            INSERT INTO paylink.ledger_accounts (code, name, currency_code, metadata)
            VALUES (:code, :name, :currency, CAST(:metadata AS jsonb))
            """
        ),
        {
            "code": account_code,
            "name": f"Wallet {normalized_currency} User {user_id}",
            "currency": normalized_currency,
            "metadata": json.dumps(
                {
                    "wallet_type": f"USER_{normalized_currency}",
                    "user_id": str(user_id),
                }
            ),
        },
    )
    return account_code


async def _resolve_existing_bif_wallet_code(db: AsyncSession, user_id: str) -> str | None:
    user_style = _bif_wallet_account_code(user_id)
    legacy_style = f"WALLET_BIF_{user_id}"
    res = await db.execute(
        text(
            """
            SELECT code
            FROM paylink.ledger_accounts
            WHERE code IN (:user_style, :legacy_style)
            ORDER BY CASE WHEN code = :user_style THEN 0 ELSE 1 END
            LIMIT 1
            """
        ),
        {
            "user_style": user_style,
            "legacy_style": legacy_style,
        },
    )
    row = res.first()
    if not row:
        return None
    return str(row[0])


async def _get_or_create_bif_wallet_account_code(db: AsyncSession, user_id: str) -> str:
    existing = await _resolve_existing_bif_wallet_code(db, user_id)
    if existing:
        return existing

    account_code = _bif_wallet_account_code(user_id)
    await db.execute(
        text(
            """
            INSERT INTO paylink.ledger_accounts (code, name, currency_code, metadata)
            VALUES (:code, :name, :currency, CAST(:metadata AS jsonb))
            """
        ),
        {
            "code": account_code,
            "name": f"Wallet BIF User {user_id}",
            "currency": BIF_CURRENCY,
            "metadata": json.dumps(
                {
                    "wallet_type": "USER_BIF",
                    "user_id": str(user_id),
                }
            ),
        },
    )
    return account_code


async def ensure_usdc_wallet_account(user_id: str, db: AsyncSession | None = None) -> str:
    if db is not None:
        return await _get_or_create_wallet_account_code(db, str(user_id))

    async with async_session_maker() as session:
        code = await _get_or_create_wallet_account_code(session, str(user_id))
        await session.commit()
        return code


async def ensure_bif_wallet_account(user_id: str, db: AsyncSession | None = None) -> str:
    if db is not None:
        return await _get_or_create_bif_wallet_account_code(db, str(user_id))

    async with async_session_maker() as session:
        code = await _get_or_create_bif_wallet_account_code(session, str(user_id))
        await session.commit()
        return code


async def ensure_crypto_wallet_account(
    user_id: str,
    currency: str,
    db: AsyncSession | None = None,
) -> str:
    normalized_currency = str(currency or "").upper()
    if db is not None:
        return await _get_or_create_crypto_wallet_account_code(db, str(user_id), normalized_currency)

    async with async_session_maker() as session:
        code = await _get_or_create_crypto_wallet_account_code(session, str(user_id), normalized_currency)
        await session.commit()
        return code


async def ensure_usdt_wallet_account(user_id: str, db: AsyncSession | None = None) -> str:
    return await ensure_crypto_wallet_account(user_id, USDT_CURRENCY, db=db)


async def get_usdc_balance(user_id: str, db: AsyncSession | None = None) -> Decimal:
    return await get_crypto_balance(user_id, USDC_CURRENCY, db=db)


async def get_crypto_balance(
    user_id: str,
    currency: str,
    db: AsyncSession | None = None,
) -> Decimal:
    normalized_currency = str(currency or "").upper()
    account_code = _crypto_wallet_account_code(str(user_id), normalized_currency)
    if db is not None:
        return await PaylinkLedgerService.get_balance(
            db,
            account_code=account_code,
            currency=normalized_currency,
        )

    async with async_session_maker() as session:
        return await PaylinkLedgerService.get_balance(
            session,
            account_code=account_code,
            currency=normalized_currency,
        )


async def get_usdt_balance(user_id: str, db: AsyncSession | None = None) -> Decimal:
    return await get_crypto_balance(user_id, USDT_CURRENCY, db=db)


async def _journal_exists_by_ref(db: AsyncSession, ref: str) -> bool:
    res = await db.execute(
        text(
            """
            SELECT journal_id
            FROM paylink.ledger_journal
            WHERE metadata ->> 'ref' = :ref
            LIMIT 1
            """
        ),
        {"ref": ref},
    )
    return res.first() is not None


async def _post_transfer_journal(
    db: AsyncSession,
    *,
    debit_account_code: str,
    credit_account_code: str,
    amount: Decimal,
    currency: str,
    description: str,
    metadata: dict,
) -> None:
    debit_account_id = await _resolve_account_id(db, debit_account_code)
    credit_account_id = await _resolve_account_id(db, credit_account_code)

    journal = await db.execute(
        text(
            """
            INSERT INTO paylink.ledger_journal (tx_id, description, metadata)
            VALUES (:tx_id, :description, CAST(:metadata AS jsonb))
            RETURNING journal_id
            """
        ),
        {
            "tx_id": str(uuid4()),
            "description": description,
            "metadata": json.dumps(metadata),
        },
    )
    journal_id = journal.scalar_one()

    await db.execute(
        text(
            """
            INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
            VALUES
              (:jid, :debit_account_id, 'DEBIT', :amount, :currency),
              (:jid, :credit_account_id, 'CREDIT', :amount, :currency)
            """
        ),
        {
            "jid": journal_id,
            "debit_account_id": debit_account_id,
            "credit_account_id": credit_account_id,
            "amount": Decimal(str(amount)),
            "currency": currency,
        },
    )


async def credit_user_usdc(
    user_id: str,
    amount: Decimal,
    *,
    source_account_code: str = USDC_WALLET_SOURCE_ACCOUNT,
    ref: str | None = None,
    description: str = "Crypto deposit credited to user USDC wallet",
    db: AsyncSession | None = None,
) -> str:
    return await credit_user_crypto(
        user_id,
        amount,
        currency=USDC_CURRENCY,
        source_account_code=source_account_code,
        ref=ref,
        description=description,
        db=db,
    )


async def credit_user_usdt(
    user_id: str,
    amount: Decimal,
    *,
    source_account_code: str = USDT_WALLET_SOURCE_ACCOUNT,
    ref: str | None = None,
    description: str = "Crypto deposit credited to user USDT wallet",
    db: AsyncSession | None = None,
) -> str:
    return await credit_user_crypto(
        user_id,
        amount,
        currency=USDT_CURRENCY,
        source_account_code=source_account_code,
        ref=ref,
        description=description,
        db=db,
    )


async def credit_user_crypto(
    user_id: str,
    amount: Decimal,
    *,
    currency: str,
    source_account_code: str,
    ref: str | None = None,
    description: str | None = None,
    db: AsyncSession | None = None,
) -> str:
    normalized_user_id = str(user_id)
    normalized_amount = Decimal(str(amount))
    normalized_currency = str(currency or "").upper()
    if normalized_amount <= 0:
        raise ValueError("Amount must be > 0")

    effective_ref = ref or f"{normalized_currency}_CREDIT:{normalized_user_id}:{normalized_amount.normalize()}"
    effective_description = description or f"Crypto deposit credited to user {normalized_currency} wallet"

    async def _run(session: AsyncSession) -> str:
        wallet_code = await _get_or_create_crypto_wallet_account_code(
            session,
            normalized_user_id,
            normalized_currency,
        )
        if await _journal_exists_by_ref(session, effective_ref):
            return wallet_code
        await _post_transfer_journal(
            session,
            debit_account_code=source_account_code,
            credit_account_code=wallet_code,
            amount=normalized_amount,
            currency=normalized_currency,
            description=effective_description,
            metadata={
                "event": f"{normalized_currency}_WALLET_CREDIT",
                "ref": effective_ref,
                "user_id": normalized_user_id,
                "currency": normalized_currency,
            },
        )
        return wallet_code

    if db is not None:
        return await _run(db)

    async with async_session_maker() as session:
        wallet_code = await _run(session)
        await session.commit()
        return wallet_code


async def debit_user_usdc(
    user_id: str,
    amount: Decimal,
    *,
    destination_account_code: str,
    ref: str | None = None,
    description: str = "User USDC wallet debit",
    db: AsyncSession | None = None,
) -> str:
    return await debit_user_crypto(
        user_id,
        amount,
        currency=USDC_CURRENCY,
        destination_account_code=destination_account_code,
        ref=ref,
        description=description,
        db=db,
    )


async def debit_user_usdt(
    user_id: str,
    amount: Decimal,
    *,
    destination_account_code: str,
    ref: str | None = None,
    description: str = "User USDT wallet debit",
    db: AsyncSession | None = None,
) -> str:
    return await debit_user_crypto(
        user_id,
        amount,
        currency=USDT_CURRENCY,
        destination_account_code=destination_account_code,
        ref=ref,
        description=description,
        db=db,
    )


async def debit_user_crypto(
    user_id: str,
    amount: Decimal,
    *,
    currency: str,
    destination_account_code: str,
    ref: str | None = None,
    description: str | None = None,
    db: AsyncSession | None = None,
) -> str:
    normalized_user_id = str(user_id)
    normalized_amount = Decimal(str(amount))
    normalized_currency = str(currency or "").upper()
    if normalized_amount <= 0:
        raise ValueError("Amount must be > 0")

    effective_ref = ref or f"{normalized_currency}_DEBIT:{normalized_user_id}:{normalized_amount.normalize()}"
    effective_description = description or f"User {normalized_currency} wallet debit"

    async def _run(session: AsyncSession) -> str:
        wallet_code = await _get_or_create_crypto_wallet_account_code(
            session,
            normalized_user_id,
            normalized_currency,
        )
        if await _journal_exists_by_ref(session, effective_ref):
            return wallet_code
        balance = await get_crypto_balance(normalized_user_id, normalized_currency, db=session)
        if balance < normalized_amount:
            raise ValueError("Insufficient balance")
        await _post_transfer_journal(
            session,
            debit_account_code=wallet_code,
            credit_account_code=destination_account_code,
            amount=normalized_amount,
            currency=normalized_currency,
            description=effective_description,
            metadata={
                "event": f"{normalized_currency}_WALLET_DEBIT",
                "ref": effective_ref,
                "user_id": normalized_user_id,
                "currency": normalized_currency,
            },
        )
        return wallet_code

    if db is not None:
        return await _run(db)

    async with async_session_maker() as session:
        wallet_code = await _run(session)
        await session.commit()
        return wallet_code


async def transfer_usdc(
    from_user: str,
    to_user: str,
    amount: Decimal,
    *,
    ref: str | None = None,
    description: str = "Internal USDC wallet transfer",
    db: AsyncSession | None = None,
) -> tuple[str, str]:
    from_user_id = str(from_user)
    to_user_id = str(to_user)
    normalized_amount = Decimal(str(amount))
    if normalized_amount <= 0:
        raise ValueError("Amount must be > 0")
    if from_user_id == to_user_id:
        raise ValueError("Source and destination users must be different")

    effective_ref = ref or f"USDC_TRANSFER:{from_user_id}:{to_user_id}:{normalized_amount.normalize()}"

    async def _run(session: AsyncSession) -> tuple[str, str]:
        from_wallet = await _get_or_create_wallet_account_code(session, from_user_id)
        to_wallet = await _get_or_create_wallet_account_code(session, to_user_id)
        if await _journal_exists_by_ref(session, effective_ref):
            return from_wallet, to_wallet
        balance = await get_usdc_balance(from_user_id, db=session)
        if balance < normalized_amount:
            raise ValueError("Insufficient balance")
        await _post_transfer_journal(
            session,
            debit_account_code=from_wallet,
            credit_account_code=to_wallet,
            amount=normalized_amount,
            currency=USDC_CURRENCY,
            description=description,
            metadata={
                "event": "USDC_WALLET_TRANSFER",
                "ref": effective_ref,
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
            },
        )
        return from_wallet, to_wallet

    if db is not None:
        return await _run(db)

    async with async_session_maker() as session:
        wallets = await _run(session)
        await session.commit()
        return wallets


async def resolve_usdc_bif_rate(
    db: AsyncSession,
    *,
    override_rate: Decimal | None = None,
) -> Decimal:
    if override_rate is not None:
        candidate = Decimal(str(override_rate))
        if candidate <= 0:
            raise ValueError("Rate must be > 0")
        return candidate

    res = await db.execute(
        text(
            """
            SELECT rate
            FROM paylink.fx_custom_rates
            WHERE origin_currency = 'USDC'
              AND destination_currency = 'BIF'
              AND is_active = TRUE
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """
        )
    )
    row = res.first()
    if not row or row[0] is None:
        return DEFAULT_USDC_BIF_RATE
    rate = Decimal(str(row[0]))
    if rate <= 0:
        return DEFAULT_USDC_BIF_RATE
    return rate


async def convert_usdc_to_bif(
    user_id: str,
    amount_usdc: Decimal,
    *,
    rate: Decimal | None = None,
    ref: str | None = None,
    db: AsyncSession | None = None,
) -> dict:
    normalized_user_id = str(user_id)
    usdc_amount = Decimal(str(amount_usdc))
    if usdc_amount <= 0:
        raise ValueError("Amount must be > 0")

    async def _run(session: AsyncSession) -> dict:
        usdc_wallet = await _get_or_create_wallet_account_code(session, normalized_user_id)
        bif_wallet = await _get_or_create_bif_wallet_account_code(session, normalized_user_id)
        applied_rate = await resolve_usdc_bif_rate(session, override_rate=rate)
        bif_amount = (usdc_amount * applied_rate).quantize(Decimal("0.01"))
        if bif_amount <= 0:
            raise ValueError("Converted BIF amount must be > 0")

        effective_ref = ref or f"USDC_BIF_CONVERT:{normalized_user_id}:{usdc_amount.normalize()}"
        if await _journal_exists_by_ref(session, effective_ref):
            return {
                "user_id": normalized_user_id,
                "amount_usdc": usdc_amount,
                "amount_bif": bif_amount,
                "rate": applied_rate,
                "usdc_wallet": usdc_wallet,
                "bif_wallet": bif_wallet,
                "ref": effective_ref,
            }

        usdc_balance = await get_usdc_balance(normalized_user_id, db=session)
        if usdc_balance < usdc_amount:
            raise ValueError("Insufficient USDC balance")

        # Journal 1 (USDC): Dr USER_USDC / Cr FX_POOL_USDC
        await _post_transfer_journal(
            session,
            debit_account_code=usdc_wallet,
            credit_account_code=FX_POOL_USDC_ACCOUNT,
            amount=usdc_amount,
            currency=USDC_CURRENCY,
            description="Conversion interne USDC -> BIF (USDC leg)",
            metadata={
                "event": "USDC_TO_BIF",
                "leg": "USDC",
                "ref": effective_ref,
                "user_id": normalized_user_id,
                "rate": str(applied_rate),
                "amount_usdc": str(usdc_amount),
                "amount_bif": str(bif_amount),
            },
        )

        # Journal 2 (BIF): Dr FX_POOL_BIF / Cr USER_BIF
        await _post_transfer_journal(
            session,
            debit_account_code=FX_POOL_BIF_ACCOUNT,
            credit_account_code=bif_wallet,
            amount=bif_amount,
            currency=BIF_CURRENCY,
            description="Conversion interne USDC -> BIF (BIF leg)",
            metadata={
                "event": "USDC_TO_BIF",
                "leg": "BIF",
                "ref": effective_ref,
                "user_id": normalized_user_id,
                "rate": str(applied_rate),
                "amount_usdc": str(usdc_amount),
                "amount_bif": str(bif_amount),
            },
        )

        return {
            "user_id": normalized_user_id,
            "amount_usdc": usdc_amount,
            "amount_bif": bif_amount,
            "rate": applied_rate,
            "usdc_wallet": usdc_wallet,
            "bif_wallet": bif_wallet,
            "ref": effective_ref,
        }

    if db is not None:
        return await _run(db)

    async with async_session_maker() as session:
        payload = await _run(session)
        await session.commit()
        return payload
