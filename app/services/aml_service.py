from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.aml_engine import AMLEngine, AMLResult
from app.services.audit_service import audit_log


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
        "payload": payload,
    })

async def run_aml(
    db: AsyncSession,
    *,
    user,
    order,
    stage: str,
    actor_user_id: str | None,
    actor_role: str | None,
    ip: str | None,
    user_agent: str | None,
) -> AMLResult:
    result = await AMLEngine.screen(db, user=user, order=order, stage=stage)

    await db.execute(
        text("""
          INSERT INTO paylink.aml_screenings(user_id, order_id, stage, decision, score, hits)
          VALUES (CAST(:uid AS uuid), CAST(:oid AS uuid), :stage, :decision, :score, CAST(:hits AS jsonb))
        """),
        {
            "uid": str(user.user_id),
            "oid": str(order.id),
            "stage": stage,
            "decision": result.decision,
            "score": result.score,
            "hits": result.hits,
        },
    )

    # Flags sur order (champ flags text[])
    if result.decision == "REVIEW":
        await db.execute(
            text("""
              UPDATE escrow.orders
              SET flags = array(
                    SELECT DISTINCT unnest(COALESCE(flags, ARRAY[]::text[]) || ARRAY['AML_REVIEW']::text[])
                  ),
                  risk_score = GREATEST(COALESCE(risk_score, 0), :score)
              WHERE id = CAST(:oid AS uuid)
            """),
            {"oid": str(order.id), "score": result.score},
        )

    if result.decision == "BLOCK":
        await db.execute(
            text("""
              UPDATE escrow.orders
              SET flags = array(
                    SELECT DISTINCT unnest(COALESCE(flags, ARRAY[]::text[]) || ARRAY['AML_BLOCK']::text[])
                  ),
                  risk_score = 100
              WHERE id = CAST(:oid AS uuid)
            """),
            {"oid": str(order.id)},
        )

    await audit_log(
        db,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=f"AML_{stage}",
        entity_type="escrow_order",
        entity_id=str(order.id),
        before_state=None,
        after_state={"decision": result.decision, "score": result.score, "hits": result.hits},
        ip=ip,
        user_agent=user_agent,
    )

    if result.score >= 80:
        await enqueue_alert(
            db,
            type="AML_HIGH",
            severity="HIGH",
            user_id=str(user.user_id),
            order_id=str(order.id),
            payload={"stage": stage, "score": result.score, "hits": result.hits},
        )

    return result
