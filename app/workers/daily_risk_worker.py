from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def recompute_daily_risk(db: AsyncSession):
    # Exemple simple : base 0..100
    # +20 si KYC pas verified
    # +20 si >=3 webhooks failed (7d)
    # +20 si >=2 payout failed (7d)
    # +10 si >5 orders created (24h)

    await db.execute(text("""
      UPDATE paylink.users u
      SET risk_score = LEAST(100, GREATEST(0,
        (CASE WHEN u.kyc_status <> 'verified' THEN 20 ELSE 0 END)
        +
        (SELECT CASE WHEN COUNT(*) >= 3 THEN 20 ELSE 0 END
         FROM escrow.webhook_logs w
         WHERE w.created_at >= now() - interval '7 days'
           AND w.status='FAILED'
           AND w.order_id IN (SELECT id FROM escrow.orders o WHERE o.user_id=u.user_id)
        )
        +
        (SELECT CASE WHEN COUNT(*) >= 2 THEN 20 ELSE 0 END
         FROM paylink.audit_log a
         WHERE a.created_at >= now() - interval '7 days'
           AND a.action='ESCROW_PAYOUT_FAILED'
           AND a.actor_user_id IS NOT NULL
           AND a.entity_id IN (SELECT id FROM escrow.orders o WHERE o.user_id=u.user_id)
        )
        +
        (SELECT CASE WHEN COUNT(*) > 5 THEN 10 ELSE 0 END
         FROM escrow.orders o2
         WHERE o2.user_id=u.user_id
           AND o2.created_at >= now() - interval '24 hours'
        )
      ))
      WHERE TRUE
    """))

    await db.commit()
