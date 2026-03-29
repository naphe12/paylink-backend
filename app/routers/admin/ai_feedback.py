from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.ai_audit_logs import AiAuditLogs
from app.models.ai_feedback_annotations import AiFeedbackAnnotations
from app.models.ai_feedback_suggestions import AiFeedbackSuggestions
from app.models.ai_intent_slots import AiIntentSlots
from app.models.ai_prompt_fragments import AiPromptFragments
from app.models.ai_synonyms import AiSynonyms
from app.models.users import Users
from app.schemas.ai_feedback import (
    AiAuditLogRead,
    AiFeedbackAnnotationCreate,
    AiFeedbackAnnotationRead,
    AiFeedbackSuggestionRead,
    AiSynonymCreate,
    AiSynonymRead,
    AiSynonymUpdate,
)

router = APIRouter(prefix="/admin/ai", tags=["Admin AI Feedback"])


def _normalize_feedback_synonym(raw_message: str) -> str | None:
    value = " ".join(str(raw_message or "").strip().lower().split())
    return value or None


def _normalize_manual_synonym(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _build_annotation_suggestions(
    audit_log: AiAuditLogs,
    annotation: AiFeedbackAnnotations,
) -> list[dict]:
    suggestions: list[dict] = []
    synonym = _normalize_feedback_synonym(audit_log.raw_message)
    if (
        synonym
        and annotation.expected_intent
        and annotation.parser_was_correct is False
    ):
        suggestions.append(
            {
                "suggestion_type": "intent_alias",
                "target_key": annotation.expected_intent,
                "proposed_value": {
                    "domain": "intent",
                    "canonical_value": annotation.expected_intent,
                    "synonym": synonym,
                    "language_code": "fr",
                },
            }
        )
    network = annotation.expected_entities_json.get("partner_name")
    if (
        isinstance(network, str)
        and network.strip()
        and annotation.resolver_was_correct is False
        and synonym
    ):
        suggestions.append(
            {
                "suggestion_type": "network_alias",
                "target_key": network.strip(),
                "proposed_value": {
                    "domain": "network",
                    "canonical_value": network.strip(),
                    "synonym": synonym,
                    "language_code": "fr",
                },
            }
        )
    for slot_name, slot_value in dict(annotation.expected_entities_json or {}).items():
        if not isinstance(slot_value, (str, int, float)) or slot_value in ("", None):
            continue
        if not annotation.expected_intent:
            continue
        suggestions.append(
            {
                "suggestion_type": "slot_example",
                "target_key": f"{annotation.expected_intent}:{slot_name}",
                "proposed_value": {
                    "intent_code": annotation.expected_intent,
                    "slot_name": slot_name,
                    "example": str(slot_value),
                },
            }
        )
    if annotation.expected_intent and annotation.final_resolution_notes:
        suggestions.append(
            {
                "suggestion_type": "prompt_hint",
                "target_key": annotation.expected_intent,
                "proposed_value": {
                    "intent_code": annotation.expected_intent,
                    "prompt_hint": annotation.final_resolution_notes.strip(),
                    "language_code": "fr",
                },
            }
        )
    return suggestions


@router.get("/audit-logs", response_model=list[AiAuditLogRead])
async def list_ai_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    q: str | None = Query(None),
    parsed_intent: str | None = Query(None),
    annotated: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    stmt = (
        select(AiAuditLogs)
        .outerjoin(AiFeedbackAnnotations, AiFeedbackAnnotations.audit_log_id == AiAuditLogs.id)
        .order_by(desc(AiAuditLogs.created_at))
        .offset(offset)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(AiAuditLogs.status == status)
    if q:
        pattern = f"%{str(q).strip()}%"
        stmt = stmt.where(
            or_(
                AiAuditLogs.raw_message.ilike(pattern),
                AiAuditLogs.error_message.ilike(pattern),
                cast(AiAuditLogs.parsed_intent, String).ilike(pattern),
            )
        )
    if parsed_intent:
        stmt = stmt.where(AiAuditLogs.parsed_intent["intent"].astext.ilike(f"%{str(parsed_intent).strip()}%"))
    if annotated is True:
        stmt = stmt.where(AiFeedbackAnnotations.id.is_not(None))
    elif annotated is False:
        stmt = stmt.where(AiFeedbackAnnotations.id.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.get("/audit-logs/{audit_log_id}")
async def get_ai_audit_log_detail(
    audit_log_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    audit_log = await db.get(AiAuditLogs, audit_log_id)
    if not audit_log:
        raise HTTPException(status_code=404, detail="Audit log introuvable.")

    annotation = (
        await db.execute(
            select(AiFeedbackAnnotations)
            .where(AiFeedbackAnnotations.audit_log_id == audit_log_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    suggestions = []
    if annotation is not None:
        suggestions = (
            await db.execute(
                select(AiFeedbackSuggestions)
                .where(AiFeedbackSuggestions.annotation_id == annotation.id)
                .order_by(desc(AiFeedbackSuggestions.created_at))
            )
        ).scalars().all()

    return {
        "audit_log": AiAuditLogRead.model_validate(audit_log).model_dump(mode="json"),
        "annotation": (
            AiFeedbackAnnotationRead.model_validate(annotation).model_dump(mode="json")
            if annotation is not None
            else None
        ),
        "suggestions": [
            AiFeedbackSuggestionRead.model_validate(item).model_dump(mode="json")
            for item in suggestions
        ],
    }


@router.post("/audit-logs/{audit_log_id}/annotate")
async def annotate_ai_audit_log(
    audit_log_id: UUID,
    payload: AiFeedbackAnnotationCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: Users = Depends(get_current_admin),
):
    audit_log = await db.get(AiAuditLogs, audit_log_id)
    if not audit_log:
        raise HTTPException(status_code=404, detail="Audit log introuvable.")

    stmt = select(AiFeedbackAnnotations).where(AiFeedbackAnnotations.audit_log_id == audit_log_id).limit(1)
    annotation = (await db.execute(stmt)).scalar_one_or_none()
    if annotation is None:
        annotation = AiFeedbackAnnotations(
            audit_log_id=audit_log_id,
            reviewer_user_id=current_admin.user_id,
        )
        db.add(annotation)

    annotation.reviewer_user_id = current_admin.user_id
    annotation.status = payload.status
    annotation.expected_intent = payload.expected_intent
    annotation.expected_entities_json = payload.expected_entities_json
    annotation.parser_was_correct = payload.parser_was_correct
    annotation.resolver_was_correct = payload.resolver_was_correct
    annotation.final_resolution_notes = payload.final_resolution_notes

    await db.flush()

    existing = (
        await db.execute(
            select(AiFeedbackSuggestions).where(AiFeedbackSuggestions.annotation_id == annotation.id)
        )
    ).scalars().all()
    for item in existing:
        if not item.applied:
            await db.delete(item)

    for suggestion in _build_annotation_suggestions(audit_log, annotation):
        db.add(
            AiFeedbackSuggestions(
                annotation_id=annotation.id,
                suggestion_type=suggestion["suggestion_type"],
                target_key=suggestion["target_key"],
                proposed_value=suggestion["proposed_value"],
            )
        )

    await db.commit()
    await db.refresh(annotation)

    suggestions = (
        await db.execute(
            select(AiFeedbackSuggestions)
            .where(AiFeedbackSuggestions.annotation_id == annotation.id)
            .order_by(desc(AiFeedbackSuggestions.created_at))
        )
    ).scalars().all()

    return {
        "annotation": AiFeedbackAnnotationRead.model_validate(annotation).model_dump(mode="json"),
        "suggestions": [
            AiFeedbackSuggestionRead.model_validate(item).model_dump(mode="json")
            for item in suggestions
        ],
    }


@router.get("/feedback/suggestions", response_model=list[AiFeedbackSuggestionRead])
async def list_ai_feedback_suggestions(
    applied: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    stmt = select(AiFeedbackSuggestions).order_by(desc(AiFeedbackSuggestions.created_at)).limit(limit)
    if applied is not None:
        stmt = stmt.where(AiFeedbackSuggestions.applied == applied)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.post("/feedback/suggestions/{suggestion_id}/apply", response_model=AiFeedbackSuggestionRead)
async def apply_ai_feedback_suggestion(
    suggestion_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    suggestion = await db.get(AiFeedbackSuggestions, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion introuvable.")
    if suggestion.applied:
        return suggestion

    payload = dict(suggestion.proposed_value or {})
    domain = str(payload.get("domain") or "").strip()
    canonical_value = str(payload.get("canonical_value") or suggestion.target_key or "").strip()
    synonym = _normalize_feedback_synonym(payload.get("synonym") or "")
    language_code = str(payload.get("language_code") or "fr").strip() or "fr"

    if suggestion.suggestion_type in {"intent_alias", "network_alias"}:
        if not domain or not canonical_value or not synonym:
            raise HTTPException(status_code=400, detail="Suggestion incomplete.")
        existing_stmt = select(AiSynonyms).where(
            AiSynonyms.domain == domain,
            AiSynonyms.canonical_value == canonical_value,
            AiSynonyms.synonym == synonym,
            AiSynonyms.language_code == language_code,
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is None:
            db.add(
                AiSynonyms(
                    domain=domain,
                    canonical_value=canonical_value,
                    synonym=synonym,
                    language_code=language_code,
                    is_active=True,
                )
            )
        else:
            existing.is_active = True
    elif suggestion.suggestion_type == "slot_example":
        intent_code = str(payload.get("intent_code") or "").strip()
        slot_name = str(payload.get("slot_name") or "").strip()
        example = str(payload.get("example") or "").strip()
        if not intent_code or not slot_name or not example:
            raise HTTPException(status_code=400, detail="Suggestion incomplete.")
        slot = (
            await db.execute(
                select(AiIntentSlots)
                .where(
                    AiIntentSlots.intent_code == intent_code,
                    AiIntentSlots.slot_name == slot_name,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if slot is None:
            raise HTTPException(status_code=404, detail="Slot introuvable.")
        slot.example = example
    elif suggestion.suggestion_type == "prompt_hint":
        intent_code = str(payload.get("intent_code") or "").strip()
        prompt_hint = str(payload.get("prompt_hint") or "").strip()
        if not intent_code or not prompt_hint:
            raise HTTPException(status_code=400, detail="Suggestion incomplete.")
        db.add(
            AiPromptFragments(
                intent_code=intent_code,
                fragment_type="feedback_hint",
                content=prompt_hint,
                language_code=language_code,
                enabled=True,
            )
        )
    else:
        raise HTTPException(status_code=400, detail="Type de suggestion non pris en charge.")

    suggestion.applied = True
    suggestion.applied_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.get("/synonyms", response_model=list[AiSynonymRead])
async def list_ai_synonyms(
    domain: str | None = Query(None),
    language_code: str | None = Query(None),
    canonical_value: str | None = Query(None),
    is_active: bool | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    stmt = select(AiSynonyms).order_by(AiSynonyms.domain, AiSynonyms.canonical_value, AiSynonyms.synonym).limit(limit)
    if domain:
        stmt = stmt.where(AiSynonyms.domain == str(domain).strip())
    if language_code:
        stmt = stmt.where(AiSynonyms.language_code == str(language_code).strip())
    if canonical_value:
        stmt = stmt.where(AiSynonyms.canonical_value.ilike(f"%{str(canonical_value).strip()}%"))
    if is_active is not None:
        stmt = stmt.where(AiSynonyms.is_active.is_(is_active))
    if q:
        pattern = f"%{str(q).strip()}%"
        stmt = stmt.where(
            or_(
                AiSynonyms.synonym.ilike(pattern),
                AiSynonyms.canonical_value.ilike(pattern),
                AiSynonyms.domain.ilike(pattern),
                AiSynonyms.language_code.ilike(pattern),
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.post("/synonyms", response_model=AiSynonymRead)
async def create_ai_synonym(
    payload: AiSynonymCreate,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    domain = str(payload.domain or "").strip()
    canonical_value = str(payload.canonical_value or "").strip()
    synonym = _normalize_manual_synonym(payload.synonym)
    language_code = str(payload.language_code or "fr").strip() or "fr"

    if not domain or not canonical_value or not synonym:
        raise HTTPException(status_code=400, detail="domain, canonical_value et synonym sont requis.")

    existing = (
        await db.execute(
            select(AiSynonyms).where(
                AiSynonyms.domain == domain,
                AiSynonyms.canonical_value == canonical_value,
                AiSynonyms.synonym == synonym,
                AiSynonyms.language_code == language_code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not existing.is_active and payload.is_active:
            existing.is_active = True
            await db.commit()
            await db.refresh(existing)
        return existing

    row = AiSynonyms(
        domain=domain,
        canonical_value=canonical_value,
        synonym=synonym,
        language_code=language_code,
        is_active=bool(payload.is_active),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/synonyms/{synonym_id}", response_model=AiSynonymRead)
async def update_ai_synonym(
    synonym_id: UUID,
    payload: AiSynonymUpdate,
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    row = await db.get(AiSynonyms, synonym_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Synonyme introuvable.")

    domain = str(payload.domain or "").strip()
    canonical_value = str(payload.canonical_value or "").strip()
    synonym = _normalize_manual_synonym(payload.synonym)
    language_code = str(payload.language_code or "fr").strip() or "fr"

    if not domain or not canonical_value or not synonym:
        raise HTTPException(status_code=400, detail="domain, canonical_value et synonym sont requis.")

    duplicate = (
        await db.execute(
            select(AiSynonyms).where(
                AiSynonyms.id != synonym_id,
                AiSynonyms.domain == domain,
                AiSynonyms.canonical_value == canonical_value,
                AiSynonyms.synonym == synonym,
                AiSynonyms.language_code == language_code,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Un synonyme identique existe deja.")

    row.domain = domain
    row.canonical_value = canonical_value
    row.synonym = synonym
    row.language_code = language_code
    row.is_active = bool(payload.is_active)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/synonyms/{synonym_id}/status", response_model=AiSynonymRead)
async def set_ai_synonym_status(
    synonym_id: UUID,
    is_active: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    _: Users = Depends(get_current_admin),
):
    row = await db.get(AiSynonyms, synonym_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Synonyme introuvable.")
    row.is_active = is_active
    await db.commit()
    await db.refresh(row)
    return row
