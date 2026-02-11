import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, APIWebSocketRoute

import app.schemas
from app.api.ws_security import router as ws_security_router
from app.config import settings
from app.core.database import get_db
from app.logger import get_logger
from app.logger_middleware import LoggerMiddleware
from app.routers import debug, test_email
from app.routers.admin import analytics as admin_analytics_router
from app.routers.admin import agents as admin_agents_router
from app.routers.admin import aml_events as admin_aml_router
from app.routers.admin import cash_requests as admin_cash_requests_router
from app.routers.admin import credit_history as admin_credit_history_router
from app.routers.admin import credit_lines_admin as admin_credit_lines_router
from app.routers.admin import kyc_reviews as admin_kyc_router
from app.routers.admin import loan_collaterals as admin_loan_collaterals_router
from app.routers.admin import loan_documents as admin_loan_documents_router
from app.routers.admin import loan_penalties as admin_loan_penalties_router
from app.routers.admin import loan_products as admin_loan_products_router
from app.routers.admin import loan_stats as admin_loan_stats_router
from app.routers.admin import mobilemoney as admin_mobilemoney_router
from app.routers.admin import notifications as admin_notifications_router
from app.routers.admin import payment_requests as admin_payment_requests_router
from app.routers.admin import risk_admin as risk_admin_router
from app.routers.admin import settings as admin_settings_router
from app.routers.admin import tontine_arrears as admin_tontine_arrears_router
from app.routers.admin import transactions_audit as admin_transactions_audit_router
from app.routers.admin import transfers_monitor as admin_transfers_router
from app.routers.admin.admin_users import router as admin_users_router
from app.routers.admin.wallets_alerts import router as admin_wallets_router
from app.routers.agent.agent import router as agent_router
from app.routers.agent.agent_external_transfer import router as agent_router_extern
from app.routers.auth import auth
from app.routers.auth.change_password import router as change_password_router
from app.routers.escrow import sandbox
from app.routers.escrow.backoffice_webhooks import router as backoffice_webhooks_router
from app.routers.escrow.escrow import router as escrow_router
from app.routers.escrow.escrow_webhook import router as escrow_webhook_router
from app.routers.health import router as health_router
from app.routers.invoices import router as invoices_router
from app.routers.loans import router as loans_router
from app.routers.merchant import router as merchant_router
from app.routers.meta import router as meta_router
from app.routers.notifications import websocket as notif_ws
from app.routers.ref import country, exchange
from app.routers.tontines.tontines import router as tontine_router
from app.routers.wallet import payments as wallet_payments
from app.routers.wallet import transactions, wallet
from app.routers.wallet.transfer import router as transfer_router
from app.routers.ws import router as ws_router
from app.services.backoffice_risk import router as backoffice_risk_router
from app.services.sandbox_transition_worker import run_sandbox_auto_transitions
from app.services.tontine_rotation import process_tontine_rotations
from app.workers.alerts_worker import deliver_alerts
from services.escrow_webhook_retry_worker import run_escrow_webhook_retry_worker

logging.getLogger("websockets.client").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)

logger = get_logger("paylink")
app = FastAPI(title="PayLink API (Dev Mode)", version="0.1")
background_tasks = []


async def webhook_retry_worker():
    async for db in get_db():
        while True:
            try:
                await run_escrow_webhook_retry_worker(db)
            except Exception as exc:
                logger.error(f"Webhook retry worker error: {exc}")
            await asyncio.sleep(60)


async def sandbox_transition_worker():
    async for db in get_db():
        while True:
            try:
                await run_sandbox_auto_transitions(db)
            except Exception as exc:
                logger.error(f"Sandbox transition worker error: {exc}")
            await asyncio.sleep(5)


async def alerts_worker():
    async for db in get_db():
        while True:
            try:
                await deliver_alerts(db)
            except Exception as exc:
                logger.error(f"Alerts worker error: {exc}")
            await asyncio.sleep(60)


app.add_middleware(LoggerMiddleware)

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


app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(change_password_router)
app.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
app.include_router(country.router, prefix="/api/countries", tags=["Countries"])
app.include_router(exchange.router)
app.include_router(notif_ws.router)
app.include_router(wallet_payments.router)
app.include_router(admin_loan_products_router.router)
app.include_router(admin_loan_penalties_router.router)
app.include_router(admin_loan_collaterals_router.router)
app.include_router(admin_loan_documents_router.router)
app.include_router(admin_payment_requests_router.router)
app.include_router(invoices_router)
app.include_router(merchant_router)
app.include_router(loans_router)
app.include_router(transactions.router)
app.include_router(transfer_router)
app.include_router(tontine_router, prefix="/tontines", tags=["Tontines"])
app.include_router(ws_router)
app.include_router(ws_router)
app.include_router(risk_admin_router.router)
app.include_router(ws_security_router)
app.include_router(admin_users_router)
app.include_router(admin_wallets_router)
app.include_router(admin_transfers_router.router)
app.include_router(admin_settings_router.router)
app.include_router(admin_kyc_router.router)
app.include_router(admin_analytics_router.router)
app.include_router(admin_agents_router.router)
app.include_router(admin_mobilemoney_router.router)
app.include_router(admin_tontine_arrears_router.router)
app.include_router(admin_credit_lines_router.router)
app.include_router(admin_notifications_router.router)
app.include_router(admin_loan_stats_router.router)
app.include_router(admin_aml_router.router)
app.include_router(admin_credit_history_router.router)
app.include_router(admin_cash_requests_router.router)
app.include_router(admin_transactions_audit_router.router)
app.include_router(agent_router, prefix="/agent", tags=["Agent Operations"])
app.include_router(agent_router_extern)
app.include_router(debug.router)
app.include_router(meta_router)
app.include_router(test_email.router)
app.include_router(health_router)
app.include_router(escrow_router)
app.include_router(escrow_webhook_router)
app.include_router(backoffice_webhooks_router)
app.include_router(sandbox.router)
app.include_router(backoffice_risk_router)


@app.on_event("startup")
async def startup_event():
    background_tasks.append(asyncio.create_task(webhook_retry_worker()))
    background_tasks.append(asyncio.create_task(alerts_worker()))
    if settings.APP_ENV != "prod" and settings.SANDBOX_ENABLED:
        background_tasks.append(asyncio.create_task(sandbox_transition_worker()))

    print("Routes disponibles :")
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            methods = ",".join(route.methods)
            print(f"{methods:10} {route.path}")
        elif isinstance(route, APIWebSocketRoute):
            print(f"{'WEBSOCKET':10} {route.path}")


@app.get("/")
async def root():
    return {"message": "PayLink backend en mode developpement"}


logger.info("Demarrage du backend PayLink...")
