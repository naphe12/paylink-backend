import secrets
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.p2p_trade import P2PTrade

class P2PEscrowAllocator:

    @staticmethod
    async def allocate_address(db: AsyncSession, trade: P2PTrade):
        """
        Pour l’instant :
        - adresse unique simulée
        - en prod: HD wallet dérivé / custody provider
        """

        # ⚠️ En prod : utiliser HD wallet
        fake_address = "0x" + secrets.token_hex(20)

        trade.escrow_network = "polygon_amoy"
        trade.escrow_deposit_addr = fake_address

        await db.flush()
        return fake_address
