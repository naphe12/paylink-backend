from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from models.escrow_event import EscrowEvent

class EscrowLedgerService:
    def __init__(self, ledger):
        self.ledger = ledger  # LedgerPort

    async def on_funded(self, db: AsyncSession, user_id, order_id, usdc_amount: Decimal):
        # Exemple: hold USDC (ou juste audit si fonds off-chain)
        res = await self.ledger.hold(user_id=user_id, currency="USDC", amount=usdc_amount, ref=f"escrow:{order_id}")
        await db.execute(
            "INSERT INTO escrow.ledger_links(order_id, action, currency, amount, external_entry_id) VALUES (:oid,:a,:c,:amt,:eid)",
            {"oid": order_id, "a": "HOLD_USDC", "c": "USDC", "amt": usdc_amount, "eid": res.entry_id}
        )
        db.add(EscrowEvent(order_id=order_id, event_type="LEDGER_HOLD_USDC", payload={"entry_id": res.entry_id}))

    async def on_swap(self, db: AsyncSession, user_id, order_id, usdc_amount: Decimal, usdt_amount: Decimal, fee_usdt: Decimal):
        # release hold + credit USDT net + fee
        r1 = await self.ledger.release(user_id=user_id, currency="USDC", amount=usdc_amount, ref=f"escrow:{order_id}")
        r2 = await self.ledger.credit(user_id=user_id, currency="USDT", amount=usdt_amount, ref=f"escrow:{order_id}")
        await db.execute(
            "INSERT INTO escrow.ledger_links(order_id, action, currency, amount, external_entry_id) VALUES (:oid,'RELEASE_USDC','USDC',:amt,:eid)",
            {"oid": order_id, "amt": usdc_amount, "eid": r1.entry_id}
        )
        await db.execute(
            "INSERT INTO escrow.ledger_links(order_id, action, currency, amount, external_entry_id) VALUES (:oid,'CREDIT_USDT','USDT',:amt,:eid)",
            {"oid": order_id, "amt": usdt_amount, "eid": r2.entry_id}
        )
        if fee_usdt > 0:
            r3 = await self.ledger.debit(user_id=user_id, currency="USDT", amount=fee_usdt, ref=f"escrow_fee:{order_id}")
            await db.execute(
                "INSERT INTO escrow.ledger_links(order_id, action, currency, amount, external_entry_id) VALUES (:oid,'FEE_USDT','USDT',:amt,:eid)",
                {"oid": order_id, "amt": fee_usdt, "eid": r3.entry_id}
            )
