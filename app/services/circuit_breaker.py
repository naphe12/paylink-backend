from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

OPEN_AFTER_FAILURES = 5
COOLDOWN_SECONDS = 300  # 5 min

async def get_payout_circuit(db: AsyncSession) -> dict:
    res = await db.execute(text("SELECT value FROM paylink.system_flags WHERE key='PAYOUT_CIRCUIT'"))
    row = res.first()
    return row[0] if row else {"state":"CLOSED","failures":0,"opened_at":None}

async def set_payout_circuit(db: AsyncSession, value: dict):
    await db.execute(text("""
      UPDATE paylink.system_flags
      SET value=:value::jsonb, updated_at=now()
      WHERE key='PAYOUT_CIRCUIT'
    """), {"value": value})

async def circuit_allow_payout(db: AsyncSession) -> bool:
    st = await get_payout_circuit(db)
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

async def circuit_on_success(db: AsyncSession):
    await set_payout_circuit(db, {"state":"CLOSED","failures":0,"opened_at":None})

async def circuit_on_failure(db: AsyncSession):
    st = await get_payout_circuit(db)
    failures = int(st.get("failures", 0)) + 1
    state = st.get("state", "CLOSED")

    if failures >= OPEN_AFTER_FAILURES:
        await set_payout_circuit(db, {
            "state":"OPEN",
            "failures": failures,
            "opened_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        })
    else:
        await set_payout_circuit(db, {
            "state": state,
            "failures": failures,
            "opened_at": st.get("opened_at")
        })
