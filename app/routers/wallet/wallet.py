# app/routers/wallet.py
import decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import cast, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.bonus_history import BonusHistory
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.countries import Countries
from app.models.wallet_cash_requests import (
    WalletCashRequestStatus,
    WalletCashRequestType,
    WalletCashRequests,
)
from app.models.wallets import Wallets
from app.models.credit_line_history import CreditLineHistory
from app.schemas.wallet_cash_requests import (
    WalletCashDepositCreate,
    WalletCashRequestRead,
    WalletCashWithdrawCreate,
)
from app.schemas.wallets import WalletsRead, WalletTopUp
from app.schemas.credit_line_history import CreditLineHistoryRead
from app.services.aml import update_risk_score
from app.services.ledger import LedgerLine, LedgerService
from app.services.limits import reset_limits_if_needed
from app.services.risk_engine import calculate_risk_score
from app.services.wallet_history import log_wallet_movement
router = APIRouter()

# 🔹 Obtenir le portefeuille utilisateur
@router.get("/", response_model=WalletsRead)
async def get_wallet(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    ledger = LedgerService(db)
    result = await db.execute(
        select(Wallets)
        .options(selectinload(Wallets.user))
        .where(Wallets.user_id == current_user.user_id)
    )
    wallet = result.scalar_one_or_none()

    # 🔸 Crée un portefeuille si inexistant
    if not wallet:
        wallet = Wallets(
            user_id=current_user.user_id,
            type="personal",
            currency_code="EUR",
            available=decimal.Decimal("0.00"),
            pending=decimal.Decimal("0.00")
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
        wallet.user = current_user

    await ledger.ensure_wallet_account(wallet)

    user_country_code = None
    if wallet.user:
        user_country_code = wallet.user.country_code
    elif wallet.user_id:
        user_country_code = await db.scalar(
            select(Users.country_code).where(Users.user_id == wallet.user_id)
        )

    display_currency = wallet.currency_code
    user_country_currency = None
    if user_country_code:
        user_country_currency = await db.scalar(
            select(Countries.currency_code).where(Countries.country_code == user_country_code)
        )
        if user_country_currency:
            display_currency = user_country_currency

    payload = jsonable_encoder(wallet)
    payload["display_currency_code"] = display_currency
    payload["user_country_code"] = user_country_code
    payload["user_country_currency_code"] = user_country_currency
    return payload


# 🔹 Recharger le portefeuille
@router.post("/topup", response_model=WalletsRead)
async def topup_wallet(
    topup: WalletTopUp,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    ledger = LedgerService(db)
    result = await db.execute(
        select(Wallets).where(Wallets.user_id == current_user.user_id)
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    await reset_limits_if_needed(db, current_user)

    amount = Decimal(topup.amount)
    if current_user.used_daily + amount > current_user.daily_limit:
        raise HTTPException(403, "⚠️ Limite journalière dépassée")

    if current_user.used_monthly + amount > current_user.monthly_limit:
        raise HTTPException(403, "⚠️ Limite mensuelle dépassée")

    # ✅ Si OK → enregistrer
    current_user.used_daily += amount
    current_user.used_monthly += amount
    wallet.available += topup.amount
    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="credit",
        operation_type="user_topup",
        description="Recharge manuelle",
    )
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_in_account = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_IN)
    metadata = {
        "operation": "user_topup",
        "wallet_id": str(wallet.wallet_id),
        "user_id": str(current_user.user_id),
    }
    if movement:
        metadata["movement_id"] = str(movement.transaction_id)
    await ledger.post_journal(
        tx_id=None,
        description="Recharge wallet utilisateur",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=cash_in_account,
                direction="debit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
            LedgerLine(
                account=wallet_account,
                direction="credit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
        ],
    )
    await update_risk_score(db, current_user)
    await db.commit()
    await db.refresh(wallet)

    # ✅ Conversion JSON safe
    return jsonable_encoder(wallet)



@router.post("/cash/deposit", response_model=WalletCashRequestRead)
async def request_cash_deposit(
    payload: WalletCashDepositCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    amount = decimal.Decimal(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")

    request = WalletCashRequests(
        user_id=current_user.user_id,
        wallet_id=wallet.wallet_id,
        type=WalletCashRequestType.DEPOSIT,
        status=WalletCashRequestStatus.PENDING,
        amount=amount,
        fee_amount=decimal.Decimal("0"),
        total_amount=amount,
        currency_code=wallet.currency_code,
        note=payload.note,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request


@router.post("/cash/withdraw", response_model=WalletCashRequestRead)
async def request_cash_withdraw(
    payload: WalletCashWithdrawCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    amount = decimal.Decimal(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")

    fee = (amount * decimal.Decimal("0.0625")).quantize(decimal.Decimal("0.000001"))
    total = amount + fee
    wallet_balance = decimal.Decimal(wallet.available or 0)
    if wallet_balance < total:
        raise HTTPException(status_code=400, detail="Solde insuffisant pour ce retrait")

    request = WalletCashRequests(
        user_id=current_user.user_id,
        wallet_id=wallet.wallet_id,
        type=WalletCashRequestType.WITHDRAW,
        status=WalletCashRequestStatus.PENDING,
        amount=amount,
        fee_amount=fee,
        total_amount=total,
        currency_code=wallet.currency_code,
        mobile_number=payload.mobile_number,
        provider_name=payload.provider_name,
        note=payload.note,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request


@router.get("/cash/requests", response_model=list[WalletCashRequestRead])
async def list_cash_requests(
    request_type: WalletCashRequestType | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    stmt = (
        select(WalletCashRequests)
        .where(WalletCashRequests.user_id == current_user.user_id)
        .order_by(WalletCashRequests.created_at.desc())
    )
    if request_type:
        stmt = stmt.where(WalletCashRequests.type == request_type)

    requests = (await db.execute(stmt)).scalars().all()
    return requests





@router.post("/transfer")
async def transfer_money(
    to_email: str,
    amount: decimal.Decimal,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    ledger = LedgerService(db)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")

    sender_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not sender_wallet or sender_wallet.available < amount:
        raise HTTPException(status_code=400, detail="Solde insuffisant")

    receiver_user = await db.scalar(select(Users).where(Users.email == to_email))
    if not receiver_user:
        raise HTTPException(status_code=404, detail="Destinataire introuvable")

    receiver_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == receiver_user.user_id))
    if not receiver_wallet:
        raise HTTPException(status_code=404, detail="Portefeuille destinataire introuvable")

    # 💱 Transfert atomique
    sender_wallet.available -= amount
    receiver_wallet.available += amount
    sender_movement = await log_wallet_movement(
        db,
        wallet=sender_wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="transfer_send",
        reference=receiver_user.email,
        description=f"Transfert vers {receiver_user.email}",
    )
    receiver_movement = await log_wallet_movement(
        db,
        wallet=receiver_wallet,
        user_id=receiver_user.user_id,
        amount=amount,
        direction="credit",
        operation_type="transfer_receive",
        reference=current_user.email,
        description=f"Transfert de {current_user.email}",
    )
    sender_account = await ledger.ensure_wallet_account(sender_wallet)
    receiver_account = await ledger.ensure_wallet_account(receiver_wallet)
    metadata = {
        "operation": "internal_transfer",
        "sender_wallet_id": str(sender_wallet.wallet_id),
        "receiver_wallet_id": str(receiver_wallet.wallet_id),
        "sender_user_id": str(current_user.user_id),
        "receiver_user_id": str(receiver_user.user_id),
    }
    if sender_movement:
        metadata["sender_movement_id"] = str(sender_movement.transaction_id)
    if receiver_movement:
        metadata["receiver_movement_id"] = str(receiver_movement.transaction_id)
    await ledger.post_journal(
        tx_id=None,
        description=f"Transfert interne vers {receiver_user.email}",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=amount,
                currency_code=sender_wallet.currency_code,
            ),
            LedgerLine(
                account=receiver_account,
                direction="credit",
                amount=amount,
                currency_code=receiver_wallet.currency_code,
            ),
        ],
    )

    # 🧾 Enregistrement des transactions
    tx_sender = Transactions(
        transaction_id=uuid.uuid4(),
        user_id=current_user.user_id,
        type="transfer",
        amount=-amount,
        currency="EUR",
        status="completed",
        details={"to": receiver_user.email}
    )
    tx_receiver = Transactions(
        transaction_id=uuid.uuid4(),
        user_id=receiver_user.user_id,
        type="transfer",
        amount=amount,
        currency="EUR",
        status="completed",
        details={"from": current_user.email}
    )
    db.add_all([tx_sender, tx_receiver])

    await db.commit()
    from app.utils.notify import send_notification

# Après le commit
    await send_notification(str(receiver_user.user_id), f"💸 Vous avez reçu {amount}€ de {current_user.email}")

    return {"status": "success", "message": f"Transfert de {amount}€ vers {to_email} effectué ✅"}




@router.post("/topup/mobilemoney")
async def topup_mobilemoney(
    amount: decimal.Decimal,
    provider: str,
    phone_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    ledger = LedgerService(db)
    wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable")

    # Simulation succès agrégateur (à remplacer par API réelle)
    wallet.available += amount

    movement = await log_wallet_movement(
        db,
        wallet=wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="credit",
        operation_type="mobile_topup",
        reference=provider,
        description=f"Recharge {provider} {phone_number}",
    )
    wallet_account = await ledger.ensure_wallet_account(wallet)
    cash_in_account = await ledger.get_account_by_code(settings.LEDGER_ACCOUNT_CASH_IN)
    metadata = {
        "operation": "mobile_topup",
        "wallet_id": str(wallet.wallet_id),
        "user_id": str(current_user.user_id),
        "provider": provider,
        "phone_number": phone_number,
    }
    if movement:
        metadata["movement_id"] = str(movement.transaction_id)
    await ledger.post_journal(
        tx_id=None,
        description=f"Recharge mobile money {provider}",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=cash_in_account,
                direction="debit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
            LedgerLine(
                account=wallet_account,
                direction="credit",
                amount=amount,
                currency_code=wallet.currency_code,
            ),
        ],
    )

    #risk = await calculate_risk_score(db, current_user.user_id)
    await update_risk_score(db, current_user, amount,channel='cash')

    db.add(Transactions(
        transaction_id=uuid.uuid4(),
        user_id=current_user.user_id,
        type="topup",
        amount=amount,
        currency="EUR",
        status="completed",
        details={"provider": provider, "phone": phone_number}
    ))
    await db.commit()

    return {"message": f"Recharge de {amount}€ via {provider} réussie ✅"}

@router.get("/credit-status")
async def get_credit_status(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    result = await db.execute(select(Wallets).where(Wallets.user_id == current_user.user_id))
    wallet = result.scalar_one_or_none()

    credit_available = (current_user.credit_limit or 0) - (current_user.credit_used or 0)
    total_available = (wallet.available or 0) + credit_available

    return {
        "wallet_balance": float(wallet.available),
        "credit_limit": float(current_user.credit_limit),
        "credit_used": float(current_user.credit_used),
        "credit_available": float(credit_available),
        "total_available": float(total_available)
    }


@router.get("/credit/history", response_model=list[CreditLineHistoryRead])
async def get_credit_history(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    stmt = (
        select(CreditLineHistory)
        .where(CreditLineHistory.user_id == current_user.user_id)
        .order_by(CreditLineHistory.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        CreditLineHistoryRead.model_validate(row, from_attributes=True)
        for row in rows
    ]
@router.get("/bonus/history")
async def bonus_history(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    result = await db.execute(
        select(BonusHistory)
        .where(BonusHistory.user_id == current_user.user_id)
        .order_by(BonusHistory.created_at.desc())
    )
    return result.scalars().all()


@router.get("/bonus")
async def get_bonus_balance(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    result = await db.execute(select(Wallets).where(Wallets.user_id == current_user.user_id))
    wallet = result.scalar_one()
    return {"bonus_balance": wallet.bonus_balance}

from app.models.bonus_history import BonusHistory


@router.post("/bonus/send")
async def send_bonus(
    recipient: str,
    amount_bif: decimal.Decimal,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    # Trouver le wallet émetteur
    sender_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == current_user.user_id))
    if sender_wallet.bonus_balance < amount_bif:
        raise HTTPException(400, "Solde bonus insuffisant")

    # Trouver le destinataire
    recipient_user = await db.scalar(
        select(Users).where((Users.email == recipient) | (Users.phone_e164 == recipient))
    )
    if not recipient_user:
        raise HTTPException(404, "Destinataire introuvable")

    recipient_wallet = await db.scalar(select(Wallets).where(Wallets.user_id == recipient_user.user_id))

    # Mise à jour des soldes
    sender_wallet.bonus_balance -= amount_bif
    recipient_wallet.bonus_balance += amount_bif

    # Historique
    db.add(BonusHistory(user_id=current_user.user_id, amount_bif=amount_bif, source="used"))
    db.add(BonusHistory(user_id=recipient_user.user_id, amount_bif=amount_bif, source="earned"))

    await db.commit()
    return {"status": "success"}


from sqlalchemy import or_, select

from app.models.transactions import Transactions
from app.models.wallets import Wallets
from app.schemas.transactions import TransactionListItem


@router.get("/transactions", response_model=list[TransactionListItem])
async def get_wallet_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    # 1. Récupérer le wallet du user
    wallet_result = await db.execute(
        select(Wallets).where(Wallets.user_id == current_user.user_id)
    )
    wallet = wallet_result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet introuvable")

    wallet_id = wallet.wallet_id

    # 2. Récupérer toutes transactions liées à ce wallet
    tx_result = await db.execute(
        select(Transactions)
        .where(
            or_(
                Transactions.initiated_by == current_user.user_id,
                Transactions.sender_wallet == wallet_id,
                Transactions.receiver_wallet == wallet_id,
            )
        )
        .order_by(Transactions.created_at.desc())
    )
    txs = tx_result.scalars().all()

    # 3. Normaliser direction + structure
    response = []
    for tx in txs:
        direction = "in" if tx.receiver_wallet == wallet_id else "out"

        response.append({
            "tx_id": str(tx.tx_id),
            "amount": float(tx.amount),
            "currency_code": tx.currency_code,
            "direction": direction,
            "description": tx.description or "",
            "status": tx.status,
            "created_at": tx.created_at,
        })

    return response

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.transactions import Transactions
from app.models.wallets import Wallets
from app.schemas.transactions import TransactionSend
from app.services.limits import reset_limits_if_needed
from fastapi import HTTPException

@router.post("/send")
async def send_money(
    tx: TransactionSend,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    ledger = LedgerService(db)
    await calculate_risk_score(db, current_user.user_id)
    if current_user.status == "frozen":
        raise HTTPException(423, "Votre compte est gelé pour raisons de sécurité.")
    # 1) Trouver le wallet du sender
    result = await db.execute(
        select(Wallets).where(Wallets.user_id == current_user.user_id)
    )
    sender_wallet = result.scalar_one_or_none()
    if not sender_wallet:
        raise HTTPException(404, "Sender wallet not found")

    # 2) Trouver destinataire par email / téléphone
    result = await db.execute(
        select(Users).where(
            (Users.email == tx.to_identifier) | (Users.phone_e164 == tx.to_identifier)
        )
    )
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(404, "Destinataire introuvable")

    result = await db.execute(
        select(Wallets).where(Wallets.user_id == receiver.user_id)
    )
    receiver_wallet = result.scalar_one_or_none()

    await reset_limits_if_needed(db, current_user)
    # 3) Vérifier solde suffisant
    amount = Decimal(tx.amount)
    if sender_wallet.available < amount:
        raise HTTPException(400, "Solde insuffisant")
    
    if current_user.used_daily + amount > current_user.daily_limit:
        raise HTTPException(403, "⚠️ Limite journalière dépassée")
    
    if current_user.used_monthly + amount > current_user.monthly_limit:
        raise HTTPException(403, "⚠️ Limite mensuelle dépassée")

    # 4) Effectuer le transfert
    sender_wallet.available -= amount
    receiver_wallet.available += amount

    sender_movement = await log_wallet_movement(
        db,
        wallet=sender_wallet,
        user_id=current_user.user_id,
        amount=amount,
        direction="debit",
        operation_type="wallet_send",
        reference=tx.to_identifier,
        description=f"Envoi vers {tx.to_identifier}",
    )
    receiver_movement = await log_wallet_movement(
        db,
        wallet=receiver_wallet,
        user_id=receiver.user_id,
        amount=amount,
        direction="credit",
        operation_type="wallet_receive",
        reference=current_user.email,
        description=f"Réception de {current_user.email}",
    )

    new_tx = Transactions(
        amount=amount,
        currency_code=sender_wallet.currency_code,
        sender_wallet=sender_wallet.wallet_id,
        receiver_wallet=receiver_wallet.wallet_id,
        initiated_by=current_user.user_id,
        description=tx.description or "Transfert PayLink",
        channel="internal",
        status="succeeded"
    )
    db.add(new_tx)
    await db.flush()
    sender_account = await ledger.ensure_wallet_account(sender_wallet)
    receiver_account = await ledger.ensure_wallet_account(receiver_wallet)
    metadata = {
        "operation": "wallet_send",
        "sender_wallet_id": str(sender_wallet.wallet_id),
        "receiver_wallet_id": str(receiver_wallet.wallet_id),
        "sender_user_id": str(current_user.user_id),
        "receiver_user_id": str(receiver.user_id),
        "identifier": tx.to_identifier,
        "transaction_id": str(new_tx.tx_id),
    }
    if sender_movement:
        metadata["sender_movement_id"] = str(sender_movement.transaction_id)
    if receiver_movement:
        metadata["receiver_movement_id"] = str(receiver_movement.transaction_id)
    metadata = {k: v for k, v in metadata.items() if v is not None}
    await ledger.post_journal(
        tx_id=new_tx.tx_id,
        description=f"Transfert interne vers {tx.to_identifier}",
        metadata=metadata,
        entries=[
            LedgerLine(
                account=sender_account,
                direction="debit",
                amount=amount,
                currency_code=sender_wallet.currency_code,
            ),
            LedgerLine(
                account=receiver_account,
                direction="credit",
                amount=amount,
                currency_code=receiver_wallet.currency_code,
            ),
        ],
    )
    # ✅ Si OK → enregistrer
    current_user.used_daily += amount
    current_user.used_monthly += amount
    await update_risk_score(db, current_user)
    await db.commit()

    return {"message": "✅ Transfert effectué avec succès"}


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.wallets import Wallets
from app.models.wallet_transactions import WalletTransactions
from uuid import UUID



from datetime import datetime, timedelta
from fastapi import Query

@router.get("/ledger/{wallet_id}")
async def get_wallet_ledger(
    wallet_id: UUID,
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):

    # Vérifier que le wallet appartient à l'utilisateur
    wallet = await db.get(Wallets, wallet_id)
    if not wallet or wallet.user_id != current_user.user_id:
        raise HTTPException(403, "Accès refusé")

    q = (
        select(
            WalletTransactions.transaction_id,
            WalletTransactions.amount,
            WalletTransactions.direction,
            WalletTransactions.balance_after,
            WalletTransactions.created_at,
            WalletTransactions.reference,
            WalletTransactions.operation_type,
            WalletTransactions.description,
        )
        .where(WalletTransactions.wallet_id == wallet_id)
        .order_by(WalletTransactions.created_at.desc())
        .limit(limit)
    )
    if from_date:
       q = q.where(WalletTransactions.created_at >= from_date)
    if to_date:
       q = q.where(WalletTransactions.created_at <= to_date)

    if search:
        pattern = f"%{search}%"
        q = q.where(
            WalletTransactions.reference.ilike(pattern)
            | WalletTransactions.operation_type.ilike(pattern)
            | WalletTransactions.description.ilike(pattern)
            | WalletTransactions.amount.cast(String).ilike(pattern)
        )

    rows = (await db.execute(q)).mappings().all()
    for r in rows:
       print(r.direction)


    return [
        {
            "transaction_id": r.transaction_id,
            "amount": float(r.amount),
            "direction": r.direction,  # debit / credit
            "balance_after": float(r.balance_after),
            "created_at": r.created_at.isoformat(),
            "reference": r.reference,
            "operation_type": r.operation_type,
            "description": r.description or "",
        }
        for r in rows
    ]


@router.get("/limits")
async def get_limits(current_user: Users = Depends(get_current_user)):
    return {
        "daily_limit": float(current_user.daily_limit),
        "monthly_limit": float(current_user.monthly_limit),
        "used_daily": float(current_user.used_daily),
        "used_monthly": float(current_user.used_monthly),
    }

@router.get("/risk")
async def get_risk_score(current_user: Users = Depends(get_current_user)):
    return {"risk_score": current_user.risk_score}











