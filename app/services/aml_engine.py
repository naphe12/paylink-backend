from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.aml_case import AMLCase
from app.models.aml_hit import AMLHit
from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.models.users import Users
from app.services.aml_builtin_rules import (
    AMLContext,
    rule_fast_repeat,
    rule_large_trade_bif,
    rule_new_account,
    rule_price_outlier,
    rule_unverified_kyc,
)
from app.services.alerts import deliver_alerts

AML_ALERT_THRESHOLD = 80
AML_CASE_THRESHOLD = 80

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

    @staticmethod
    async def evaluate_p2p(db: AsyncSession, trade: P2PTrade, event: str) -> dict:
        """
        Return:
        {
          "score_delta": int,
          "hits": [..],
          "should_alert": bool,
          "should_open_case": bool
        }
        """
        now = datetime.now(timezone.utc)
        ctx = AMLContext(event=event, now=now)

        buyer = await db.scalar(select(Users).where(Users.user_id == trade.buyer_id))
        seller = await db.scalar(select(Users).where(Users.user_id == trade.seller_id))
        offer = await db.scalar(select(P2POffer).where(P2POffer.offer_id == trade.offer_id))

        if not buyer or not seller or not offer:
            return {
                "score_delta": 0,
                "hits": [],
                "final_score": int(getattr(trade, "risk_score", 0) or 0),
                "should_alert": False,
                "should_open_case": False,
            }

        hits = []
        total_delta = 0

        # 1) KYC
        for r in (
            rule_unverified_kyc(str(buyer.kyc_status), "BUYER"),
            rule_unverified_kyc(str(seller.kyc_status), "SELLER"),
        ):
            if r:
                hits.append(r)
                total_delta += r[1]

        # 2) New account (if created_at exists)
        try:
            buyer_age_days = (date.today() - buyer.created_at.date()).days if buyer.created_at else 9999
            seller_age_days = (date.today() - seller.created_at.date()).days if seller.created_at else 9999
            for r in (rule_new_account(buyer_age_days), rule_new_account(seller_age_days)):
                if r:
                    hits.append(r)
                    total_delta += r[1]
        except Exception:
            pass

        # 3) Large trade
        r = rule_large_trade_bif(Decimal(trade.bif_amount))
        if r:
            hits.append(r)
            total_delta += r[1]

        # 4) Rapid repeats (trades in last 1h per buyer)
        one_hour_ago = now - timedelta(hours=1)
        buyer_count_stmt = (
            select(func.count())
            .select_from(P2PTrade)
            .where(P2PTrade.buyer_id == buyer.user_id, P2PTrade.created_at >= one_hour_ago)
        )
        buyer_count = (await db.execute(buyer_count_stmt)).scalar() or 0
        r = rule_fast_repeat(int(buyer_count))
        if r:
            hits.append(r)
            total_delta += r[1]

        # 5) Price outlier vs median order book
        median_stmt = select(func.percentile_cont(0.5).within_group(P2POffer.price_bif_per_usd)).where(
            P2POffer.token == offer.token,
            P2POffer.side == offer.side,
            P2POffer.is_active.is_(True),
        )
        median = (await db.execute(median_stmt)).scalar()
        if median and float(median) > 0:
            diff = abs(float(trade.price_bif_per_usd) - float(median)) / float(median)
            r = rule_price_outlier(diff)
            if r:
                hits.append(r)
                total_delta += r[1]

        # Persist hits
        for (code, delta, details) in hits:
            db.add(
                AMLHit(
                    user_id=buyer.user_id,
                    trade_id=trade.trade_id,
                    rule_code=code,
                    score_delta=int(delta),
                    details={"event": ctx.event, **details},
                )
            )

        # Decision based on trade risk_score + aml deltas
        final_score = min(100, int(trade.risk_score) + int(total_delta))
        should_alert = final_score >= AML_ALERT_THRESHOLD
        should_open_case = final_score >= AML_CASE_THRESHOLD
        auto_frozen = False

        if settings.AML_AUTO_FREEZE_ENABLED and final_score >= settings.AML_AUTO_FREEZE_THRESHOLD:
            buyer.status = "frozen"
            trade.flags = sorted(set((trade.flags or []) + ["AML_AUTO_FROZEN"]))
            auto_frozen = True

        # Open/update case (one open case per trade)
        if should_open_case:
            existing = await db.scalar(
                select(AMLCase).where(AMLCase.trade_id == trade.trade_id, AMLCase.status == "OPEN")
            )
            if not existing:
                db.add(
                    AMLCase(
                        user_id=buyer.user_id,
                        trade_id=trade.trade_id,
                        status="OPEN",
                        risk_score=final_score,
                        reason=f"AML score {final_score} triggered by event {event}",
                    )
                )
            else:
                existing.risk_score = max(int(existing.risk_score or 0), final_score)

        await db.flush()
        if auto_frozen:
            await deliver_alerts(
                db,
                subject="AML AUTO-FREEZE",
                message=f"User {buyer.user_id} frozen. Trade {trade.trade_id}, score={final_score}",
                metadata={
                    "user_id": str(buyer.user_id),
                    "trade_id": str(trade.trade_id),
                    "score": final_score,
                },
            )

        return {
            "score_delta": int(total_delta),
            "hits": [{"code": c, "delta": d, "details": det} for (c, d, det) in hits],
            "final_score": final_score,
            "should_alert": should_alert,
            "should_open_case": should_open_case,
        }
