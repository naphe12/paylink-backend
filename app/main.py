import asyncio
import logging
import time

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, APIWebSocketRoute

import app.schemas
from app.api.ws_security import router as ws_security_router
from app.api.ws_tracking import router as ws_tracking_router
from app.api.ops_payout import router as ops_payout_router
from app.api.ops_liquidity import router as ops_liquidity_router
from app.api.agent import router as agent_ops_router
from app.config import settings
from app.core.database import get_db
from app.logger import get_logger
from app.logger_middleware import LoggerMiddleware
from app.middlewares.rate_limit import RateLimitMiddleware
from app.middlewares.request_id import RequestIdMiddleware
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.routers import debug, test_email
from app.routers import backoffice_audit as backoffice_audit_router
from app.routers import backoffice_monitoring as backoffice_monitoring_router
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
from app.routers.admin_dashboard import router as admin_dashboard_router
from app.routers.admin_flags import router as admin_flags_router
from app.routers.admin_reports import router as admin_reports_router
from app.routers.agent.agent import router as agent_router
from app.routers.agent.agent_external_transfer import router as agent_router_extern
from app.routers.auth import auth
from app.routers.auth.change_password import router as change_password_router
from app.routers.admin_aml import router as admin_aml_cases_router
from app.routers.escrow import sandbox
from app.routers.escrow import backoffice_ledger as backoffice_ledger_router
from app.routers.escrow import escrow_backoffice as escrow_backoffice_router
from app.routers.escrow import escrow_audit_export as escrow_audit_export_router
from app.routers.escrow import escrow_audit_export_pdf as escrow_audit_export_pdf_router
from app.routers.escrow.backoffice_webhooks import router as backoffice_webhooks_router
from app.routers.escrow.escrow import router as escrow_router
from app.routers.escrow.escrow_webhook import router as escrow_webhook_router
from app.routers.health import router as health_router
from app.routers.invoices import router as invoices_router
from app.routers.loans import router as loans_router
from app.routers.merchant import router as merchant_router
from app.routers.metrics import router as metrics_router
from app.routers.meta import router as meta_router
from app.routers.notifications import websocket as notif_ws
from app.routers.bif_token import router as bif_router
from app.routers.ref import country, exchange
from app.routers.tontines.tontines import router as tontine_router
from app.routers.wallet import payments as wallet_payments
from app.routers.wallet import transactions, wallet
from app.routers.wallet.crypto_wallet import router as crypto_wallet_router
from app.routers.wallet.usdc_wallet import router as usdc_wallet_router
from app.routers.wallet.transfer import router as transfer_router
from app.routers.ws import router as ws_router
from app.services.backoffice_risk import router as backoffice_risk_router
from app.services.sandbox_transition_worker import run_sandbox_auto_transitions
from app.services.p2p_expiration_worker import run_p2p_expiration_worker
from app.services.tontine_rotation import process_tontine_rotations
from app.websocket_manager import admin_ws_join, admin_ws_leave
from app.workers.alerts_worker import deliver_alerts
from services.escrow_webhook_retry_worker import run_escrow_webhook_retry_worker

logging.getLogger("websockets.client").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)

logger = get_logger("paylink")
app = FastAPI(title="PayLink API (Dev Mode)", version="0.1")
background_tasks = []

if settings.APP_ENV == "prod":
    settings.SANDBOX_ENABLED = False


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


async def p2p_expiration_worker():
    async for db in get_db():
        while True:
            try:
                await run_p2p_expiration_worker(db)
            except Exception as exc:
                logger.error(f"P2P expiration worker error: {exc}")
            await asyncio.sleep(30)


default_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://paylink-frontend-production.up.railway.app",
    "https://web-production-448ce.up.railway.app",
}
configured_origins = {
    o.strip().rstrip("/")
    for o in str(settings.ALLOWED_ORIGINS or "").split(",")
    if o and o.strip()
}
origins = sorted(default_origins | configured_origins)

app.add_middleware(LoggerMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.state.rate_limits = {
    "default": 120,
    "auth": settings.RL_AUTH_PER_MIN,
    "p2p_write": settings.RL_P2P_WRITE_PER_MIN,
    "webhook": settings.RL_WEBHOOK_PER_MIN,
    "admin": settings.RL_ADMIN_PER_MIN,
}
app.add_middleware(RateLimitMiddleware, redis_url=settings.REDIS_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(change_password_router)
app.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
app.include_router(usdc_wallet_router)
app.include_router(crypto_wallet_router)
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
app.include_router(ws_tracking_router)
app.include_router(ops_payout_router)
app.include_router(ops_liquidity_router)
app.include_router(agent_ops_router)
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
app.include_router(metrics_router, prefix="/api")
app.include_router(bif_router, prefix="/api")
app.include_router(escrow_router)
app.include_router(escrow_webhook_router)
app.include_router(backoffice_webhooks_router)
app.include_router(backoffice_ledger_router.router)
app.include_router(escrow_backoffice_router.router)
app.include_router(escrow_audit_export_router.router)
app.include_router(escrow_audit_export_pdf_router.router)
app.include_router(sandbox.router)
app.include_router(backoffice_risk_router)
app.include_router(backoffice_audit_router.router)
app.include_router(backoffice_monitoring_router.router)
app.include_router(admin_aml_cases_router, prefix="/api")
app.include_router(admin_dashboard_router, prefix="/api")
app.include_router(admin_flags_router, prefix="/api")
app.include_router(admin_reports_router, prefix="/api")

from app.routers.p2p.p2p import router as p2p_router
from app.routers.p2p.admin_p2p import router as admin_p2p_router
from app.routers.p2p.admin_arbitrage import router as admin_arbitrage_router

app.include_router(p2p_router, prefix="/api")
app.include_router(admin_p2p_router, prefix="/api")
app.include_router(admin_arbitrage_router, prefix="/api")


@app.websocket("/ws/admin")
async def ws_admin(
    ws: WebSocket,
    topics: str | None = Query(default=None),
):
    topic_set = {t.strip() for t in (topics or "").split(",") if t.strip()}
    await admin_ws_join(ws, topic_set or None)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await admin_ws_leave(ws)
    except Exception:
        await admin_ws_leave(ws)


@app.on_event("startup")
async def startup_event():
    app.state.started_at_ts = time.time()
    background_tasks.append(asyncio.create_task(webhook_retry_worker()))
    background_tasks.append(asyncio.create_task(alerts_worker()))
    background_tasks.append(asyncio.create_task(p2p_expiration_worker()))
    if settings.APP_ENV != "prod" and settings.SANDBOX_ENABLED:
        background_tasks.append(asyncio.create_task(sandbox_transition_worker()))
    app.state.background_tasks = background_tasks

    logger.info(
        "Startup complete env=%s sandbox=%s cors_origins=%s bg_tasks=%s",
        settings.APP_ENV,
        settings.SANDBOX_ENABLED,
        len(origins),
        len(background_tasks),
    )

    print("Routes disponibles :")
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            methods = ",".join(route.methods)
            print(f"{methods:10} {route.path}")
        elif isinstance(route, APIWebSocketRoute):
            print(f"{'WEBSOCKET':10} {route.path}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.warning("Shutdown signal received; cancelling %s background task(s)", len(background_tasks))
    for t in background_tasks:
        t.cancel()
    logger.warning("Application shutdown complete")


@app.get("/")
async def root():
    return {"message": "PayLink backend en mode developpement"}


logger.info("Demarrage du backend PayLink...")
