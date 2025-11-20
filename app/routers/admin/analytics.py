from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select, cast, Text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.agents import Agents
from app.models.amlevents import AmlEvents
from app.models.external_transfers import ExternalTransfers
from app.models.sanctionsscreening import SanctionsScreening
from app.models.tontinecontributions import TontineContributions, ContributionStatus
from app.models.tontinemembers import TontineMembers
from app.models.tontines import Tontines
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallets import Wallets

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])


@router.get("/overview")
async def analytics_overview(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    total_users = await db.scalar(select(func.count(Users.user_id)))
    active_today = await db.scalar(
        select(func.count(Users.user_id)).where(Users.updated_at >= day_ago)
    )

    tx_today = await db.scalar(
        select(func.sum(Transactions.amount)).where(
            Transactions.created_at >= day_ago
        )
    )
    tx_week = await db.scalar(
        select(func.sum(Transactions.amount)).where(
            Transactions.created_at >= week_ago
        )
    )

    negative_wallets = await db.scalar(
        select(func.count(Wallets.wallet_id)).where(Wallets.available < 0)
    )

    return {
        "total_users": total_users or 0,
        "active_today": active_today or 0,
        "transactions_24h": float(tx_today or 0),
        "transactions_7d": float(tx_week or 0),
        "negative_wallets": negative_wallets or 0,
    }


@router.get("/growth")
async def growth_metrics(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    now = datetime.utcnow()
    starts = [now - timedelta(days=i) for i in range(6, -1, -1)]

    daily_counts = []
    for start in starts:
        end = start + timedelta(days=1)
        count = await db.scalar(
            select(func.count(Users.user_id)).where(
                Users.created_at >= start, Users.created_at < end
            )
        )
        daily_counts.append(
            {"date": start.date().isoformat(), "new_users": count or 0}
        )

    return daily_counts


@router.get("/premium")
async def premium_dashboard(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    now = datetime.utcnow()
    week_window = now - timedelta(days=6)
    six_week_window = now - timedelta(weeks=6)

    total_volume = await db.scalar(
        select(func.coalesce(func.sum(Transactions.amount), 0))
    )
    mobile_volume = await db.scalar(
        select(func.coalesce(func.sum(Transactions.amount), 0)).where(
            Transactions.channel == "mobile_money"
        )
    )

    active_agents = await db.scalar(
        select(func.count(Agents.agent_id)).where(Agents.active.is_(True))
    )

    aml_breakdown_rows = await db.execute(
        select(AmlEvents.risk_level, func.count(AmlEvents.aml_id)).group_by(
            AmlEvents.risk_level
        )
    )
    aml_breakdown = {row.risk_level: row.count for row in aml_breakdown_rows}
    aml_high = aml_breakdown.get("high", 0) + aml_breakdown.get("critical", 0)

    pending_external = await db.scalar(
        select(func.count(ExternalTransfers.transfer_id)).where(
            ExternalTransfers.status == "pending"
        )
    )

    active_tontines = await db.scalar(
        select(func.count(Tontines.tontine_id)).where(
            Tontines.status == "active"
        )
    )

    sanctions_matches = await db.scalar(
        select(func.count(SanctionsScreening.screening_id)).where(
            SanctionsScreening.matched.is_(True)
        )
    )

    daily_stmt = (
        select(
            func.date_trunc("day", Transactions.created_at).label("bucket"),
            func.sum(Transactions.amount).label("total"),
            func.sum(
                case(
                    (Transactions.channel == "mobile_money", Transactions.amount),
                    else_=0,
                )
            ).label("mobile"),
        )
        .where(Transactions.created_at >= week_window)
        .group_by("bucket")
        .order_by("bucket")
    )
    daily_rows = (await db.execute(daily_stmt)).all()
    daily_volume = [
        {
            "date": row.bucket.date().isoformat(),
            "total": float(row.total or 0),
            "mobile": float(row.mobile or 0),
        }
        for row in daily_rows
    ]

    weekly_stmt = (
        select(
            func.date_trunc("week", Transactions.created_at).label("bucket"),
            func.sum(Transactions.amount).label("total"),
        )
        .where(Transactions.created_at >= six_week_window)
        .group_by("bucket")
        .order_by("bucket")
    )
    weekly_rows = (await db.execute(weekly_stmt)).all()
    weekly_volume = [
        {
            "week": row.bucket.date().isoformat(),
            "total": float(row.total or 0),
        }
        for row in weekly_rows
    ]

    return {
        "kpis": {
            "total_volume": float(total_volume or 0),
            "mobile_money_volume": float(mobile_volume or 0),
            "active_agents": active_agents or 0,
            "aml_high": aml_high,
            "pending_external": pending_external or 0,
            "active_tontines": active_tontines or 0,
            "sanctions_matches": sanctions_matches or 0,
        },
        "daily_volume": daily_volume,
        "weekly_volume": weekly_volume,
        "risk_breakdown": aml_breakdown,
    }


from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import bindparam



@router.get("/tontines")
async def tontine_dashboard(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=6)
    
    paid_status_filter = cast(TontineContributions.status, Text) == ContributionStatus.paid.value

    total_contributions = await db.scalar(
        select(func.coalesce(func.sum(TontineContributions.amount), 0)).where(
            paid_status_filter
        )
    )

    total_tontines = await db.scalar(
        select(func.count(Tontines.tontine_id))
    )
    active_tontines = await db.scalar(
        select(func.count(Tontines.tontine_id)).where(Tontines.status == "active")
    )
    global_pot = await db.scalar(
        select(func.coalesce(func.sum(Tontines.common_pot), 0))
    )

    status_rows = await db.execute(
        select(Tontines.status, func.count(Tontines.tontine_id)).group_by(
            Tontines.status
        )
    )
    status_breakdown = {row.status: row.count for row in status_rows}

    daily_stmt = (
        select(
            func.date_trunc("day", TontineContributions.paid_at).label("bucket"),
            func.sum(TontineContributions.amount).label("total"),
        )
        .where(
            paid_status_filter,
            TontineContributions.paid_at >= week_ago,
        )
        .group_by("bucket")
        .order_by("bucket")
    )
    daily_rows = (await db.execute(daily_stmt)).all()
    daily_contributions = [
        {"date": row.bucket.date().isoformat(), "amount": float(row.total or 0)}
        for row in daily_rows
    ]

    members_count = await db.scalar(
        select(func.count(TontineMembers.user_id))
    )

    return {
        "total_contributions": float(total_contributions or 0),
        "global_pot": float(global_pot or 0),
        "total_tontines": total_tontines or 0,
        "active_tontines": active_tontines or 0,
        "inactive_tontines": (total_tontines or 0) - (active_tontines or 0),
        "members_count": members_count or 0,
        "status_breakdown": status_breakdown,
        "daily_contributions": daily_contributions,
    }
