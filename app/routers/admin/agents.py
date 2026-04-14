from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.dependencies.step_up import get_admin_step_up_method, require_admin_step_up
from app.models.agent_commissions import AgentCommissions
from app.models.agent_transactions import AgentTransactions
from app.models.agents import Agents
from app.models.users import Users
from app.models.wallets import Wallets
from app.services.admin_notifications import push_admin_notification
from app.services.audit_service import audit_log
from app.services.auth_sessions import get_request_ip, get_request_user_agent


router = APIRouter(prefix="/admin/agents", tags=["Admin Agents"])


class CommissionPayload(BaseModel):
    commission_rate: Decimal = Field(gt=0, le=1)


class AgentCreatePayload(BaseModel):
    user_id: UUID
    display_name: str = Field(min_length=2, max_length=80)
    country_code: str = Field(min_length=2, max_length=2)


def _agent_state(agent: Agents) -> dict:
    return {
        "active": bool(getattr(agent, "active", False)),
        "commission_rate": float(getattr(agent, "commission_rate", 0) or 0),
        "country_code": str(getattr(agent, "country_code", "") or ""),
        "display_name": str(getattr(agent, "display_name", "") or ""),
    }


async def _audit_admin_agent_action(
    *,
    db: AsyncSession,
    request: Request,
    admin: Users,
    agent: Agents,
    action: str,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    await audit_log(
        db,
        actor_user_id=str(getattr(admin, "user_id", "") or "") or None,
        actor_role=str(getattr(admin, "role", "") or "") or None,
        action=action,
        entity_type="agent",
        entity_id=str(agent.agent_id),
        before_state=before_state,
        after_state={**(after_state or {}), "step_up_method": get_admin_step_up_method(request)},
        ip=get_request_ip(request),
        user_agent=get_request_user_agent(request),
    )


@router.post("/")
async def create_agent(
    payload: AgentCreatePayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("agent_create")),
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
    await _audit_admin_agent_action(
        db=db,
        request=request,
        admin=admin,
        agent=agent,
        action="ADMIN_AGENT_CREATE",
        before_state=None,
        after_state=_agent_state(agent),
    )

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
            "step_up_method": get_admin_step_up_method(request),
        },
    )
    await db.commit()

    return {
        "agent_id": str(agent.agent_id),
        "display_name": agent.display_name,
        "country_code": agent.country_code,
        "active": agent.active,
    }


@router.get("")
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
            Wallets.currency_code.label("currency_code"),
            func.coalesce(
                select(func.sum(AgentTransactions.commission))
                .where(AgentTransactions.agent_id == Agents.agent_id)
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
            "currency_code": str(r.currency_code or "").upper() or "BIF",
            "total_commission": float(r.total_commission or 0),
        }
        for r in rows.all()
    ]


@router.patch("/{agent_id}/toggle")
async def toggle_agent(
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("agent_toggle_status")),
):
    agent = await db.scalar(select(Agents).where(Agents.agent_id == agent_id))
    if not agent:
        raise HTTPException(404, "Agent introuvable")

    before_state = _agent_state(agent)
    agent.active = not agent.active
    await db.commit()
    await _audit_admin_agent_action(
        db=db,
        request=request,
        admin=admin,
        agent=agent,
        action="ADMIN_AGENT_TOGGLE_STATUS",
        before_state=before_state,
        after_state=_agent_state(agent),
    )
    await db.commit()
    return {"message": "Etat mis a jour", "active": agent.active}


@router.patch("/{agent_id}/commission")
async def update_agent_commission(
    agent_id: str,
    payload: CommissionPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Users = Depends(require_admin_step_up("agent_update_commission")),
):
    agent = await db.scalar(select(Agents).where(Agents.agent_id == agent_id))
    if not agent:
        raise HTTPException(404, "Agent introuvable")

    before_state = _agent_state(agent)
    agent.commission_rate = payload.commission_rate
    await db.commit()
    await _audit_admin_agent_action(
        db=db,
        request=request,
        admin=admin,
        agent=agent,
        action="ADMIN_AGENT_UPDATE_COMMISSION",
        before_state=before_state,
        after_state=_agent_state(agent),
    )
    await db.commit()
    return {
        "message": "Commission mise a jour",
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

    agent_wallet = await db.scalar(
        select(Wallets)
        .where(
            Wallets.user_id == agent.user_id,
            Wallets.type == "agent",
        )
        .limit(1)
    )
    currency_code = str(getattr(agent_wallet, "currency_code", "") or "").upper() or "BIF"

    stmt = (
        select(
            AgentTransactions,
            Users.full_name.label("client_name"),
            Users.phone_e164.label("client_phone"),
        )
        .join(Users, Users.user_id == AgentTransactions.client_user_id, isouter=True)
        .where(AgentTransactions.agent_id == agent.agent_id)
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
                "currency_code": currency_code,
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
                "currency_code": currency_code,
                "created_at": c.created_at.isoformat(),
            }
            for c in commissions
        ],
        "currency_code": currency_code,
    }
