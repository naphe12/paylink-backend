from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AiAuditLogRead(BaseModel):
    id: UUID
    user_id: UUID | None = None
    session_id: UUID | None = None
    raw_message: str
    parsed_intent: dict[str, Any] | None = None
    resolved_command: dict[str, Any] | None = None
    action_taken: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiFeedbackAnnotationCreate(BaseModel):
    status: str = "reviewed"
    expected_intent: str | None = None
    expected_entities_json: dict[str, Any] = Field(default_factory=dict)
    parser_was_correct: bool | None = None
    resolver_was_correct: bool | None = None
    final_resolution_notes: str | None = None


class AiFeedbackAnnotationRead(BaseModel):
    id: UUID
    audit_log_id: UUID
    reviewer_user_id: UUID | None = None
    status: str
    expected_intent: str | None = None
    expected_entities_json: dict[str, Any] = Field(default_factory=dict)
    parser_was_correct: bool | None = None
    resolver_was_correct: bool | None = None
    final_resolution_notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiFeedbackSuggestionRead(BaseModel):
    id: UUID
    annotation_id: UUID
    suggestion_type: str
    target_key: str
    proposed_value: dict[str, Any]
    applied: bool
    applied_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiSynonymCreate(BaseModel):
    domain: str
    canonical_value: str
    synonym: str
    language_code: str = "fr"
    is_active: bool = True


class AiSynonymUpdate(BaseModel):
    domain: str
    canonical_value: str
    synonym: str
    language_code: str = "fr"
    is_active: bool = True


class AiSynonymRead(BaseModel):
    id: UUID
    domain: str
    canonical_value: str
    synonym: str
    language_code: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
