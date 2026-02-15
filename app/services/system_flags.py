import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _ensure_table(db: AsyncSession):
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.system_flags (
              key text PRIMARY KEY,
              value jsonb NOT NULL DEFAULT 'false'::jsonb,
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


async def _value_column_type(db: AsyncSession) -> str:
    row = (
        await db.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = 'paylink'
                  AND table_name = 'system_flags'
                  AND column_name = 'value'
                LIMIT 1
                """
            )
        )
    ).first()
    return str(row[0]).lower() if row and row[0] else "jsonb"


def _coerce_bool(raw) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        v = raw.strip().lower()
        if v in {"true", "1", "yes", "on"}:
            return True
        if v in {"false", "0", "no", "off", ""}:
            return False
        try:
            parsed = json.loads(raw)
            return _coerce_bool(parsed)
        except Exception:
            return False
    if isinstance(raw, dict):
        if "value" in raw:
            return _coerce_bool(raw.get("value"))
        if "enabled" in raw:
            return _coerce_bool(raw.get("enabled"))
        return False
    return bool(raw)


async def _ensure_default_kill_switch(db: AsyncSession):
    value_type = await _value_column_type(db)
    if value_type == "boolean":
        await db.execute(
            text(
                """
                INSERT INTO paylink.system_flags(key, value)
                VALUES ('KILL_SWITCH', false)
                ON CONFLICT (key) DO NOTHING
                """
            )
        )
    else:
        await db.execute(
            text(
                """
                INSERT INTO paylink.system_flags(key, value)
                VALUES ('KILL_SWITCH', 'false'::jsonb)
                ON CONFLICT (key) DO NOTHING
                """
            )
        )


async def get_flag(db: AsyncSession, key: str) -> bool:
    await _ensure_table(db)
    await _ensure_default_kill_switch(db)
    q = text("SELECT value FROM paylink.system_flags WHERE key=:k")
    row = (await db.execute(q, {"k": key})).first()
    return _coerce_bool(row[0]) if row else False


async def set_flag(db: AsyncSession, key: str, value: bool):
    await _ensure_table(db)
    value_type = await _value_column_type(db)
    if value_type == "boolean":
        q = text(
            """
          INSERT INTO paylink.system_flags(key, value)
          VALUES (:k, :v)
          ON CONFLICT (key) DO UPDATE
          SET value = EXCLUDED.value, updated_at = now()
        """
        )
        await db.execute(q, {"k": key, "v": bool(value)})
    else:
        q = text(
            """
          INSERT INTO paylink.system_flags(key, value)
          VALUES (:k, CAST(:v AS jsonb))
          ON CONFLICT (key) DO UPDATE
          SET value = EXCLUDED.value, updated_at = now()
        """
        )
        await db.execute(q, {"k": key, "v": json.dumps(bool(value))})
