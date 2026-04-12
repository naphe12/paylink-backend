import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


def compute_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class IdempotencyAcquireResult:
    accepted: bool
    conflict: bool = False
    in_progress: bool = False
    replay_status: int | None = None
    replay_payload: Any | None = None


async def ensure_idempotency_schema(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            ALTER TABLE paylink.idempotency_keys
            ADD COLUMN IF NOT EXISTS request_hash text
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE paylink.idempotency_keys
            ADD COLUMN IF NOT EXISTS response_status integer
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE paylink.idempotency_keys
            ADD COLUMN IF NOT EXISTS response_payload jsonb
            """
        )
    )
    await db.commit()


async def acquire_idempotency(
    db: AsyncSession,
    *,
    key: str,
    request_hash: str,
) -> IdempotencyAcquireResult:
    stale_after_seconds = max(
        10,
        int(getattr(settings, "IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS", 120) or 120),
    )

    inserted = await db.execute(
        text(
            """
            INSERT INTO paylink.idempotency_keys (client_key, request_hash)
            VALUES (:key, :request_hash)
            ON CONFLICT (client_key) DO NOTHING
            RETURNING key_id
            """
        ),
        {"key": key, "request_hash": request_hash},
    )
    accepted = inserted.first() is not None

    row_q = await db.execute(
        text(
            """
            SELECT request_hash, response_status, response_payload
            FROM paylink.idempotency_keys
            WHERE client_key = :key
            LIMIT 1
            """
        ),
        {"key": key},
    )
    row = row_q.mappings().first()
    if not row:
        return IdempotencyAcquireResult(accepted=accepted)

    existing_hash = row["request_hash"]
    if existing_hash and existing_hash != request_hash:
        return IdempotencyAcquireResult(accepted=False, conflict=True)

    if row["response_payload"] is not None:
        return IdempotencyAcquireResult(
            accepted=False,
            replay_status=int(row["response_status"] or 200),
            replay_payload=row["response_payload"],
        )

    if accepted:
        return IdempotencyAcquireResult(accepted=True)

    stale_takeover = await db.execute(
        text(
            """
            UPDATE paylink.idempotency_keys
            SET request_hash = :request_hash,
                response_status = NULL,
                response_payload = NULL,
                created_at = now()
            WHERE client_key = :key
              AND response_payload IS NULL
              AND (
                created_at IS NULL
                OR created_at < (now() - make_interval(secs => :stale_after_seconds))
              )
            RETURNING key_id
            """
        ),
        {
            "key": key,
            "request_hash": request_hash,
            "stale_after_seconds": stale_after_seconds,
        },
    )
    if stale_takeover.first() is not None:
        return IdempotencyAcquireResult(accepted=True)

    return IdempotencyAcquireResult(accepted=False, in_progress=True)


async def store_idempotency_response(
    db: AsyncSession,
    *,
    key: str,
    status_code: int,
    payload: Any,
) -> None:
    await db.execute(
        text(
            """
            UPDATE paylink.idempotency_keys
            SET response_status = :status_code,
                response_payload = CAST(:payload AS jsonb)
            WHERE client_key = :key
            """
        ),
        {
            "key": key,
            "status_code": status_code,
            "payload": json.dumps(payload, default=str),
        },
    )
