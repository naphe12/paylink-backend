from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_case_attachments import SupportCaseAttachments
from app.models.support_case_events import SupportCaseEvents
from app.models.support_case_messages import SupportCaseMessages
from app.models.support_cases import SupportCases
from app.models.users import Users

VALID_CATEGORIES = {"payment_request", "wallet", "p2p", "escrow", "cash_in", "cash_out", "kyc", "fraud", "other"}
VALID_STATUSES = {"open", "in_review", "waiting_user", "resolved", "closed"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _display_user(user: Users | None) -> str | None:
    if not user:
        return None
    return user.paytag or user.username or user.email or user.full_name


def _role_value(user: Users | None) -> str | None:
    if not user:
        return None
    return getattr(user.role, "value", user.role)


async def _users_map(db: AsyncSession, user_ids: Iterable[UUID | None]) -> dict[UUID, Users]:
    valid_ids = [user_id for user_id in user_ids if user_id]
    if not valid_ids:
        return {}
    rows = await db.execute(select(Users).where(Users.user_id.in_(valid_ids)))
    return {item.user_id: item for item in rows.scalars().all()}


async def _append_event(
    db: AsyncSession,
    *,
    case_id: UUID,
    actor_user_id: UUID | None,
    actor_role: str | None,
    event_type: str,
    before_status: str | None,
    after_status: str | None,
    metadata: dict | None = None,
) -> None:
    db.add(
        SupportCaseEvents(
            case_id=case_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            event_type=event_type,
            before_status=before_status,
            after_status=after_status,
            metadata_=metadata or {},
        )
    )
    await db.flush()


async def _add_message(
    db: AsyncSession,
    *,
    case_id: UUID,
    author_user_id: UUID | None,
    author_role: str,
    body: str,
    message_type: str = "comment",
    is_visible_to_customer: bool = True,
    metadata: dict | None = None,
) -> SupportCaseMessages:
    message = SupportCaseMessages(
        case_id=case_id,
        author_user_id=author_user_id,
        author_role=author_role,
        body=body.strip(),
        message_type=message_type,
        is_visible_to_customer=is_visible_to_customer,
        metadata_=metadata or {},
    )
    db.add(message)
    await db.flush()
    return message


async def _list_case_attachments(db: AsyncSession, *, case_id: UUID) -> list[SupportCaseAttachments]:
    return (
        await db.execute(
            select(SupportCaseAttachments)
            .where(SupportCaseAttachments.case_id == case_id)
            .order_by(SupportCaseAttachments.created_at.desc())
        )
    ).scalars().all()


def _serialize_case(case_obj: SupportCases, users: dict[UUID, Users]) -> dict:
    customer = users.get(case_obj.user_id)
    assignee = users.get(case_obj.assigned_to_user_id) if case_obj.assigned_to_user_id else None
    return {
        "case_id": case_obj.case_id,
        "user_id": case_obj.user_id,
        "assigned_to_user_id": case_obj.assigned_to_user_id,
        "entity_type": case_obj.entity_type,
        "entity_id": case_obj.entity_id,
        "category": case_obj.category,
        "subject": case_obj.subject,
        "description": case_obj.description,
        "status": case_obj.status,
        "priority": case_obj.priority,
        "reason_code": case_obj.reason_code,
        "resolution_code": case_obj.resolution_code,
        "sla_due_at": case_obj.sla_due_at,
        "first_response_at": case_obj.first_response_at,
        "resolved_at": case_obj.resolved_at,
        "closed_at": case_obj.closed_at,
        "metadata": case_obj.metadata_ or {},
        "created_at": case_obj.created_at,
        "updated_at": case_obj.updated_at,
        "customer_label": _display_user(customer),
        "assigned_to_label": _display_user(assignee),
    }


async def create_support_case(
    db: AsyncSession,
    *,
    current_user: Users,
    category: str,
    subject: str,
    description: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> dict:
    normalized_category = str(category or "").strip().lower()
    if normalized_category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categorie de dossier invalide.")
    cleaned_subject = str(subject or "").strip()
    cleaned_description = str(description or "").strip()
    if not cleaned_subject or not cleaned_description:
        raise HTTPException(status_code=400, detail="Sujet et description obligatoires.")

    now = _utcnow()
    case_obj = SupportCases(
        user_id=current_user.user_id,
        entity_type=(entity_type or "").strip() or None,
        entity_id=(entity_id or "").strip() or None,
        category=normalized_category,
        subject=cleaned_subject,
        description=cleaned_description,
        status="open",
        priority="normal",
        sla_due_at=now + timedelta(hours=24),
        created_at=now,
        updated_at=now,
        metadata_={},
    )
    db.add(case_obj)
    await db.flush()

    await _add_message(
        db,
        case_id=case_obj.case_id,
        author_user_id=current_user.user_id,
        author_role=_role_value(current_user) or "client",
        body=cleaned_description,
    )
    await _append_event(
        db,
        case_id=case_obj.case_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="created",
        before_status=None,
        after_status=case_obj.status,
        metadata={"category": normalized_category},
    )
    await db.commit()
    await db.refresh(case_obj)
    users = await _users_map(db, [case_obj.user_id, case_obj.assigned_to_user_id])
    return _serialize_case(case_obj, users)


async def list_support_cases_for_user(
    db: AsyncSession,
    *,
    current_user: Users,
    status: str | None = None,
) -> list[dict]:
    stmt = select(SupportCases).where(SupportCases.user_id == current_user.user_id).order_by(SupportCases.created_at.desc())
    if status:
        stmt = stmt.where(SupportCases.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    users = await _users_map(db, [item.user_id for item in rows] + [item.assigned_to_user_id for item in rows])
    return [_serialize_case(item, users) for item in rows]


async def get_support_case_detail_for_user(
    db: AsyncSession,
    *,
    case_id: UUID,
    current_user: Users,
) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    if case_obj.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Acces refuse.")

    messages = (
        await db.execute(
            select(SupportCaseMessages)
            .where(
                SupportCaseMessages.case_id == case_id,
                SupportCaseMessages.is_visible_to_customer.is_(True),
            )
            .order_by(SupportCaseMessages.created_at.asc())
        )
    ).scalars().all()
    events = (
        await db.execute(
            select(SupportCaseEvents).where(SupportCaseEvents.case_id == case_id).order_by(SupportCaseEvents.created_at.desc())
        )
    ).scalars().all()
    users = await _users_map(db, [case_obj.user_id, case_obj.assigned_to_user_id])
    attachments = await _list_case_attachments(db, case_id=case_id)
    return {"case": _serialize_case(case_obj, users), "messages": messages, "attachments": attachments, "events": events}


async def add_support_case_message_for_user(
    db: AsyncSession,
    *,
    case_id: UUID,
    current_user: Users,
    body: str,
) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    if case_obj.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Acces refuse.")
    if case_obj.status == "closed":
        raise HTTPException(status_code=409, detail="Ce dossier est ferme.")
    cleaned_body = str(body or "").strip()
    if not cleaned_body:
        raise HTTPException(status_code=400, detail="Message vide.")

    previous_status = case_obj.status
    if case_obj.status == "waiting_user":
        case_obj.status = "in_review"
    case_obj.updated_at = _utcnow()
    await _add_message(
        db,
        case_id=case_id,
        author_user_id=current_user.user_id,
        author_role=_role_value(current_user) or "client",
        body=cleaned_body,
    )
    await _append_event(
        db,
        case_id=case_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="replied",
        before_status=previous_status,
        after_status=case_obj.status,
        metadata={"source": "customer"},
    )
    await db.commit()
    return await get_support_case_detail_for_user(db, case_id=case_id, current_user=current_user)


async def add_support_case_attachment_for_user(
    db: AsyncSession,
    *,
    case_id: UUID,
    current_user: Users,
    file_name: str,
    storage_key: str,
    file_mime_type: str | None = None,
    file_size_bytes: int | None = None,
    checksum_sha256: str | None = None,
) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    if case_obj.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Acces refuse.")
    if case_obj.status == "closed":
        raise HTTPException(status_code=409, detail="Ce dossier est ferme.")

    cleaned_name = str(file_name or "").strip()
    cleaned_storage_key = str(storage_key or "").strip()
    if not cleaned_name or not cleaned_storage_key:
        raise HTTPException(status_code=400, detail="Nom de preuve et lien ou reference obligatoires.")

    previous_status = case_obj.status
    if case_obj.status == "waiting_user":
        case_obj.status = "in_review"
    case_obj.updated_at = _utcnow()
    db.add(
        SupportCaseAttachments(
            case_id=case_id,
            uploaded_by_user_id=current_user.user_id,
            file_name=cleaned_name,
            file_mime_type=(file_mime_type or "").strip() or None,
            file_size_bytes=file_size_bytes,
            storage_key=cleaned_storage_key,
            checksum_sha256=(checksum_sha256 or "").strip() or None,
            metadata_={"source": "customer"},
        )
    )
    await db.flush()
    await _append_event(
        db,
        case_id=case_id,
        actor_user_id=current_user.user_id,
        actor_role=_role_value(current_user),
        event_type="replied",
        before_status=previous_status,
        after_status=case_obj.status,
        metadata={"source": "customer_attachment", "file_name": cleaned_name},
    )
    await db.commit()
    return await get_support_case_detail_for_user(db, case_id=case_id, current_user=current_user)


async def list_support_cases_admin(
    db: AsyncSession,
    *,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    stmt = select(SupportCases).order_by(SupportCases.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(SupportCases.status == status)
    if q:
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(SupportCases.subject).like(term),
                func.lower(SupportCases.description).like(term),
                func.lower(func.coalesce(SupportCases.entity_id, "")).like(term),
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    users = await _users_map(db, [item.user_id for item in rows] + [item.assigned_to_user_id for item in rows])
    return [_serialize_case(item, users) for item in rows]


async def get_support_case_detail_admin(db: AsyncSession, *, case_id: UUID) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    messages = (
        await db.execute(
            select(SupportCaseMessages).where(SupportCaseMessages.case_id == case_id).order_by(SupportCaseMessages.created_at.asc())
        )
    ).scalars().all()
    events = (
        await db.execute(
            select(SupportCaseEvents).where(SupportCaseEvents.case_id == case_id).order_by(SupportCaseEvents.created_at.desc())
        )
    ).scalars().all()
    users = await _users_map(db, [case_obj.user_id, case_obj.assigned_to_user_id])
    attachments = await _list_case_attachments(db, case_id=case_id)
    return {"case": _serialize_case(case_obj, users), "messages": messages, "attachments": attachments, "events": events}


async def assign_support_case_admin(
    db: AsyncSession,
    *,
    case_id: UUID,
    admin_user: Users,
    assigned_to_user_id: UUID | None,
) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    case_obj.assigned_to_user_id = assigned_to_user_id
    case_obj.updated_at = _utcnow()
    await _append_event(
        db,
        case_id=case_id,
        actor_user_id=admin_user.user_id,
        actor_role=_role_value(admin_user),
        event_type="assigned",
        before_status=case_obj.status,
        after_status=case_obj.status,
        metadata={"assigned_to_user_id": str(assigned_to_user_id) if assigned_to_user_id else None},
    )
    await db.commit()
    return await get_support_case_detail_admin(db, case_id=case_id)


async def update_support_case_status_admin(
    db: AsyncSession,
    *,
    case_id: UUID,
    admin_user: Users,
    status: str,
    resolution_code: str | None = None,
    reason_code: str | None = None,
    message: str | None = None,
) -> dict:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide.")

    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    previous_status = case_obj.status
    now = _utcnow()
    case_obj.status = normalized_status
    case_obj.reason_code = (reason_code or "").strip() or case_obj.reason_code
    case_obj.resolution_code = (resolution_code or "").strip() or case_obj.resolution_code
    case_obj.updated_at = now
    if normalized_status == "resolved":
        case_obj.resolved_at = now
    if normalized_status == "closed":
        case_obj.closed_at = now
    if normalized_status == "in_review" and case_obj.first_response_at is None:
        case_obj.first_response_at = now

    if (message or "").strip():
        await _add_message(
            db,
            case_id=case_id,
            author_user_id=admin_user.user_id,
            author_role=_role_value(admin_user) or "admin",
            body=message,
            message_type="status_update",
            is_visible_to_customer=True,
            metadata={"status": normalized_status},
        )
    await _append_event(
        db,
        case_id=case_id,
        actor_user_id=admin_user.user_id,
        actor_role=_role_value(admin_user),
        event_type="status_changed",
        before_status=previous_status,
        after_status=normalized_status,
        metadata={"resolution_code": resolution_code, "reason_code": reason_code},
    )
    await db.commit()
    return await get_support_case_detail_admin(db, case_id=case_id)


async def reply_support_case_admin(
    db: AsyncSession,
    *,
    case_id: UUID,
    admin_user: Users,
    body: str,
) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    cleaned_body = str(body or "").strip()
    if not cleaned_body:
        raise HTTPException(status_code=400, detail="Message vide.")

    previous_status = case_obj.status
    case_obj.status = "waiting_user"
    if case_obj.first_response_at is None:
        case_obj.first_response_at = _utcnow()
    case_obj.updated_at = _utcnow()
    await _add_message(
        db,
        case_id=case_id,
        author_user_id=admin_user.user_id,
        author_role=_role_value(admin_user) or "admin",
        body=cleaned_body,
        is_visible_to_customer=True,
    )
    await _append_event(
        db,
        case_id=case_id,
        actor_user_id=admin_user.user_id,
        actor_role=_role_value(admin_user),
        event_type="replied",
        before_status=previous_status,
        after_status=case_obj.status,
        metadata={"source": "admin"},
    )
    await db.commit()
    return await get_support_case_detail_admin(db, case_id=case_id)


async def add_support_case_attachment_admin(
    db: AsyncSession,
    *,
    case_id: UUID,
    admin_user: Users,
    file_name: str,
    storage_key: str,
    file_mime_type: str | None = None,
    file_size_bytes: int | None = None,
    checksum_sha256: str | None = None,
) -> dict:
    case_obj = await db.scalar(select(SupportCases).where(SupportCases.case_id == case_id))
    if not case_obj:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    cleaned_name = str(file_name or "").strip()
    cleaned_storage_key = str(storage_key or "").strip()
    if not cleaned_name or not cleaned_storage_key:
        raise HTTPException(status_code=400, detail="Nom de preuve et lien ou reference obligatoires.")

    case_obj.updated_at = _utcnow()
    db.add(
        SupportCaseAttachments(
            case_id=case_id,
            uploaded_by_user_id=admin_user.user_id,
            file_name=cleaned_name,
            file_mime_type=(file_mime_type or "").strip() or None,
            file_size_bytes=file_size_bytes,
            storage_key=cleaned_storage_key,
            checksum_sha256=(checksum_sha256 or "").strip() or None,
            metadata_={"source": "admin"},
        )
    )
    await db.flush()
    await _append_event(
        db,
        case_id=case_id,
        actor_user_id=admin_user.user_id,
        actor_role=_role_value(admin_user),
        event_type="replied",
        before_status=case_obj.status,
        after_status=case_obj.status,
        metadata={"source": "admin_attachment", "file_name": cleaned_name},
    )
    await db.commit()
    return await get_support_case_detail_admin(db, case_id=case_id)
