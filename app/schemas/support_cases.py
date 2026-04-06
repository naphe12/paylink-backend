from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupportCaseCreate(BaseModel):
    category: str
    subject: str
    description: str
    entity_type: str | None = None
    entity_id: str | None = None


class SupportCaseMessageCreate(BaseModel):
    body: str


class SupportCaseAttachmentCreate(BaseModel):
    file_name: str
    storage_key: str
    file_mime_type: str | None = None
    file_size_bytes: int | None = None
    checksum_sha256: str | None = None


class SupportCaseAdminAssign(BaseModel):
    assigned_to_user_id: UUID | None = None


class SupportCaseAdminStatusUpdate(BaseModel):
    status: str
    resolution_code: str | None = None
    reason_code: str | None = None
    message: str | None = None


class SupportCaseMessageRead(BaseModel):
    message_id: UUID
    case_id: UUID
    author_user_id: UUID | None = None
    author_role: str
    message_type: str
    body: str
    is_visible_to_customer: bool
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupportCaseEventRead(BaseModel):
    event_id: UUID
    case_id: UUID
    actor_user_id: UUID | None = None
    actor_role: str | None = None
    event_type: str
    before_status: str | None = None
    after_status: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupportCaseAttachmentRead(BaseModel):
    attachment_id: UUID
    case_id: UUID
    uploaded_by_user_id: UUID | None = None
    file_name: str
    file_mime_type: str | None = None
    file_size_bytes: int | None = None
    storage_key: str
    checksum_sha256: str | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupportCaseRead(BaseModel):
    case_id: UUID
    user_id: UUID
    assigned_to_user_id: UUID | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    category: str
    subject: str
    description: str
    status: str
    priority: str
    reason_code: str | None = None
    resolution_code: str | None = None
    sla_due_at: datetime | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime
    updated_at: datetime
    customer_label: str | None = None
    assigned_to_label: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupportCaseDetailRead(BaseModel):
    case: SupportCaseRead
    messages: list[SupportCaseMessageRead] = Field(default_factory=list)
    attachments: list[SupportCaseAttachmentRead] = Field(default_factory=list)
    events: list[SupportCaseEventRead] = Field(default_factory=list)
