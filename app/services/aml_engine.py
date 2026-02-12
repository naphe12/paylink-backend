from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

@dataclass
class AMLResult:
    score: int
    decision: str          # ALLOW / REVIEW / BLOCK
    hits: list[dict]       # [{"rule":"...", "points":.., "detail":...}]

class AMLEngine:
    @staticmethod
    async def screen(db: AsyncSession, *, user, order, stage: str) -> AMLResult:
        score = 0
        hits: list[dict] = []

        def add(rule: str, points: int, detail: str = ""):
            nonlocal score
            score += points
            hits.append({"rule": rule, "points": points, "detail": detail})

        # Hard blocks
        if str(user.status) != "active":
            return AMLResult(100, "BLOCK", [{"rule": "USER_INACTIVE", "points": 100, "detail": ""}])

        # KYC
        kyc = str(getattr(user, "kyc_status", "unverified"))
        if kyc != "verified":
            add("KYC_NOT_VERIFIED", 20, f"kyc={kyc}")

        # Amount heuristic (USDC expected)
        amount = float(getattr(order, "usdc_expected", 0) or 0)
        if amount >= 3000:
            add("VERY_HIGH_AMOUNT", 35, f"usdc_expected={amount}")
        elif amount >= 1000:
            add("HIGH_AMOUNT", 20, f"usdc_expected={amount}")
        elif amount >= 300:
            add("MEDIUM_AMOUNT", 10, f"usdc_expected={amount}")

        # Structuring: many small orders in 24h
        res = await db.execute(text("""
          SELECT COUNT(*)::int
          FROM escrow.orders
          WHERE user_id = CAST(:uid AS uuid)
            AND created_at >= now() - interval '24 hours'
            AND usdc_expected < 300
        """), {"uid": str(user.user_id)})
        small_24h = res.scalar_one()
        if small_24h >= 5:
            add("STRUCTURING_24H", 30, f"small_orders_24h={small_24h}")

        # Many CREATED but not funded in 60m
        res2 = await db.execute(text("""
          SELECT COUNT(*)::int
          FROM escrow.orders
          WHERE user_id = CAST(:uid AS uuid)
            AND created_at >= now() - interval '60 minutes'
            AND status = 'CREATED'
        """), {"uid": str(user.user_id)})
        created_60m = res2.scalar_one()
        if created_60m >= 3:
            add("VELOCITY_CREATED_60M", 20, f"created_60m={created_60m}")

        # Reused payout account across users (30 days)
        if getattr(order, "payout_account_number", None):
            res2 = await db.execute(text("""
              SELECT COUNT(DISTINCT user_id)::int
              FROM escrow.orders
              WHERE payout_account_number = :pt
                AND created_at >= now() - interval '30 days'
            """), {"pt": order.payout_account_number})
            users_same_target = res2.scalar_one()
            if users_same_target >= 3:
                add("MULTI_USERS_SAME_PAYOUT_ACCOUNT", 40, f"users={users_same_target}")

        # Deposit tx hash reused across users (if known at stage FUNDED/PAYOUT)
        tx_hash = str(getattr(order, "deposit_tx_hash", "") or "").strip()
        if tx_hash:
            res3 = await db.execute(text("""
              SELECT COUNT(DISTINCT user_id)::int
              FROM escrow.orders
              WHERE deposit_tx_hash = :tx
                AND created_at >= now() - interval '30 days'
            """), {"tx": tx_hash})
            users_same_tx = res3.scalar_one()
            if users_same_tx >= 2:
                add("TX_HASH_REUSED_MULTI_USERS", 50, f"users={users_same_tx}")

        # Existing AML/Risk context from user profile
        base_risk = int(getattr(user, "risk_score", 0) or 0)
        if base_risk >= 70:
            add("USER_RISK_HIGH", 15, f"user_risk={base_risk}")
        elif base_risk >= 40:
            add("USER_RISK_MED", 8, f"user_risk={base_risk}")

        # Existing AML flags on order can increase vigilance.
        flags = [str(f) for f in list(getattr(order, "flags", []) or [])]
        if any(flag.startswith("AML_REVIEW") for flag in flags):
            add("ORDER_ALREADY_AML_REVIEW", 15, "existing AML review flag")
        if any(flag.startswith("AML_BLOCK") for flag in flags):
            add("ORDER_ALREADY_AML_BLOCK", 40, "existing AML block flag")

        decision = AMLEngine._decision(score)
        return AMLResult(score, decision, hits)

    @staticmethod
    def _decision(score: int) -> str:
        if score >= 85:
            return "BLOCK"
        if score >= 60:
            return "REVIEW"
        return "ALLOW"
