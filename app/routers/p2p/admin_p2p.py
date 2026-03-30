from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_admin  # you already have it
from app.models.users import Users
from app.models.p2p_trade import P2PTrade
from app.services.p2p_chain_deposit_service import (
    list_chain_deposits,
    get_chain_deposit_stats,
    assign_chain_deposit_to_trade,
    auto_assign_chain_deposit,
    get_chain_deposit_timeline,
)
from app.services.admin_p2p_read_service import (
    fetch_admin_trade_rows,
    fetch_admin_trade_detail_row,
    fetch_p2p_dispute_rows,
    fetch_legacy_dispute_rows,
    fetch_p2p_dispute_opened_audit_rows,
    fetch_p2p_dispute_resolved_audit_rows,
    fetch_latest_p2p_dispute_opened_state,
    fetch_latest_p2p_dispute_resolved_state,
)
from app.services.admin_p2p_projection import (
    serialize_admin_trade_summary,
    serialize_admin_trade_detail,
    serialize_admin_trade_csv_row,
    serialize_p2p_dispute_row,
    serialize_legacy_dispute_row,
    serialize_admin_dispute_csv_row,
    serialize_admin_chain_deposit_csv_row,
    serialize_p2p_dispute_opened_timeline_row,
    serialize_p2p_dispute_resolved_timeline_row,
    serialize_legacy_dispute_timeline_item,
    enrich_dispute_labels,
    enrich_timeline_item_labels,
    ADMIN_TRADE_CSV_HEADERS,
    ADMIN_DISPUTE_CSV_HEADERS,
    ADMIN_CHAIN_DEPOSIT_CSV_HEADERS,
)
from app.services.admin_export_response_service import (
    build_csv_download_response,
    build_json_download_response,
    normalize_export_format,
)
from app.services.admin_p2p_reference_service import get_dispute_code_catalog
from app.services.operator_workflow_service import fetch_operator_workflow_map

router = APIRouter(prefix="/admin/p2p", tags=["Admin P2P"])


async def _collect_admin_trades(db: AsyncSession, status: str | None = None) -> list[dict]:
    rows = await fetch_admin_trade_rows(db)
    trades = [serialize_admin_trade_summary(row) for row in rows.mappings().all()]

    if status:
        wanted = status.strip().upper()
        trades = [t for t in trades if str(t.get("status", "")).upper() == wanted]

    return trades


async def _get_admin_trade_detail(db: AsyncSession, trade_id: str) -> dict | None:
    row = await fetch_admin_trade_detail_row(db, trade_id)
    data = row.mappings().first()
    if not data:
        return None
    return serialize_admin_trade_detail(data)


async def _enrich_p2p_dispute_from_audit(db: AsyncSession, item: dict) -> dict:
    trade_id = item.get("trade_id")
    dispute_id = item.get("dispute_id")
    if trade_id:
        opened_row = await fetch_latest_p2p_dispute_opened_state(db, trade_id)
        opened_state = (opened_row.mappings().first() or {}).get("after_state") or {}
        if isinstance(opened_state, dict):
            item["reason_code"] = opened_state.get("reason_code")
            item["proof_type"] = opened_state.get("proof_type")
            item["proof_ref"] = opened_state.get("proof_ref")
    if dispute_id:
        resolved_row = await fetch_latest_p2p_dispute_resolved_state(db, dispute_id)
        resolved_state = (resolved_row.mappings().first() or {}).get("after_state") or {}
        if isinstance(resolved_state, dict):
            item["resolution_code"] = resolved_state.get("resolution_code")
            if not item.get("proof_type"):
                item["proof_type"] = resolved_state.get("proof_type")
            if not item.get("proof_ref"):
                item["proof_ref"] = resolved_state.get("proof_ref")
    return enrich_dispute_labels(item)




@router.get("/disputes/codes")
async def admin_dispute_codes(
    me: Users = Depends(get_current_admin),
):
    return get_dispute_code_catalog()


async def _load_p2p_dispute_timeline(
    db: AsyncSession,
    *,
    dispute_id: str | None,
    trade_id: str | None,
) -> list[dict]:
    timeline: list[dict] = []

    if trade_id:
        opened_rows = await fetch_p2p_dispute_opened_audit_rows(db, trade_id)
        for row in opened_rows.mappings().all():
            after_state = row.get("after_state") or {}
            if not isinstance(after_state, dict):
                after_state = {}
            timeline.append(
                enrich_timeline_item_labels(
                    serialize_p2p_dispute_opened_timeline_row(row, after_state)
                )
            )

    if dispute_id:
        resolved_rows = await fetch_p2p_dispute_resolved_audit_rows(db, dispute_id)
        for row in resolved_rows.mappings().all():
            before_state = row.get("before_state") or {}
            after_state = row.get("after_state") or {}
            if not isinstance(before_state, dict):
                before_state = {}
            if not isinstance(after_state, dict):
                after_state = {}
            timeline.append(
                enrich_timeline_item_labels(
                    serialize_p2p_dispute_resolved_timeline_row(row, before_state, after_state)
                )
            )

    timeline.sort(key=lambda item: item.get("created_at") or "", reverse=False)
    return timeline


def _load_legacy_dispute_timeline(dispute: dict) -> list[dict]:
    timeline: list[dict] = []
    created_at = dispute.get("created_at")
    updated_at = dispute.get("updated_at")
    status = dispute.get("status")
    reason = dispute.get("reason")
    evidence_url = dispute.get("evidence_url")

    timeline.append(
        serialize_legacy_dispute_timeline_item(
            item_id=f'{dispute.get("dispute_id")}:opened',
            action="LEGACY_DISPUTE_OPENED",
            actor_user_id=dispute.get("opened_by_user_id"),
            actor_role="CLIENT",
            created_at=created_at,
            dispute_status=status,
            reason=reason,
            evidence_url=evidence_url,
        )
    )

    if updated_at and updated_at != created_at:
        timeline.append(
            serialize_legacy_dispute_timeline_item(
                item_id=f'{dispute.get("dispute_id")}:updated',
                action="LEGACY_DISPUTE_UPDATED",
                actor_user_id=dispute.get("resolved_by_user_id") or dispute.get("opened_by_user_id"),
                actor_role="ADMIN" if dispute.get("resolved_by_user_id") else "CLIENT",
                created_at=updated_at,
                dispute_status=status,
                resolution=dispute.get("resolution"),
                evidence_url=evidence_url,
            )
        )

    return timeline


async def _collect_disputes(db: AsyncSession, status: str | None = None) -> list[dict]:
    disputes: list[dict] = []

    p2p_rows = await fetch_p2p_dispute_rows(db)
    for row in p2p_rows.mappings().all():
        disputes.append(serialize_p2p_dispute_row(row))

    # Legacy disputes table (schema paylink)
    legacy_rows = await fetch_legacy_dispute_rows(db)
    for row in legacy_rows.mappings().all():
        disputes.append(serialize_legacy_dispute_row(row))

    if status:
        wanted = status.strip().lower()
        disputes = [d for d in disputes if str(d.get("status", "")).lower() == wanted]

    for item in disputes:
        if str(item.get("source", "")).lower() != "p2p":
            enrich_dispute_labels(item)
            continue
        await _enrich_p2p_dispute_from_audit(db, item)

    workflow_map = await fetch_operator_workflow_map(
        db,
        entity_type="p2p_dispute",
        entity_ids=[item.get("dispute_id") for item in disputes if item.get("dispute_id")],
    )
    for item in disputes:
        item["operator_workflow"] = workflow_map.get(str(item.get("dispute_id")))

    disputes.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
    return disputes


@router.get("/deposits/settings")
async def admin_chain_deposit_settings(
    me: Users = Depends(get_current_admin),
):
    return {
        "auto_assign_min_score": int(settings.P2P_CHAIN_AUTO_ASSIGN_MIN_SCORE or 90),
    }


@router.get("/deposits/stats")
async def admin_chain_deposit_stats(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    return await get_chain_deposit_stats(db)


@router.get("/deposits/providers")
async def admin_chain_deposit_providers(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT TRIM(COALESCE(metadata->>'provider', '')) AS provider
                FROM p2p.chain_deposits
                WHERE TRIM(COALESCE(metadata->>'provider', '')) <> ''
                ORDER BY provider ASC
                """
            )
        )
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]

@router.get("/trades")
async def admin_list_trades(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    return await _collect_admin_trades(db, status=status)


@router.get("/trades/export")
async def export_admin_trades(
    status: str | None = None,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    trades = await _collect_admin_trades(db, status=status)
    normalized_format = normalize_export_format(format)
    filename_suffix = str(status or "all").strip().lower() or "all"

    if normalized_format == "json":
        return build_json_download_response(
            trades,
            filename=f"p2p_trades_{filename_suffix}.json",
        )

    return build_csv_download_response(
        headers=ADMIN_TRADE_CSV_HEADERS,
        rows=[serialize_admin_trade_csv_row(item) for item in trades],
        filename=f"p2p_trades_{filename_suffix}.csv",
    )


@router.get("/trades/{trade_id}")
async def admin_trade_detail(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    data = await _get_admin_trade_detail(db, trade_id)
    if not data:
        raise HTTPException(status_code=404, detail="Trade not found")
    return data


@router.get("/disputes")
async def list_disputes(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    return await _collect_disputes(db, status=status)


@router.get("/disputes/detail/{dispute_id}")
async def get_dispute_detail(
    dispute_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    disputes = await _collect_disputes(db, status=None)
    dispute = next((item for item in disputes if str(item.get("dispute_id")) == str(dispute_id)), None)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    dispute = enrich_dispute_labels(dispute)

    timeline = []
    if str(dispute.get("source", "")).lower() == "p2p":
        timeline = await _load_p2p_dispute_timeline(
            db,
            dispute_id=dispute.get("dispute_id"),
            trade_id=dispute.get("trade_id"),
        )
    else:
        timeline = _load_legacy_dispute_timeline(dispute)
    return {"dispute": dispute, "timeline": timeline}


@router.get("/disputes/export")
async def export_disputes(
    status: str | None = None,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    disputes = await _collect_disputes(db, status=status)
    normalized_format = normalize_export_format(format)
    filename_suffix = str(status or "all").strip().lower() or "all"

    if normalized_format == "json":
        return build_json_download_response(
            disputes,
            filename=f"p2p_disputes_{filename_suffix}.json",
        )

    return build_csv_download_response(
        headers=ADMIN_DISPUTE_CSV_HEADERS,
        rows=[serialize_admin_dispute_csv_row(item) for item in disputes],
        filename=f"p2p_disputes_{filename_suffix}.csv",
    )


@router.get("/risk")
async def risk_dashboard(
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    high_risk_stmt = select(func.count()).where(P2PTrade.risk_score >= 80)
    high_risk = (await db.execute(high_risk_stmt)).scalar()

    total_stmt = select(func.count()).select_from(P2PTrade)
    total = (await db.execute(total_stmt)).scalar()

    avg_stmt = select(func.avg(P2PTrade.risk_score))
    avg = (await db.execute(avg_stmt)).scalar()

    return {
        "total_trades": total,
        "high_risk_trades": high_risk,
        "average_risk": float(avg or 0),
    }


@router.get("/deposits")
async def admin_list_chain_deposits(
    status: str | None = None,
    query: str | None = None,
    token: str | None = None,
    source: str | None = None,
    provider: str | None = None,
    assignment_mode: str | None = None,
    sort_by: str | None = None,
    score_min: int | None = None,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    return await list_chain_deposits(
        db,
        status=status,
        query_text=query,
        token=token,
        source=source,
        provider=provider,
        assignment_mode=assignment_mode,
        sort_by=sort_by,
        score_min=score_min,
    )


@router.get("/deposits/export")
async def admin_export_chain_deposits(
    status: str | None = None,
    query: str | None = None,
    token: str | None = None,
    source: str | None = None,
    provider: str | None = None,
    assignment_mode: str | None = None,
    sort_by: str | None = None,
    score_min: int | None = None,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    items = await list_chain_deposits(
        db,
        status=status,
        query_text=query,
        token=token,
        source=source,
        provider=provider,
        assignment_mode=assignment_mode,
        sort_by=sort_by,
        score_min=score_min,
    )
    normalized_format = normalize_export_format(format)
    filename_suffix = str(status or "all").strip().lower() or "all"
    if query:
        filename_suffix += "_filtered"
    if token:
        filename_suffix += f"_{str(token).lower()}"
    if source:
        filename_suffix += f"_{str(source).lower()}"
    if provider:
        filename_suffix += f"_{str(provider).lower()}"
    if assignment_mode:
        filename_suffix += f"_{str(assignment_mode).lower()}"
    if score_min:
        filename_suffix += f"_score{int(score_min)}"

    if normalized_format == "json":
        return build_json_download_response(
            items,
            filename=f"p2p_chain_deposits_{filename_suffix}.json",
        )

    return build_csv_download_response(
        headers=ADMIN_CHAIN_DEPOSIT_CSV_HEADERS,
        rows=[serialize_admin_chain_deposit_csv_row(item) for item in items],
        filename=f"p2p_chain_deposits_{filename_suffix}.csv",
    )


@router.get("/deposits/{deposit_id}/timeline")
async def admin_chain_deposit_timeline(
    deposit_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    try:
        return await get_chain_deposit_timeline(db, deposit_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/deposits/{deposit_id}/assign")
async def admin_assign_chain_deposit(
    deposit_id: str,
    trade_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    try:
        return await assign_chain_deposit_to_trade(
            db,
            deposit_id=deposit_id,
            trade_id=trade_id,
            actor_user_id=str(me.user_id),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deposits/{deposit_id}/auto-assign")
async def admin_auto_assign_chain_deposit(
    deposit_id: str,
    db: AsyncSession = Depends(get_db),
    me: Users = Depends(get_current_admin),
):
    try:
        return await auto_assign_chain_deposit(
            db,
            deposit_id=deposit_id,
            actor_user_id=str(me.user_id),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
