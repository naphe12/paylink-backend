from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


OperatorWorkflowStatus = Literal["needs_follow_up", "blocked", "watching", "resolved"]


class OperatorWorkflowRead(BaseModel):
    work_item_id: UUID | None = None
    entity_type: str
    entity_id: UUID
    operator_status: OperatorWorkflowStatus
    owner_user_id: UUID | None = None
    owner_name: str | None = None
    blocked_reason: str | None = None
    notes: str | None = None
    follow_up_at: datetime | None = None
    last_action_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OperatorWorkflowUpsert(BaseModel):
    operator_status: OperatorWorkflowStatus | None = None
    owner_user_id: UUID | None = None
    blocked_reason: str | None = None
    notes: str | None = None
    follow_up_at: datetime | None = None


class OperatorWorkflowOwnerSummary(BaseModel):
    owner_key: str
    owner_label: str
    count: int
    blocked_count: int = 0
    overdue_follow_up_count: int = 0
    mine: bool = False


class OperatorWorkflowSummaryRead(BaseModel):
    all: int
    mine: int
    team: int
    unassigned: int
    blocked_only: int
    needs_follow_up: int
    watching: int
    resolved: int
    overdue_follow_up: int
    owner_breakdown: list[OperatorWorkflowOwnerSummary]


class OperatorUrgencyItemRead(BaseModel):
    id: str
    entity_type: str
    entity_id: UUID
    kind: str
    title: str
    subtitle: str
    status: str
    priority: Literal["critical", "warning", "info"] = "warning"
    operator_status: str
    age: str
    stale: bool = False
    owner: str
    last_action_at: datetime | None = None
    to: str
    meta: str | None = None
    operator_workflow: OperatorWorkflowRead | None = None


class OperatorUrgencyOwnerLoadRead(BaseModel):
    owner_key: str
    owner_label: str
    count: int
    blocked_count: int = 0
    overdue_follow_up_count: int = 0
    critical_count: int = 0


class OperatorUrgencyQueueSummaryRead(BaseModel):
    kind: str
    total: int
    blocked_count: int = 0
    overdue_follow_up_count: int = 0
    stale_count: int = 0
    critical_count: int = 0


class OperatorUrgencyListRead(BaseModel):
    items: list[OperatorUrgencyItemRead]
    total: int
    limit: int
    offset: int
    sort_by: str
    sort_dir: str
    owner_load: list[OperatorUrgencyOwnerLoadRead]
    queue_summary: list[OperatorUrgencyQueueSummaryRead]


class OperatorWorkflowBatchTarget(BaseModel):
    entity_type: str
    entity_id: UUID


class OperatorWorkflowBatchUpsert(BaseModel):
    targets: list[OperatorWorkflowBatchTarget]
    operator_status: OperatorWorkflowStatus | None = None
    owner_user_id: UUID | None = None
    blocked_reason: str | None = None
    notes: str | None = None
    follow_up_at: datetime | None = None


class OperatorWorkflowBatchResultRead(BaseModel):
    updated: int
    items: list[OperatorWorkflowRead]
