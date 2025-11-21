import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, APIWebSocketRoute

import app.schemas  # 👈 force la reconstruction des modèles interconnectés
from app.core.database import get_db
from app.logger import get_logger
from app.logger_middleware import LoggerMiddleware
from app.routers.auth import auth
from app.routers.ref import country
from app.routers.ref import exchange
from app.routers.wallet import   wallet
from app.routers.notifications import websocket as notif_ws
from app.routers.wallet import payments as wallet_payments
from app.routers.invoices import router as invoices_router
from app.routers.merchant import router as merchant_router
from app.routers.loans import router as loans_router
from app.routers.wallet import transactions
from app.services.tontine_rotation import process_tontine_rotations
from fastapi.middleware.cors import CORSMiddleware
import logging
logging.getLogger("websockets.client").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)
logger = get_logger("paylink")
app = FastAPI(title="PayLink API (Dev Mode)", version="0.1")

async def rotation_worker():
    async for db in get_db():
        while True:
            await process_tontine_rotations(db)
            await asyncio.sleep(60 * 60)  # Vérifie toutes les heures

# ✅ Ajout du middleware
app.add_middleware(LoggerMiddleware)
# Autoriser le frontend React/Flutter
# origins = [
#     "http://localhost:5173",  # Vite/React
#     "http://127.0.0.1:5173",
#     "http://localhost:3000",  # Autres ports React
#     "http://127.0.0.1:3000",
#     "*"  # à restreindre en production
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

origins = [
    "https://paylink-frontend-production.up.railway.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# @app.on_event("startup")
# async def startup():
#     await init_db()




app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
app.include_router(country.router, prefix="/api/countries", tags=["Countries"])
app.include_router(exchange.router)
app.include_router(notif_ws.router)
app.include_router(wallet_payments.router)
app.include_router(invoices_router)
app.include_router(merchant_router)
app.include_router(loans_router)
app.include_router(transactions.router)

from app.routers.wallet.transfer import router as transfer_router

app.include_router(transfer_router)


#from app.routers import ws   # ← ajoute ceci

#app.include_router(ws.router)  # ← ajoute ceci après les autres routers

from app.routers.tontines.tontines import router as tontine_router
from app.routers.ws import router as ws_router
app.include_router(tontine_router,prefix="/tontines", tags=["Tontines"])
app.include_router(ws_router)

from app.routers.ws import router as notifications_ws_router
app.include_router(notifications_ws_router)


from app.routers.admin.risk_admin import router as risk_admin_router
app.include_router(risk_admin_router)

from app.api.ws_security import router as ws_security_router
app.include_router(ws_security_router)

from app.routers.admin.admin_users import router as admin_users_router
from app.routers.admin.wallets_alerts import router as admin_wallets_router
from app.routers.admin.transfers_monitor import router as admin_transfers_router
from app.routers.admin.kyc_reviews import router as admin_kyc_router
from app.routers.admin.analytics import router as admin_analytics_router
from app.routers.admin.agents import router as admin_agents_router
from app.routers.admin.mobilemoney import router as admin_mobilemoney_router
from app.routers.admin.tontine_arrears import router as admin_tontine_arrears_router
from app.routers.admin.notifications import router as admin_notifications_router
from app.routers.admin.loan_stats import router as admin_loan_stats_router
from app.routers.admin.aml_events import router as admin_aml_router
from app.routers.admin.credit_history import router as admin_credit_history_router
from app.routers.admin.cash_requests import router as admin_cash_requests_router
app.include_router(admin_users_router)
app.include_router(admin_wallets_router)
app.include_router(admin_transfers_router)
app.include_router(admin_kyc_router)
app.include_router(admin_analytics_router)
app.include_router(admin_agents_router)
app.include_router(admin_mobilemoney_router)
app.include_router(admin_tontine_arrears_router)
app.include_router(admin_notifications_router)
app.include_router(admin_loan_stats_router)
app.include_router(admin_aml_router)
app.include_router(admin_credit_history_router)
app.include_router(admin_cash_requests_router)

from app.routers.agent.agent import router as agent_router
app.include_router(agent_router, prefix="/agent", tags=["Agent Operations"])

from app.routers.agent.agent_external_transfer import router as agent_router_extern
app.include_router(agent_router_extern)


from app.routers import debug
app.include_router(debug.router)

from app.routers import test_email
app.include_router(test_email.router)



@app.on_event("startup")
async def startup_event():
    print("📜 Routes disponibles :")
    for route in app.router.routes:
        if isinstance(route, APIRoute):  # ✅ route HTTP classique
            methods = ",".join(route.methods)
            print(f"{methods:10} {route.path}")
        elif isinstance(route, APIWebSocketRoute):  # ✅ route WebSocket
            print(f"{'WEBSOCKET':10} {route.path}")

@app.get("/")
async def root():
    return {"message": "🚀 PayLink backend en mode développement (sans Docker)"}
logger.info("🚀 Démarrage du backend PayLink...")
