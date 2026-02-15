from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _ensure_table(db: AsyncSession):
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.system_flags (
              key text PRIMARY KEY,
              value boolean NOT NULL DEFAULT false,
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO paylink.system_flags(key, value)
            VALUES ('KILL_SWITCH', false)
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


async def get_flag(db: AsyncSession, key: str) -> bool:
    await _ensure_table(db)
    q = text("SELECT value FROM paylink.system_flags WHERE key=:k")
    row = (await db.execute(q, {"k": key})).first()
    return bool(row[0]) if row else False


async def set_flag(db: AsyncSession, key: str, value: bool):
    await _ensure_table(db)
    q = text(
        """
      INSERT INTO paylink.system_flags(key, value)
      VALUES (:k, :v)
      ON CONFLICT (key) DO UPDATE
      SET value = EXCLUDED.value, updated_at = now()
    """
    )
    await db.execute(q, {"k": key, "v": value})
