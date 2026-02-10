from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.escrow_policy import EscrowPolicy

class PolicyService:
    @staticmethod
    async def get(db: AsyncSession, key: str, default=None):
        res = await db.execute(select(EscrowPolicy).where(EscrowPolicy.policy_key == key, EscrowPolicy.active == True))
        row = res.scalar_one_or_none()
        return row.policy_value if row else default
