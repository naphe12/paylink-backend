from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_admin

router = APIRouter(prefix="/admin/errors", tags=["Admin Error Logs"])


@router.get("")
@router.get("/")
async def list_app_errors(
    status_code: int | None = Query(None),
    error_type: str | None = Query(None),
    path: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    clauses = []
    params: dict[str, object] = {
        "limit": limit,
        "offset": offset,
    }

    if status_code is not None:
        clauses.append("status_code = :status_code")
        params["status_code"] = status_code
    if error_type:
        clauses.append("LOWER(error_type) = LOWER(:error_type)")
        params["error_type"] = error_type
    if path:
        clauses.append("request_path ILIKE :path")
        params["path"] = f"%{path}%"
    if q:
        clauses.append(
            """
            (
              message ILIKE :q
              OR COALESCE(stack_trace, '') ILIKE :q
              OR COALESCE(request_id, '') ILIKE :q
              OR request_path ILIKE :q
            )
            """
        )
        params["q"] = f"%{q}%"

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    result = await db.execute(
        text(
            f"""
            SELECT
              error_id,
              created_at,
              request_id,
              status_code,
              error_type,
              message,
              request_path,
              request_method,
              user_id,
              client_ip,
              handled,
              stack_trace,
              headers,
              query_params,
              request_body
            FROM paylink.app_errors
            {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )

    rows = result.mappings().all()
    return [
        {
            "error_id": str(row["error_id"]),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "request_id": row["request_id"],
            "status_code": row["status_code"],
            "error_type": row["error_type"],
            "message": row["message"],
            "request_path": row["request_path"],
            "request_method": row["request_method"],
            "user_id": str(row["user_id"]) if row["user_id"] else None,
            "client_ip": row["client_ip"],
            "handled": row["handled"],
            "stack_trace": row["stack_trace"],
            "headers": row["headers"] or {},
            "query_params": row["query_params"] or {},
            "request_body": row["request_body"],
        }
        for row in rows
    ]
