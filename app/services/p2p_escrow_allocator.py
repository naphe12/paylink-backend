import secrets
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.p2p_trade import P2PTrade


def _normalize_network(network: str | None) -> str:
    return str(network or "POLYGON").strip().upper()


def _normalize_address(address: str | None) -> str:
    normalized = str(address or "").strip().lower()
    if not normalized:
        raise ValueError("Configured deposit address is missing")
    if normalized == "0x0000000000000000000000000000000000000000":
        raise ValueError("Configured deposit address is invalid")
    return normalized


def _build_deposit_ref(trade: P2PTrade) -> str:
    trade_id = str(getattr(trade, "trade_id", "") or "").replace("-", "").upper()
    return f"P2P-{trade_id[:12]}"


class P2PEscrowAddressProvider(Protocol):
    async def allocate(self, db: AsyncSession, trade: P2PTrade) -> str:
        ...


class SimulatedP2PEscrowAddressProvider:
    async def allocate(self, db: AsyncSession, trade: P2PTrade) -> str:
        fake_address = "0x" + secrets.token_hex(20)
        trade.escrow_network = _normalize_network(getattr(settings, "P2P_ESCROW_NETWORK", "POLYGON"))
        trade.escrow_deposit_addr = fake_address
        trade.escrow_deposit_ref = trade.escrow_deposit_ref or _build_deposit_ref(trade)
        trade.escrow_provider = "SIMULATED"
        trade.flags = sorted(set(list(trade.flags or []) + ["ESCROW_PROVIDER:SIMULATED"]))
        await db.flush()
        return fake_address


class ConfiguredP2PEscrowAddressProvider:
    async def allocate(self, db: AsyncSession, trade: P2PTrade) -> str:
        token = str(getattr(trade.token, "value", trade.token) or "").upper()
        if token == "USDC":
            address = getattr(settings, "PAYLINK_USDC_DEPOSIT_ADDRESS", "")
        elif token == "USDT":
            address = getattr(settings, "PAYLINK_USDT_DEPOSIT_ADDRESS", "")
        else:
            raise ValueError(f"Unsupported token for configured P2P escrow address: {token}")

        normalized_address = _normalize_address(address)
        trade.escrow_network = _normalize_network(getattr(settings, "P2P_ESCROW_NETWORK", "POLYGON"))
        trade.escrow_deposit_addr = normalized_address
        trade.escrow_deposit_ref = trade.escrow_deposit_ref or _build_deposit_ref(trade)
        trade.escrow_provider = "CONFIGURED"
        trade.flags = sorted(
            set(
                list(trade.flags or [])
                + [
                    "ESCROW_PROVIDER:CONFIGURED",
                    "ESCROW_ADDRESS_MODE:SHARED",
                    f"ESCROW_ADDRESS_REF:{trade.trade_id}",
                    f"ESCROW_DEPOSIT_REF:{trade.escrow_deposit_ref}",
                    f"ESCROW_EXPECTED_TOKEN:{token}",
                    f"ESCROW_EXPECTED_AMOUNT:{trade.token_amount}",
                ]
            )
        )
        await db.flush()
        return normalized_address


class P2PEscrowAllocator:
    @staticmethod
    def _provider() -> P2PEscrowAddressProvider:
        provider_name = str(getattr(settings, "P2P_ESCROW_ADDRESS_PROVIDER", "simulated") or "simulated").strip().lower()
        if provider_name == "configured":
            return ConfiguredP2PEscrowAddressProvider()
        return SimulatedP2PEscrowAddressProvider()

    @staticmethod
    async def allocate_address(db: AsyncSession, trade: P2PTrade):
        """
        Provider-based allocation:
        - simulated: unique fake address for dev/sandbox
        - configured: configured custody/shared deposit address with trade ref tagging
        """

        provider = P2PEscrowAllocator._provider()
        return await provider.allocate(db, trade)
