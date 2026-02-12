import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.risk_service import RiskResult

async def enqueue_alert(
    db: AsyncSession,
    *,
    type: str,
    severity: str,
    user_id: str | None,
    order_id: str | None,
    payload: dict,
):
    await db.execute(text("""
      INSERT INTO paylink.alerts(type, severity, user_id, order_id, payload)
      VALUES (:type, :severity, CAST(:user_id AS uuid), CAST(:order_id AS uuid), CAST(:payload AS jsonb))
    """), {
        "type": type,
        "severity": severity,
        "user_id": user_id,
        "order_id": order_id,
        "payload": json.dumps(payload),
    })

async def log_risk_decision(
    db: AsyncSession,
    *,
    user_id: str | None,
    order_id: str | None,
    stage: str,
    result: RiskResult,
):
    await db.execute(text("""
      INSERT INTO paylink.risk_decisions (user_id, order_id, stage, decision, score, reasons)
      VALUES (CAST(:user_id AS uuid), CAST(:order_id AS uuid), :stage, :decision, :score, CAST(:reasons AS jsonb))
    """), {
        "user_id": user_id,
        "order_id": order_id,
        "stage": stage,
        "decision": result.decision,
        "score": result.score,
        "reasons": json.dumps(result.reasons),
    })

    if result.score >= 80:
        await enqueue_alert(
            db,
            type="RISK_HIGH",
            severity="HIGH",
            user_id=user_id,
            order_id=order_id,
            payload={"stage": stage, "score": result.score, "reasons": result.reasons},
        )
