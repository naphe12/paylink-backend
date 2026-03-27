# app/routers/agent.py
from datetime import datetime, timezone
import base64
import json
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, update, select, func, or_
from app.core.database import get_db
from app.core.security import agent_required, get_current_user
from app.models.agent_transactions import AgentTransactions
from app.models.countries import Countries
from app.models.users import Users
from app.services.agent_ops import compute_agent_commission
from app.services.limits import guard_and_increment_limits
from app.services.aml import update_risk_score
from app.dependencies.auth import get_current_agent
from pydantic import BaseModel, Field
from decimal import Decimal
from app.models.agent_commissions import AgentCommissions
from app.models.wallets import Wallets
from app.models.transactions import Transactions
from app.models.agents import Agents
from app.schemas.users import UsersCreate, UsersRead
from app.services.idempotency_service import (
    acquire_idempotency,
    compute_request_hash,
    store_idempotency_response,
)
from app.services.user_provisioning import create_client_user



router = APIRouter(tags=["agent"])

QR_ALLOWED_STATUSES = {"initiated", "pending"}
QR_ALLOWED_CHANNELS = {"mobile_money", "cash", "internal"}

async def _require_agent(db: AsyncSession, user: Users) -> Agents:
    agent = await db.scalar(select(Agents).where(Agents.user_id == user.user_id))
    if not agent:
        raise HTTPException(404, "Profil agent introuvable pour cet utilisateur")
    return agent

class AgentCashPayload(BaseModel):
    client_user_id: str
    amount: Decimal = Field(gt=0)


class AgentCashDepositCreate(BaseModel):
    user_id: UUID
    amount: Decimal = Field(gt=0)
    note: str | None = None


class AgentQrScanRequest(BaseModel):
    qr_payload: str | None = None
    tx_id: UUID | None = None


class AgentQrConfirmRequest(BaseModel):
    tx_id: UUID
    pin: str | None = None


@router.post(
    "/clients",
    response_model=UsersRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(agent_required)],
)
async def create_client_from_agent(
    payload: UsersCreate,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_user),
):
    await _require_agent(db, current_agent)
    try:
        user = await create_client_user(db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(user)
    return UsersRead.model_validate(user, from_attributes=True)


@router.post("/cash-in", dependencies=[Depends(agent_required)])
async def agent_cashin(
    body: AgentCashPayload,
    db: AsyncSession = Depends(get_db),
    agent: Users = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    agent_row = await _require_agent(db, agent)
    agent_id = agent_row.agent_id
    client = await db.scalar(select(Users).where(Users.user_id==body.client_user_id))
    if not client: raise HTTPException(404, "Client introuvable")
    if str(agent.user_id) == str(client.user_id):
        raise HTTPException(400, "Agent ≠ Client")

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "operation": "agent_cashin",
                "agent_id": str(agent.user_id),
                "client_user_id": str(body.client_user_id),
                "amount": str(body.amount),
            }
        )
        scoped_idempotency_key = f"agent_cashin:{agent.user_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(status_code=409, detail="Idempotency-Key deja utilisee avec un payload different.")
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

    amount = float(body.amount)
    await guard_and_increment_limits(db, client, amount)
    commission = compute_agent_commission(amount, agent.agents.commission_rate if agent.agents else None)

    # AML & risque
    score = await update_risk_score(db, client, amount, channel="agent")

    # Enregistrer l’opération (tu peux ensuite créditer le wallet du client et débiter le float agent)
    await db.execute(insert(AgentTransactions).values(
        agent_id=agent_id,
        client_user_id=client.user_id,
        direction="cashin",
        tx_type="cashin",
        amount=amount,
        commission=commission,
        status="completed"
    ))
    response_payload = {"message": "Cash-in effectue", "commission": str(commission), "risk_score": score}
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
    await db.commit()
    return response_payload

@router.post("/cash-out", dependencies=[Depends(agent_required)])
async def agent_cashout(
    body: AgentCashPayload,
    db: AsyncSession = Depends(get_db),
    agent: Users = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    agent_row = await _require_agent(db, agent)
    agent_id = agent_row.agent_id
    client = await db.scalar(select(Users).where(Users.user_id==body.client_user_id))
    if not client: raise HTTPException(404, "Client introuvable")

    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "operation": "agent_cashout",
                "agent_id": str(agent.user_id),
                "client_user_id": str(body.client_user_id),
                "amount": str(body.amount),
            }
        )
        scoped_idempotency_key = f"agent_cashout:{agent.user_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(status_code=409, detail="Idempotency-Key deja utilisee avec un payload different.")
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

    amount = float(body.amount)
    await guard_and_increment_limits(db, client, amount)
    commission = compute_agent_commission(amount, agent.agents.commission_rate if agent.agents else None)

    score = await update_risk_score(db, client, amount, channel="agent")

    await db.execute(insert(AgentTransactions).values(
        agent_id=agent_id,
        client_user_id=client.user_id,
        direction="cashout",
        tx_type="cashout",
        amount=amount,
        commission=commission,
        status="completed"
    ))
    response_payload = {"message": "Cash-out effectue", "commission": str(commission), "risk_score": score}
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
    await db.commit()
    return response_payload


@router.get("/cash/users")
async def agent_cash_users(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    # Ensure caller has an agent profile.
    await _require_agent(db, current_agent)
    stmt = (
        select(
            Users.user_id,
            Users.full_name,
            Users.email,
            Users.phone_e164,
            Users.country_code,
            Countries.currency_code.label("country_currency_code"),
        )
        .join(Countries, Countries.country_code == Users.country_code, isouter=True)
        .order_by(Users.created_at.desc())
        .limit(limit)
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = (
            select(
                Users.user_id,
                Users.full_name,
                Users.email,
                Users.phone_e164,
                Users.country_code,
                Countries.currency_code.label("country_currency_code"),
            )
            .join(Countries, Countries.country_code == Users.country_code, isouter=True)
            .where(
                or_(
                    Users.full_name.ilike(pattern),
                    Users.email.ilike(pattern),
                    Users.phone_e164.ilike(pattern),
                )
            )
            .order_by(Users.created_at.desc())
            .limit(limit)
        )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "full_name": r.full_name,
            "email": r.email,
            "phone_e164": r.phone_e164,
            "country_code": r.country_code,
            "currency_code": r.country_currency_code or "EUR",
        }
        for r in rows
    ]


@router.post("/cash/deposit")
async def agent_cash_deposit_direct(
    payload: AgentCashDepositCreate,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    agent_row = await _require_agent(db, current_agent)
    scoped_idempotency_key = None
    if idempotency_key and idempotency_key.strip():
        raw_key = idempotency_key.strip()
        payload_hash = compute_request_hash(
            {
                "operation": "agent_cash_deposit_direct",
                "agent_id": str(current_agent.user_id),
                "user_id": str(payload.user_id),
                "amount": str(payload.amount),
                "note": payload.note,
            }
        )
        scoped_idempotency_key = f"agent_cash_deposit_direct:{current_agent.user_id}:{raw_key}"
        idem = await acquire_idempotency(
            db,
            key=scoped_idempotency_key,
            request_hash=payload_hash,
        )
        if idem.conflict:
            raise HTTPException(status_code=409, detail="Idempotency-Key deja utilisee avec un payload different.")
        if idem.replay_payload is not None:
            return idem.replay_payload
        if idem.in_progress:
            raise HTTPException(status_code=409, detail="Requete dupliquee en cours de traitement.")

    user = await db.scalar(select(Users).where(Users.user_id == payload.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user_country_currency = await db.scalar(
        select(Countries.currency_code).where(Countries.country_code == user.country_code)
    )

    wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == payload.user_id,
            Wallets.type == "consumer",
        )
    )
    if not wallet:
        wallet = await db.scalar(select(Wallets).where(Wallets.user_id == payload.user_id))
    if not wallet:
        wallet = Wallets(
            user_id=payload.user_id,
            type="consumer",
            currency_code=(user_country_currency or "EUR"),
            available=Decimal("0"),
            pending=Decimal("0"),
        )
        db.add(wallet)
        await db.flush()

    wallet.available = Decimal(wallet.available or 0) + payload.amount

    await db.execute(insert(AgentTransactions).values(
        agent_id=agent_row.agent_id,
        client_user_id=user.user_id,
        direction="cashin",
        tx_type="cashin",
        amount=float(payload.amount),
        commission=0,
        status="completed",
    ))
    response_payload = {
        "message": "Depot cash effectue",
        "user_id": str(user.user_id),
        "amount": float(payload.amount),
        "currency": wallet.currency_code,
        "new_balance": float(wallet.available),
    }
    if scoped_idempotency_key:
        await store_idempotency_response(
            db,
            key=scoped_idempotency_key,
            status_code=200,
            payload=response_payload,
        )
    await db.commit()
    return response_payload

@router.get("/dashboard")
async def agent_dashboard(
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent)
):
    agent_row = await _require_agent(db, current_agent)
    agent_id = agent_row.agent_id
    # Wallet Agent
    wallet = await db.scalar(
        select(Wallets).where(
            Wallets.user_id == current_agent.user_id,
            Wallets.type == "agent"
        )
    )

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def tx_sum(direction: str, start_date: datetime | None = None):
        stmt = select(func.coalesce(func.sum(AgentTransactions.amount), 0)).where(
            AgentTransactions.agent_id == agent_id,
            AgentTransactions.direction == direction,
        )
        if start_date:
            stmt = stmt.where(AgentTransactions.created_at >= start_date)
        return stmt

    cashin_today = await db.scalar(tx_sum("cashin", day_start))
    cashin_month = await db.scalar(tx_sum("cashin", month_start))
    cashout_today = await db.scalar(tx_sum("cashout", day_start))
    cashout_month = await db.scalar(tx_sum("cashout", month_start))

    total_commissions = await db.scalar(
        select(func.coalesce(func.sum(AgentCommissions.amount), 0)).where(
            AgentCommissions.agent_user_id == current_agent.user_id
        )
    )

    recent = await db.execute(
        select(AgentTransactions)
        .where(AgentTransactions.agent_id == agent_id)
        .order_by(AgentTransactions.created_at.desc())
        .limit(10)
    )

    return {
        "balance": float(wallet.available) if wallet else 0,
        "metrics": {
            "cashin_today": float(cashin_today or 0),
            "cashin_month": float(cashin_month or 0),
            "cashout_today": float(cashout_today or 0),
            "cashout_month": float(cashout_month or 0),
            "total_commission": float(total_commissions or 0),
        },
        "recent": [
            {
                "transaction_id": str(r.transaction_id),
                "amount": float(r.amount),
                "direction": r.direction,
                "commission": float(r.commission),
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in recent.scalars().all()
        ],
    }


@router.get("/history", dependencies=[Depends(agent_required)])
async def agent_history(
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    phone: str | None = Query(None),
    min_amount: float | None = Query(None),
    max_amount: float | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    agent_row = await _require_agent(db, current_agent)
    agent_id = agent_row.agent_id
    filters = [AgentTransactions.agent_id == agent_id]

    if date_from:
        filters.append(AgentTransactions.created_at >= date_from)
    if date_to:
        filters.append(AgentTransactions.created_at <= date_to)
    if min_amount is not None:
        filters.append(AgentTransactions.amount >= min_amount)
    if max_amount is not None:
        filters.append(AgentTransactions.amount <= max_amount)

    stmt = (
        select(
            AgentTransactions,
            Users.full_name.label("client_name"),
            Users.phone_e164.label("client_phone"),
            Transactions.currency_code.label("currency_code"),
        )
        .join(Users, Users.user_id == AgentTransactions.client_user_id)
        .outerjoin(Transactions, Transactions.tx_id == AgentTransactions.related_tx)
        .where(*filters)
        .order_by(AgentTransactions.created_at.desc())
        .limit(limit)
    )

    if phone:
        stmt = stmt.where(Users.phone_e164.ilike(f"%{phone}%"))

    rows = await db.execute(stmt)

    operations = []
    for tx, client_name, client_phone, currency_code in rows.all():
        operations.append(
            {
                "transaction_id": str(tx.transaction_id),
                "direction": tx.direction,
                "amount": float(tx.amount),
                "commission": float(tx.commission),
                "currency_code": str(currency_code or "").upper() or None,
                "status": tx.status,
                "client_name": client_name,
                "client_phone": client_phone,
                "created_at": tx.created_at.isoformat(),
            }
        )

    return {
        "total_commission": float(
            sum(op["commission"] for op in operations)
        ),
        "operations": operations,
    }


@router.post("/qr/scan", dependencies=[Depends(agent_required)])
async def agent_qr_scan(
    payload: AgentQrScanRequest,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    _ = await _require_agent(db, current_agent)
    tx_id = _extract_tx_id(payload)
    tx, client_name, client_phone = await _fetch_pending_qr_transaction(db, tx_id)

    return {
        "tx_id": str(tx.tx_id),
        "amount": float(tx.amount),
        "currency": tx.currency_code,
        "status": tx.status,
        "description": tx.description,
        "requires_pin": False,
        "client": {
            "user_id": str(tx.initiated_by) if tx.initiated_by else None,
            "name": client_name,
            "phone": client_phone,
        },
    }


@router.post("/qr/confirm", dependencies=[Depends(agent_required)])
async def agent_qr_confirm(
    payload: AgentQrConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    agent_row = await _require_agent(db, current_agent)
    agent_id = agent_row.agent_id
    tx, client_name, client_phone = await _fetch_pending_qr_transaction(db, payload.tx_id)

    commission_value = compute_agent_commission(
        float(tx.amount),
        current_agent.agents.commission_rate if current_agent.agents else None,
    )

    await db.execute(
        insert(AgentTransactions).values(
            agent_id=agent_id,
            client_user_id=tx.initiated_by,
            direction="mobile_money",
            tx_type="mobile_money",
            amount=tx.amount,
            commission=commission_value,
            status="completed",
            client_phone=client_phone,
            related_tx=tx.tx_id,
        )
    )

    tx.status = "succeeded"
    tx.updated_at = datetime.utcnow()

    await db.commit()

    return {
        "message": "Paiement validé",
        "tx_id": str(tx.tx_id),
        "amount": float(tx.amount),
        "commission": float(commission_value),
    }


def _extract_tx_id(payload: AgentQrScanRequest) -> UUID:
    if payload.tx_id:
        return payload.tx_id
    if not payload.qr_payload:
        raise HTTPException(400, "QR invalide")

    raw = payload.qr_payload.strip()
    try:
        return UUID(raw)
    except ValueError:
        pass

    try:
        decoded = base64.b64decode(raw).decode()
    except Exception:
        decoded = raw

    try:
        data = json.loads(decoded)
        tx_value = data.get("tx_id") or data.get("transaction_id")
        if tx_value:
            return UUID(tx_value)
    except Exception:
        pass

    try:
        return UUID(decoded.strip())
    except Exception:
        raise HTTPException(400, "QR invalide")


async def _fetch_pending_qr_transaction(
    db: AsyncSession, tx_id: UUID
) -> tuple[Transactions, Optional[str], Optional[str]]:
    stmt = (
        select(
            Transactions,
            Users.full_name.label("client_name"),
            Users.phone_e164.label("client_phone"),
        )
        .join(Users, Users.user_id == Transactions.initiated_by, isouter=True)
        .where(Transactions.tx_id == tx_id)
    )

    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(404, "Transaction introuvable")

    tx, client_name, client_phone = row
    if tx.status not in QR_ALLOWED_STATUSES:
        raise HTTPException(400, "Transaction déjà traitée")
    if tx.channel not in QR_ALLOWED_CHANNELS:
        raise HTTPException(400, "Transaction non éligible au mode agent")

    return tx, client_name, client_phone


