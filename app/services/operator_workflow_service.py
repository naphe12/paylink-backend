from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operator_work_item import OperatorWorkItem
from app.schemas.operator_workflow import OperatorUrgencyItemRead, OperatorWorkflowRead
from app.schemas.operator_workflow import OperatorWorkflowSummaryRead


def _normalize_entity_id(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_work_item(row: dict) -> dict:
    entity_id = row.get("entity_id")
    work_item_id = row.get("work_item_id")
    owner_user_id = row.get("owner_user_id")
    return OperatorWorkflowRead(
        work_item_id=work_item_id,
        entity_type=str(row.get("entity_type") or ""),
        entity_id=entity_id,
        operator_status=str(row.get("operator_status") or "needs_follow_up"),
        owner_user_id=owner_user_id,
        owner_name=row.get("owner_name"),
        blocked_reason=row.get("blocked_reason"),
        notes=row.get("notes"),
        follow_up_at=row.get("follow_up_at"),
        last_action_at=row.get("last_action_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    ).model_dump(mode="json")


async def fetch_operator_workflow_map(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_ids: list[str],
) -> dict[str, dict]:
    normalized_ids = [item for item in {_normalize_entity_id(value) for value in entity_ids} if item]
    if not normalized_ids:
        return {}

    rows = await db.execute(
        text(
            """
            SELECT
              w.work_item_id,
              w.entity_type,
              w.entity_id,
              w.operator_status,
              w.owner_user_id,
              u.full_name AS owner_name,
              w.blocked_reason,
              w.notes,
              w.follow_up_at,
              w.last_action_at,
              w.created_at,
              w.updated_at
            FROM paylink.operator_work_items w
            LEFT JOIN paylink.users u ON u.user_id = w.owner_user_id
            WHERE w.entity_type = :entity_type
              AND w.entity_id = ANY(CAST(:entity_ids AS uuid[]))
            """
        ),
        {
            "entity_type": entity_type,
            "entity_ids": normalized_ids,
        },
    )
    result: dict[str, dict] = {}
    for row in rows.mappings().all():
        key = _normalize_entity_id(row.get("entity_id"))
        if key:
            result[key] = _serialize_work_item(row)
    return result


async def fetch_operator_work_item(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> dict | None:
    mapping = await fetch_operator_workflow_map(db, entity_type=entity_type, entity_ids=[entity_id])
    return mapping.get(str(entity_id))


async def upsert_operator_work_item(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    changes: dict,
) -> dict:
    stmt = select(OperatorWorkItem).where(
        OperatorWorkItem.entity_type == str(entity_type),
        OperatorWorkItem.entity_id == UUID(str(entity_id)),
    )
    work_item = await db.scalar(stmt)
    now = datetime.now(timezone.utc)
    if work_item is None:
        work_item = OperatorWorkItem(
            entity_type=str(entity_type),
            entity_id=UUID(str(entity_id)),
            operator_status="needs_follow_up",
            last_action_at=now,
        )
        db.add(work_item)

    for field, value in changes.items():
        setattr(work_item, field, value)

    if "operator_status" in changes and changes.get("operator_status") != "blocked" and "blocked_reason" not in changes:
        work_item.blocked_reason = None

    work_item.last_action_at = now
    work_item.updated_at = now
    await db.flush()
    payload = await fetch_operator_work_item(
        db,
        entity_type=str(entity_type),
        entity_id=str(entity_id),
    )
    if payload is None:
        raise RuntimeError("Operator workflow could not be reloaded after upsert.")
    return payload


def _normalize_owner_label(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_older_than_hours(value, hours: int) -> bool:
    if value is None:
        return False
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() >= hours * 3600


def _format_age_short(value) -> str:
    if value is None:
        return "-"
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}j"


async def fetch_operator_workflow_summary(
    db: AsyncSession,
    *,
    current_user_id: str | None,
    current_owner_label: str | None,
) -> dict:
    rows = await db.execute(
        text(
            """
            SELECT
              w.entity_type,
              w.entity_id,
              w.operator_status,
              w.owner_user_id,
              u.full_name AS owner_name,
              w.follow_up_at,
              w.last_action_at
            FROM paylink.operator_work_items w
            LEFT JOIN paylink.users u ON u.user_id = w.owner_user_id
            """
        )
    )

    now = datetime.now(timezone.utc)
    my_user_id = str(current_user_id or "")
    my_owner_label = _normalize_owner_label(current_owner_label)
    summary = {
        "all": 0,
        "mine": 0,
        "team": 0,
        "unassigned": 0,
        "blocked_only": 0,
        "needs_follow_up": 0,
        "watching": 0,
        "resolved": 0,
        "overdue_follow_up": 0,
    }
    owners: dict[str, dict] = {}

    for row in rows.mappings().all():
        summary["all"] += 1
        operator_status = str(row.get("operator_status") or "needs_follow_up")
        if operator_status in summary:
            summary[operator_status] += 1

        owner_user_id = str(row.get("owner_user_id") or "")
        owner_name = row.get("owner_name")
        owner_label = owner_name or owner_user_id or "Non assigne"
        owner_key = _normalize_owner_label(owner_name or owner_user_id) or "__unassigned__"
        is_unassigned = owner_key == "__unassigned__"
        is_mine = (my_user_id and owner_user_id == my_user_id) or (
            my_owner_label and _normalize_owner_label(owner_name) == my_owner_label
        )

        if is_unassigned:
            summary["unassigned"] += 1
        if is_mine:
            summary["mine"] += 1
        else:
            summary["team"] += 1
        if operator_status == "blocked":
            summary["blocked_only"] += 1

        follow_up_at = row.get("follow_up_at")
        overdue_follow_up = bool(follow_up_at and follow_up_at <= now)
        if overdue_follow_up:
            summary["overdue_follow_up"] += 1

        owner_bucket = owners.get(owner_key) or {
            "owner_key": owner_key,
            "owner_label": owner_label,
            "count": 0,
            "blocked_count": 0,
            "overdue_follow_up_count": 0,
            "mine": False,
        }
        owner_bucket["count"] += 1
        owner_bucket["mine"] = owner_bucket["mine"] or is_mine
        if operator_status == "blocked":
            owner_bucket["blocked_count"] += 1
        if overdue_follow_up:
            owner_bucket["overdue_follow_up_count"] += 1
        owners[owner_key] = owner_bucket

    owner_breakdown = sorted(
        owners.values(),
        key=lambda item: (-item["blocked_count"], -item["overdue_follow_up_count"], -item["count"], item["owner_label"]),
    )[:10]

    return OperatorWorkflowSummaryRead(
        **summary,
        owner_breakdown=owner_breakdown,
    ).model_dump(mode="json")


async def fetch_operator_urgency_items(db: AsyncSession) -> list[dict]:
    urgency_rows: list[dict] = []

    escrow_rows = (
        await db.execute(
            text(
                """
                SELECT
                  o.id,
                  o.status::text AS status,
                  o.user_id,
                  u.full_name AS user_name,
                  o.trader_id,
                  t.full_name AS trader_name,
                  o.risk_score,
                  o.created_at,
                  o.updated_at
                FROM escrow.orders o
                LEFT JOIN paylink.users u ON u.user_id = o.user_id
                LEFT JOIN paylink.users t ON t.user_id = o.trader_id
                WHERE o.status::text IN ('REFUND_PENDING', 'PAYOUT_PENDING')
                   OR COALESCE(o.risk_score, 0) >= 80
                ORDER BY o.updated_at DESC
                LIMIT 200
                """
            )
        )
    ).mappings().all()
    escrow_workflows = await fetch_operator_workflow_map(
        db,
        entity_type="escrow_order",
        entity_ids=[str(row["id"]) for row in escrow_rows],
    )
    for row in escrow_rows:
        workflow = escrow_workflows.get(str(row["id"]))
        status = str(row.get("status") or "").upper()
        age_source = row.get("updated_at") or row.get("created_at")
        action_source = (workflow or {}).get("last_action_at") or age_source
        stale = status in {"REFUND_PENDING", "PAYOUT_PENDING"} and _is_older_than_hours(action_source, 6)
        high_risk = int(row.get("risk_score") or 0) >= 80
        if not stale and not high_risk and status not in {"REFUND_PENDING", "PAYOUT_PENDING"}:
            continue
        operator_status = (workflow or {}).get("operator_status") or ("blocked" if stale else "needs_follow_up")
        owner = (workflow or {}).get("owner_name") or (workflow or {}).get("owner_user_id") or row.get("trader_name") or row.get("trader_id") or "Backoffice"
        urgency_rows.append(
            OperatorUrgencyItemRead(
                id=f"escrow:{row['id']}",
                entity_type="escrow_order",
                entity_id=row["id"],
                kind="escrow",
                title=str(row["id"]),
                subtitle=f"{row.get('user_name') or row.get('user_id') or '-'} -> {row.get('trader_name') or row.get('trader_id') or '-'}",
                status=status,
                priority="critical" if stale or status == "REFUND_PENDING" or high_risk else "warning",
                operator_status=str(operator_status),
                age=_format_age_short(action_source),
                stale=stale,
                owner=str(owner),
                last_action_at=action_source,
                to=f"/dashboard/admin/escrow?queue={'stale' if stale else 'refund_pending' if status == 'REFUND_PENDING' else 'payout_pending' if status == 'PAYOUT_PENDING' else 'high_risk'}",
                meta=(workflow or {}).get("blocked_reason")
                or (workflow or {}).get("notes")
                or (f"Risk {row.get('risk_score')}" if high_risk else status),
                operator_workflow=workflow,
            ).model_dump(mode="json")
        )

    dispute_rows = (
        await db.execute(
            text(
                """
                SELECT
                  d.dispute_id,
                  d.status::text AS status,
                  d.reason,
                  d.created_at,
                  d.resolved_at,
                  t.updated_at,
                  t.buyer_id,
                  ub.full_name AS buyer_name,
                  t.seller_id,
                  us.full_name AS seller_name,
                  d.opened_by,
                  uo.full_name AS opened_by_name
                FROM p2p.disputes d
                LEFT JOIN p2p.trades t ON t.trade_id = d.trade_id
                LEFT JOIN paylink.users ub ON ub.user_id = t.buyer_id
                LEFT JOIN paylink.users us ON us.user_id = t.seller_id
                LEFT JOIN paylink.users uo ON uo.user_id = d.opened_by
                WHERE d.status::text IN ('OPEN', 'UNDER_REVIEW')
                ORDER BY d.created_at DESC
                LIMIT 200
                """
            )
        )
    ).mappings().all()
    dispute_workflows = await fetch_operator_workflow_map(
        db,
        entity_type="p2p_dispute",
        entity_ids=[str(row["dispute_id"]) for row in dispute_rows],
    )
    for row in dispute_rows:
        workflow = dispute_workflows.get(str(row["dispute_id"]))
        status = str(row.get("status") or "").upper()
        age_source = row.get("updated_at") or row.get("created_at")
        action_source = (workflow or {}).get("last_action_at") or age_source
        stale = status in {"OPEN", "UNDER_REVIEW"} and _is_older_than_hours(action_source, 12)
        operator_status = (workflow or {}).get("operator_status") or ("blocked" if stale else "needs_follow_up")
        owner = (workflow or {}).get("owner_name") or (workflow or {}).get("owner_user_id") or row.get("opened_by_name") or "Arbitrage"
        urgency_rows.append(
            OperatorUrgencyItemRead(
                id=f"dispute:{row['dispute_id']}",
                entity_type="p2p_dispute",
                entity_id=row["dispute_id"],
                kind="p2p_dispute",
                title=str(row["dispute_id"]),
                subtitle=f"{row.get('buyer_name') or row.get('buyer_id') or '-'} / {row.get('seller_name') or row.get('seller_id') or '-'}",
                status=status,
                priority="critical" if stale else "warning",
                operator_status=str(operator_status),
                age=_format_age_short(action_source),
                stale=stale,
                owner=str(owner),
                last_action_at=action_source,
                to=f"/dashboard/admin/p2p/disputes?queue={'stale' if stale else 'to_review'}",
                meta=(workflow or {}).get("blocked_reason") or (workflow or {}).get("notes") or row.get("reason") or "P2P dispute",
                operator_workflow=workflow,
            ).model_dump(mode="json")
        )

    payment_rows = (
        await db.execute(
            text(
                """
                SELECT
                  p.intent_id,
                  p.merchant_reference,
                  p.status,
                  p.provider_channel,
                  p.provider_code,
                  p.currency_code,
                  p.amount,
                  p.payer_identifier,
                  p.created_at,
                  p.updated_at,
                  u.full_name AS user_name,
                  u.email AS user_email
                FROM paylink.payment_intents p
                LEFT JOIN paylink.users u ON u.user_id = p.user_id
                WHERE p.status NOT IN ('credited', 'cancelled')
                ORDER BY p.created_at DESC
                LIMIT 200
                """
            )
        )
    ).mappings().all()
    payment_workflows = await fetch_operator_workflow_map(
        db,
        entity_type="payment_intent",
        entity_ids=[str(row["intent_id"]) for row in payment_rows],
    )
    for row in payment_rows:
        workflow = payment_workflows.get(str(row["intent_id"]))
        status = str(row.get("status") or "").lower()
        age_source = row.get("updated_at") or row.get("created_at")
        action_source = (workflow or {}).get("last_action_at") or age_source
        stale = status in {"pending_provider", "settled", "failed"} and _is_older_than_hours(action_source, 2)
        operator_status = (workflow or {}).get("operator_status") or ("blocked" if stale or status == "failed" else "needs_follow_up")
        owner = (workflow or {}).get("owner_name") or (workflow or {}).get("owner_user_id") or row.get("provider_channel") or row.get("provider_code") or "Payments"
        urgency_rows.append(
            OperatorUrgencyItemRead(
                id=f"payment:{row['intent_id']}",
                entity_type="payment_intent",
                entity_id=row["intent_id"],
                kind="payment_intent",
                title=str(row.get("merchant_reference") or row["intent_id"]),
                subtitle=str(row.get("user_name") or row.get("user_email") or row.get("payer_identifier") or "-"),
                status=status,
                priority="critical" if stale or status == "failed" else "warning",
                operator_status=str(operator_status),
                age=_format_age_short(action_source),
                stale=stale,
                owner=str(owner),
                last_action_at=action_source,
                to=f"/dashboard/admin/payment-intents?queue={'stale' if stale else 'actionable'}",
                meta=(workflow or {}).get("blocked_reason")
                or (workflow or {}).get("notes")
                or f"{row.get('currency_code') or ''} {row.get('amount') or ''}".strip(),
                operator_workflow=workflow,
            ).model_dump(mode="json")
        )

    urgency_rows.sort(key=lambda item: str(item.get("last_action_at") or ""), reverse=True)
    return urgency_rows


def filter_operator_urgency_items(
    items: list[dict],
    *,
    kind: str | None = None,
    operator_status: str | None = None,
    owner_key: str | None = None,
    view: str | None = None,
    current_user_id: str | None = None,
    current_owner_label: str | None = None,
    q: str | None = None,
) -> list[dict]:
    normalized_kind = str(kind or "").strip().lower()
    normalized_status = str(operator_status or "").strip().lower()
    normalized_owner_key = _normalize_owner_label(owner_key)
    normalized_view = str(view or "").strip().lower()
    normalized_query = str(q or "").strip().lower()
    my_user_id = str(current_user_id or "")
    my_owner_label = _normalize_owner_label(current_owner_label)

    filtered: list[dict] = []
    for item in items:
        workflow = item.get("operator_workflow") or {}
        item_kind = str(item.get("kind") or "").lower()
        item_status = str(item.get("operator_status") or "").lower()
        item_owner_label = _normalize_owner_label(item.get("owner"))
        owner_user_id = str(workflow.get("owner_user_id") or "")
        has_owner = bool(item_owner_label or owner_user_id)
        is_mine = (my_user_id and owner_user_id == my_user_id) or (
            my_owner_label and item_owner_label == my_owner_label
        )

        if normalized_kind and normalized_kind != "all" and item_kind != normalized_kind:
            continue
        if normalized_status and normalized_status != "all" and item_status != normalized_status:
            continue
        if normalized_owner_key and normalized_owner_key != "all" and item_owner_label != normalized_owner_key:
            continue
        if normalized_view == "mine" and not is_mine:
            continue
        if normalized_view == "team" and is_mine:
            continue
        if normalized_view == "unassigned" and has_owner:
            continue
        if normalized_view == "blocked_only" and item_status != "blocked":
            continue
        if normalized_query:
            haystack = " ".join(
                str(item.get(field) or "")
                for field in ("title", "subtitle", "status", "meta", "owner")
            ).lower()
            if normalized_query not in haystack:
                continue
        filtered.append(item)
    return filtered
