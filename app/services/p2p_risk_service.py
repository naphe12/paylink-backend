from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notifications
from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.models.users import Users


class P2PRiskService:
    @staticmethod
    async def score_trade(db: AsyncSession, trade: P2PTrade) -> tuple[int, list[str]]:
        score = 0
        flags: list[str] = []

        buyer = await db.scalar(select(Users).where(Users.user_id == trade.buyer_id))
        seller = await db.scalar(select(Users).where(Users.user_id == trade.seller_id))
        offer = await db.scalar(select(P2POffer).where(P2POffer.offer_id == trade.offer_id))

        # 1) KYC / user status
        if buyer and str(getattr(buyer, "kyc_status", "")).lower() != "verified":
            score += 15
            flags.append("BUYER_KYC_NOT_VERIFIED")
        if seller and str(getattr(seller, "kyc_status", "")).lower() != "verified":
            score += 10
            flags.append("SELLER_KYC_NOT_VERIFIED")

        buyer_status = str(getattr(buyer, "status", "")).lower() if buyer else ""
        seller_status = str(getattr(seller, "status", "")).lower() if seller else ""
        if buyer_status in ("frozen", "suspended", "closed"):
            score += 40
            flags.append("BUYER_BAD_STATUS")
        if seller_status in ("frozen", "suspended", "closed"):
            score += 40
            flags.append("SELLER_BAD_STATUS")

        # 2) Trade size
        if float(trade.bif_amount) >= 10_000_000:
            score += 10
            flags.append("LARGE_TRADE")

        # 3) Price outlier vs current active offer book median
        if offer:
            median_stmt = (
                select(func.percentile_cont(0.5).within_group(P2POffer.price_bif_per_usd))
                .where(
                    P2POffer.token == offer.token,
                    P2POffer.side == offer.side,
                    P2POffer.is_active.is_(True),
                )
            )
            median = (await db.execute(median_stmt)).scalar()
            if median and float(median) > 0:
                diff = abs(float(trade.price_bif_per_usd) - float(median)) / float(median)
                if diff > 0.10:
                    score += 10
                    flags.append("PRICE_OUTLIER")

        if score > 100:
            score = 100
        return score, flags

    @staticmethod
    async def apply(db: AsyncSession, trade: P2PTrade):
        previous_score = int(trade.risk_score or 0)
        score, flags = await P2PRiskService.score_trade(db, trade)
        trade.risk_score = score
        trade.flags = sorted(set(list(trade.flags or []) + flags))

        # Alert admins only when score crosses the high-risk threshold.
        if previous_score < 80 <= score:
            admin_rows = await db.execute(
                select(Users.user_id).where(Users.role == "admin")
            )
            admin_ids = admin_rows.scalars().all()
            if admin_ids:
                message = (
                    f"P2P trade {trade.trade_id} reached high-risk score {score}. "
                    f"Current status: {trade.status}."
                )
                notifications = [
                    Notifications(
                        user_id=admin_id,
                        channel="admin_realtime",
                        subject="High-risk P2P trade",
                        message=message,
                        metadata_={
                            "topic": "P2P_RISK",
                            "severity": "high",
                            "trade_id": str(trade.trade_id),
                            "score": score,
                            "flags": list(trade.flags or []),
                        },
                    )
                    for admin_id in admin_ids
                ]
                db.add_all(notifications)

        await db.flush()
        return score, flags
