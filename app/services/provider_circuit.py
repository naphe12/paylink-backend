from sqlalchemy.ext.asyncio import AsyncSession

from app.services.circuit_breaker import circuit_allow, circuit_failure, circuit_success


def key_for(provider_name: str) -> str:
    return f"PAYOUT_CIRCUIT_{str(provider_name or '').upper()}"


async def allow_provider(db: AsyncSession, provider_name: str) -> bool:
    return await circuit_allow(db, key_for(provider_name))


async def provider_success(db: AsyncSession, provider_name: str):
    await circuit_success(db, key_for(provider_name))


async def provider_failure(db: AsyncSession, provider_name: str):
    await circuit_failure(db, key_for(provider_name))
