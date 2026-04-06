from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.users import Users
from app.schemas.agent_offline_operations import AgentOfflineOperationAdminRead
from app.services.agent_offline_service import (
    cancel_admin_agent_offline_operation,
    get_admin_agent_offline_operation_detail,
    list_admin_agent_offline_operations,
    retry_admin_agent_offline_operation,
)

router = APIRouter(prefix="/admin/agent/offline-operations", tags=["Admin Agent Offline"])


@router.get("", response_model=list[AgentOfflineOperationAdminRead])
async def list_admin_agent_offline_operations_route(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await list_admin_agent_offline_operations(db, status=status, q=q, limit=limit)


@router.get("/{operation_id}", response_model=AgentOfflineOperationAdminRead)
async def get_admin_agent_offline_operation_detail_route(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await get_admin_agent_offline_operation_detail(db, operation_id=operation_id)


@router.post("/{operation_id}/retry", response_model=AgentOfflineOperationAdminRead)
async def retry_admin_agent_offline_operation_route(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await retry_admin_agent_offline_operation(db, operation_id=operation_id)


@router.post("/{operation_id}/cancel", response_model=AgentOfflineOperationAdminRead)
async def cancel_admin_agent_offline_operation_route(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    return await cancel_admin_agent_offline_operation(db, operation_id=operation_id)
