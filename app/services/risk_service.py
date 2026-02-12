from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

@dataclass
class RiskResult:
    score: int
    decision: str  # ALLOW / REVIEW / BLOCK
    reasons: list[str]

class RiskService:
    @staticmethod
    async def evaluate_create_order(
        db: AsyncSession,
        *,
        user,
        amount_usdc: float,
        ip: str | None,
    ) -> RiskResult:
        score = 0
        reasons: list[str] = []

        # --- Hard checks (block)
        if str(user.status) != "active":
            return RiskResult(100, "BLOCK", ["USER_INACTIVE"])

        if getattr(user, "external_transfers_blocked", False):
            return RiskResult(100, "BLOCK", ["TRANSFERS_BLOCKED"])

        # --- KYC
        kyc = str(getattr(user, "kyc_status", "unverified"))
        if kyc != "verified":
            score += 25
            reasons.append("KYC_NOT_VERIFIED")

        # --- Existing risk_score
        score += int(getattr(user, "risk_score", 0))
        if int(getattr(user, "risk_score", 0)) >= 80:
            reasons.append("HIGH_RISK_PROFILE")

        # --- Amount heuristics
        if amount_usdc >= 1000:
            score += 20
            reasons.append("HIGH_AMOUNT")
        elif amount_usdc >= 300:
            score += 10
            reasons.append("MEDIUM_AMOUNT")

        # --- Velocity: too many created not funded in last 60 min
        res = await db.execute(text("""
            SELECT COUNT(*)::int
            FROM escrow.orders
            WHERE user_id = CAST(:uid AS uuid)
              AND created_at >= now() - interval '60 minutes'
              AND status = 'CREATED'
        """), {"uid": str(user.user_id)})
        created_1h = res.scalar_one()

        if created_1h >= 3:
            score += 20
            reasons.append("TOO_MANY_CREATED_1H")

        # --- Optional: IP signals (very light)
        if ip:
            # If same IP hits many users -> suspicious (optional)
            pass

        decision = RiskService._decision_from_score(score)
        return RiskResult(score, decision, reasons)

    @staticmethod
    async def evaluate_funded(
        db: AsyncSession,
        *,
        user,
        order,
    ) -> RiskResult:
        score = int(getattr(user, "risk_score", 0))
        reasons: list[str] = []

        if str(getattr(user, "kyc_status", "unverified")) != "verified":
            score += 20
            reasons.append("KYC_NOT_VERIFIED")

        # Big funded amount => review
        amt = float(
            getattr(order, "usdc_received", None)
            or getattr(order, "usdc_expected", 0)
            or 0
        )
        if amt >= 2000:
            score += 25
            reasons.append("VERY_HIGH_AMOUNT_FUNDED")

        # Too many funded today
        res = await db.execute(text("""
            SELECT COUNT(*)::int
            FROM escrow.orders
            WHERE user_id = CAST(:uid AS uuid)
              AND created_at >= date_trunc('day', now())
              AND status IN ('FUNDED', 'SWAPPED', 'PAYOUT_PENDING', 'PAID_OUT')
        """), {"uid": str(user.user_id)})
        funded_today = res.scalar_one()
        if funded_today >= 5:
            score += 15
            reasons.append("HIGH_FUNDED_VOLUME_TODAY")

        decision = RiskService._decision_from_score(score)
        return RiskResult(score, decision, reasons)

    @staticmethod
    async def evaluate_payout(
        db: AsyncSession,
        *,
        user,
        order,
    ) -> RiskResult:
        score = int(getattr(user, "risk_score", 0))
        reasons: list[str] = []

        if str(user.status) != "active":
            return RiskResult(100, "BLOCK", ["USER_INACTIVE"])

        if getattr(user, "external_transfers_blocked", False):
            return RiskResult(100, "BLOCK", ["TRANSFERS_BLOCKED"])

        # payout stuck/failed patterns could add score (optional)
        decision = RiskService._decision_from_score(score)
        return RiskResult(score, decision, reasons)

    @staticmethod
    def _decision_from_score(score: int) -> str:
        if score >= 85:
            return "BLOCK"
        if score >= 60:
            return "REVIEW"
        return "ALLOW"

