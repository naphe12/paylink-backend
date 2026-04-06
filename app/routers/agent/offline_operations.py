from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.users import Users
from app.schemas.agent_offline_operations import (
    AgentOfflineOperationCreate,
    AgentOfflineOperationRead,
    AgentOfflineSyncSummary,
)
from app.services.agent_offline_service import (
    cancel_agent_offline_operation,
    create_agent_offline_operation,
    list_agent_offline_operations,
    sync_agent_offline_operation,
    sync_pending_agent_offline_operations,
)

router = APIRouter(prefix="/agent/offline-operations", tags=["Agent Offline"])


@router.get("", response_model=list[AgentOfflineOperationRead])
async def list_agent_offline_operations_route(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await list_agent_offline_operations(db, current_agent=current_agent, status=status)


@router.post("", response_model=AgentOfflineOperationRead)
async def create_agent_offline_operation_route(
    payload: AgentOfflineOperationCreate,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await create_agent_offline_operation(db, current_agent=current_agent, payload=payload)


@router.post("/sync-pending", response_model=AgentOfflineSyncSummary)
async def sync_pending_agent_offline_operations_route(
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await sync_pending_agent_offline_operations(db, current_agent=current_agent)


@router.post("/{operation_id}/sync", response_model=AgentOfflineOperationRead)
async def sync_agent_offline_operation_route(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await sync_agent_offline_operation(db, current_agent=current_agent, operation_id=operation_id)


@router.post("/{operation_id}/cancel", response_model=AgentOfflineOperationRead)
async def cancel_agent_offline_operation_route(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_agent: Users = Depends(get_current_agent),
):
    return await cancel_agent_offline_operation(db, current_agent=current_agent, operation_id=operation_id)
