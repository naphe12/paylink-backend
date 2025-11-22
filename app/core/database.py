# app/core/db.py
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Charger les variables d'environnement
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL manquant dans le fichier .env")

# IMPORTANT : asyncpg ne doit pas recevoir sslmode= dans l'URL, on passe le SSL via connect_args
engine = create_async_engine(
    DATABASE_URL,
    echo=True,         # désactiver en production
    future=True,
    pool_pre_ping=True,     # ré-ouvre si la connexion a été coupée (timeouts provider)
    pool_recycle=300,       # recycle après 5 min pour éviter les connexions mortes
    connect_args={
        "ssl": "require"   # compatible asyncpg + Neon + Railway
    }
)

# Session async
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# Base ORM
Base = declarative_base()

# Dependency FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

# INIT
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    print("Base de données initialisée (asynchrone).")
