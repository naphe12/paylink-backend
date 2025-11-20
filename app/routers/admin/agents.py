from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.agent_commissions import AgentCommissions
from app.models.agent_transactions import AgentTransactions
from app.models.agents import Agents
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.admin_notifications import push_admin_notification


router = APIRouter(prefix="/admin/agents", tags=["Admin Agents"])


class CommissionPayload(BaseModel):
    commission_rate: Decimal = Field(gt=0, le=1)

class AgentCreatePayload(BaseModel):
    user_id: UUID
    display_name: str = Field(min_length=2, max_length=80)
    country_code: str = Field(min_length=2, max_length=2)

@router.post("/")
async def create_agent(
    payload: AgentCreatePayload,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    existing = await db.scalar(select(Agents).where(Agents.user_id == payload.user_id))
    if existing:
        raise HTTPException(400, "Agent deja cree pour cet utilisateur")

    user = await db.scalar(select(Users).where(Users.user_id == payload.user_id))
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    agent = Agents(
        user_id=payload.user_id,
        display_name=payload.display_name,
        country_code=payload.country_code.upper(),
        active=True,
    )
    if user.role != "agent":
        user.role = "agent"

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    await push_admin_notification(
        "agent_created",
        db=db,
        user_id=payload.user_id,
        severity="info",
        title="Nouvel agent cree",
        message=f"{agent.display_name} ({user.full_name}) vient d'etre ajoute au reseau.",
        metadata={
            "agent_id": str(agent.agent_id),
            "country_code": agent.country_code,
        },
    )
    await db.commit()

    return {
        "agent_id": str(agent.agent_id),
        "display_name": agent.display_name,
        "country_code": agent.country_code,
        "active": agent.active,
    }


@router.get("/")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    search: str | None = Query(None),
):
    stmt = (
        select(
            Agents.agent_id,
            Agents.display_name,
            Agents.country_code,
            Agents.active,
            Agents.created_at,
            Agents.commission_rate,
            Users.user_id,
            Users.full_name,
            Users.phone_e164,
            func.coalesce(Wallets.available, 0).label("balance"),
            func.coalesce(
                select(func.sum(AgentTransactions.commission))
                .where(AgentTransactions.agent_user_id == Users.user_id)
                .correlate(Agents)
                .scalar_subquery(),
                0,
            ).label("total_commission"),
        )
        .join(Users, Users.user_id == Agents.user_id)
        .join(
            Wallets,
            (Wallets.user_id == Users.user_id) & (Wallets.type == "agent"),
            isouter=True,
        )
    )

    if search:
        stmt = stmt.where(
            (Users.full_name.ilike(f"%{search}%"))
            | (Users.phone_e164.ilike(f"%{search}%"))
            | (Agents.display_name.ilike(f"%{search}%"))
        )

    rows = await db.execute(stmt)
    return [
        {
            "agent_id": str(r.agent_id),
            "display_name": r.display_name,
            "country_code": r.country_code,
            "active": r.active,
            "created_at": r.created_at.isoformat(),
            "commission_rate": float(r.commission_rate or 0.015),
            "user": {
                "user_id": str(r.user_id),
                "full_name": r.full_name,
                "phone": r.phone_e164,
            },
            "balance": float(r.balance or 0),
            "total_commission": float(r.total_commission or 0),
        }
        for r in rows.all()
    ]


@router.patch("/{agent_id}/toggle")
async def toggle_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    agent = await db.scalar(select(Agents).where(Agents.agent_id == agent_id))
    if not agent:
        raise HTTPException(404, "Agent introuvable")

    agent.active = not agent.active
    await db.commit()
    return {"message": "État mis à jour", "active": agent.active}


@router.patch("/{agent_id}/commission")
async def update_agent_commission(
    agent_id: str,
    payload: CommissionPayload,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    agent = await db.scalar(select(Agents).where(Agents.agent_id == agent_id))
    if not agent:
        raise HTTPException(404, "Agent introuvable")

    agent.commission_rate = payload.commission_rate
    await db.commit()
    return {
        "message": "Commission mise à jour",
        "commission_rate": float(agent.commission_rate),
    }


@router.get("/{agent_id}/history")
async def agent_history(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
    limit: int = Query(50, ge=1, le=200),
):
    agent = await db.scalar(select(Agents).where(Agents.agent_id == agent_id))
    if not agent:
        raise HTTPException(404, "Agent introuvable")

    stmt = (
        select(
            AgentTransactions,
            Users.full_name.label("client_name"),
            Users.phone_e164.label("client_phone"),
        )
        .join(Users, Users.user_id == AgentTransactions.client_user_id, isouter=True)
        .where(AgentTransactions.agent_user_id == agent.user_id)
        .order_by(AgentTransactions.created_at.desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)

    commissions_stmt = (
        select(
            AgentCommissions.amount,
            AgentCommissions.operation_type,
            AgentCommissions.created_at,
        )
        .where(AgentCommissions.agent_user_id == agent.user_id)
        .order_by(AgentCommissions.created_at.desc())
        .limit(limit)
    )
    commissions = await db.execute(commissions_stmt)

    return {
        "transactions": [
            {
                "transaction_id": str(tx.transaction_id),
                "direction": tx.direction,
                "amount": float(tx.amount),
                "commission": float(tx.commission),
                "status": tx.status,
                "client_name": client_name,
                "client_phone": client_phone,
                "created_at": tx.created_at.isoformat(),
            }
            for tx, client_name, client_phone in rows.all()
        ],
        "commissions": [
            {
                "amount": float(c.amount),
                "type": c.operation_type,
                "created_at": c.created_at.isoformat(),
            }
            for c in commissions
        ],
    }
