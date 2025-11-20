# app/core/db.py
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import declarative_base

# Charger les variables d'environnement
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL manquant dans le fichier .env")

# 🔹 Crée le moteur asynchrone
engine = create_async_engine(
    DATABASE_URL,
    echo=True,         # affiche les requêtes SQL (désactive en prod)
    future=True
)

# 🔹 Session asynchrone
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# 🔹 Base ORM
Base = declarative_base()

# 🔹 Dépendance FastAPI pour injection
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

# 🔹 Initialisation de la DB (appelée au démarrage)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    print("✅ Base de données initialisée (asynchrone).")

