from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

OPEN_AFTER_FAILURES = 5
COOLDOWN_SECONDS = 300  # 5 min
DEFAULT_PAYOUT_CIRCUIT_KEY = "PAYOUT_CIRCUIT"


async def _get(db: AsyncSession, key: str) -> dict:
    res = await db.execute(
        text("SELECT value FROM paylink.system_flags WHERE key=:k"),
        {"k": key},
    )
    row = res.first()
    return row[0] if row else {"state": "CLOSED", "failures": 0, "opened_at": None}


async def _set(db: AsyncSession, key: str, value: dict):
    await db.execute(
        text(
            """
            INSERT INTO paylink.system_flags(key, value)
            VALUES (:k, CAST(:v AS jsonb))
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """
        ),
        {"k": key, "v": value},
    )


async def circuit_allow(db: AsyncSession, key: str) -> bool:
    st = await _get(db, key)
    if st.get("state") != "OPEN":
        return True

    opened_at = st.get("opened_at")
    if not opened_at:
        return False

    # cooldown
    opened_dt = datetime.fromisoformat(opened_at.replace("Z","+00:00"))
    if datetime.now(timezone.utc) - opened_dt > timedelta(seconds=COOLDOWN_SECONDS):
        # half-open behavior: allow 1 attempt then close on success/fail handled by caller
        return True
    return False


async def circuit_success(db: AsyncSession, key: str):
    await _set(db, key, {"state": "CLOSED", "failures": 0, "opened_at": None})


async def circuit_failure(db: AsyncSession, key: str):
    st = await _get(db, key)
    failures = int(st.get("failures", 0)) + 1
    state = st.get("state", "CLOSED")

    if failures >= OPEN_AFTER_FAILURES:
        await _set(
            db,
            key,
            {
                "state": "OPEN",
                "failures": failures,
                "opened_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )
    else:
        await _set(
            db,
            key,
            {
                "state": state,
                "failures": failures,
                "opened_at": st.get("opened_at"),
            },
        )


# Backward-compatible API used by existing payout code.
async def get_circuit(db: AsyncSession, key: str) -> dict:
    return await _get(db, key)


async def set_circuit(db: AsyncSession, key: str, value: dict):
    await _set(db, key, value)


async def get_payout_circuit(db: AsyncSession) -> dict:
    return await get_circuit(db, DEFAULT_PAYOUT_CIRCUIT_KEY)


async def set_payout_circuit(db: AsyncSession, value: dict):
    await set_circuit(db, DEFAULT_PAYOUT_CIRCUIT_KEY, value)


async def circuit_allow_payout(db: AsyncSession) -> bool:
    return await circuit_allow(db, DEFAULT_PAYOUT_CIRCUIT_KEY)


async def circuit_on_success(db: AsyncSession):
    await circuit_success(db, DEFAULT_PAYOUT_CIRCUIT_KEY)


async def circuit_on_failure(db: AsyncSession):
    await circuit_failure(db, DEFAULT_PAYOUT_CIRCUIT_KEY)
