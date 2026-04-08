import asyncio
from datetime import datetime, timedelta, timezone
import inspect
import json
import logging
import time
import traceback
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute, APIWebSocketRoute
from jose import JWTError, jwt
from sqlalchemy import text

import app.schemas
from app.ai.router import router as ai_router
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
from app.routers.admin import ai_feedback as admin_ai_feedback_router
from app.routers.admin import audit_search as admin_audit_search_router
from app.routers.admin import ops_workflow as admin_ops_workflow_router
from app.routers.admin import payments as admin_payments_router
from app.routers.admin import aml_events as admin_aml_router
from app.routers.admin import cash_requests as admin_cash_requests_router
from app.routers.admin import credit_history as admin_credit_history_router
from app.routers.admin import credit_lines_admin as admin_credit_lines_router
from app.routers.admin import error_logs as admin_error_logs_router
from app.routers.admin import kyc_reviews as admin_kyc_router
from app.routers.admin import loan_collaterals as admin_loan_collaterals_router
from app.routers.admin import loan_documents as admin_loan_documents_router
from app.routers.admin import loan_penalties as admin_loan_penalties_router
from app.routers.admin import loan_products as admin_loan_products_router
from app.routers.admin import loan_stats as admin_loan_stats_router
from app.routers.admin import mobilemoney as admin_mobilemoney_router
from app.routers.admin import notifications as admin_notifications_router
from app.routers.admin import payment_requests as admin_payment_requests_router
from app.routers.admin import product_automation as admin_product_automation_router
from app.routers.admin import support_cases as admin_support_cases_router
from app.routers.admin import virtual_cards as admin_virtual_cards_router
from app.routers.admin import agent_offline_operations as admin_agent_offline_router
from app.routers.admin import risk_admin as risk_admin_router
from app.routers.admin import settings as admin_settings_router
from app.routers.admin import tontine_arrears as admin_tontine_arrears_router
from app.routers.admin import transactions_audit as admin_transactions_audit_router
from app.routers.admin import transfers_monitor as admin_transfers_router
from app.routers.admin import users_limits as admin_users_limits_router
from app.routers.admin import wallet_analysis as admin_wallet_analysis_router
from app.routers.admin.admin_users import router as admin_users_router
from app.routers.admin.wallets_alerts import router as admin_wallets_router
from app.routers.admin_dashboard import router as admin_dashboard_router
from app.routers.admin_flags import router as admin_flags_router
from app.routers.admin_reports import router as admin_reports_router
from app.routers.agent.agent import router as agent_router
from app.routers.agent.offline_operations import router as agent_offline_router
from app.routers.agent.chat import router as agent_chat_router
from app.routers.agent.bonus import router as agent_bonus_router
from app.routers.agent.cash_chat import router as agent_cash_chat_router
from app.routers.agent.credit_chat import router as agent_credit_chat_router
from app.routers.agent.kyc_chat import router as agent_kyc_chat_router
from app.routers.agent.transfer_support_chat import router as agent_transfer_support_chat_router
from app.routers.agent.wallet_chat import router as agent_wallet_chat_router
from app.routers.agent.wallet_support_chat import router as agent_wallet_support_chat_router
from app.routers.agent.agent_onboarding_chat import router as agent_onboarding_chat_router
from app.routers.agent.escrow_chat import router as agent_escrow_chat_router
from app.routers.agent.p2p_chat import router as agent_p2p_chat_router
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
from app.routers.wallet.payment_collections import router as wallet_payment_collections_router
from app.routers.wallet.payment_requests_v2 import router as wallet_payment_requests_v2_router
from app.routers.wallet.scheduled_transfers import router as wallet_scheduled_transfers_router
from app.routers.support import router as support_cases_router
from app.routers.savings import router as savings_router
from app.routers.financial_insights import router as financial_insights_router
from app.routers.referrals import router as referrals_router
from app.routers.business import router as business_router
from app.routers.merchant_api import router as merchant_api_router
from app.routers.pots import router as pots_router
from app.routers.virtual_cards import router as virtual_cards_router
from app.routers.trust import router as trust_router
from app.routers.fx import router as fx_router
from app.routers.wallet import transactions, wallet
from app.routers.wallet.crypto_wallet import router as crypto_wallet_router
from app.routers.telegram_external_transfer import router as telegram_external_transfer_router
from app.routers.wallet.usdc_wallet import router as usdc_wallet_router
from app.routers.wallet.transfer import router as transfer_router
from app.routers.ws import router as ws_router
from app.services.backoffice_risk import router as backoffice_risk_router
from app.services.idempotency_service import ensure_idempotency_schema
from app.services.ai_runtime_schema import ensure_ai_runtime_schema
from app.services.payments_runtime_schema import ensure_payments_runtime_schema
from app.services.payment_requests_runtime_schema import ensure_payment_requests_v2_schema
from app.services.support_cases_runtime_schema import ensure_support_cases_schema
from app.services.trust_runtime_schema import ensure_trust_schema
from app.services.fx_runtime_schema import ensure_fx_schema
from app.services.scheduled_transfers_runtime_schema import ensure_scheduled_transfers_schema
from app.services.savings_runtime_schema import ensure_savings_schema
from app.services.financial_insights_runtime_schema import ensure_financial_insights_schema
from app.services.referrals_runtime_schema import ensure_referrals_schema
from app.services.business_runtime_schema import ensure_business_schema
from app.services.merchant_api_runtime_schema import ensure_merchant_api_schema
from app.services.merchant_payments_runtime_schema import ensure_merchant_payments_schema
from app.services.agent_offline_runtime_schema import ensure_agent_offline_schema
from app.services.pots_runtime_schema import ensure_pots_schema
from app.services.virtual_cards_runtime_schema import ensure_virtual_cards_schema
from app.services.operator_workflow_runtime_schema import ensure_operator_workflow_schema
from app.services.product_automation_worker import run_product_automation_cycle
from app.services.request_metrics import build_request_metric_payload
from app.services.telegram_external_transfer_service import ensure_telegram_external_transfer_schema
from app.services.auth_sessions import ensure_auth_refresh_schema
from app.services.sandbox_transition_worker import run_sandbox_auto_transitions
from app.services.p2p_expiration_worker import run_p2p_expiration_worker
from app.services.tontine_rotation import process_tontine_rotations
from app.websocket_manager import admin_ws_join, admin_ws_leave
from app.workers.alerts_worker import deliver_alerts
from services.escrow_webhook_retry_worker import run_escrow_webhook_retry_worker
try:
    from app.services.slack_service import send_slack as send_slack_message
except Exception:
    send_slack_message = None
try:
    from app.services.telegram import send_message as send_telegram_message
except Exception:
    send_telegram_message = None

logging.getLogger("websockets.client").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)

logger = get_logger("PesaPaid")
app = FastAPI(title="PesaPaid API (Dev Mode)", version="0.1")
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


async def product_automation_worker():
    while True:
        try:
            async for db in get_db():
                try:
                    summary = await run_product_automation_cycle(
                        db,
                        batch_limit=settings.PRODUCT_AUTOMATION_BATCH_LIMIT,
                    )
                    if (
                        summary["payment_requests"]["processed"]
                        or summary["scheduled_transfers"]["processed"]
                        or summary["savings"]["processed"]
                    ):
                        logger.info("Product automation cycle processed: %s", summary)
                except Exception as exc:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    logger.error(f"Product automation worker error: {exc}")
                break
        except Exception as exc:
            logger.error(f"Product automation worker bootstrap error: {exc}")
        await asyncio.sleep(settings.PRODUCT_AUTOMATION_INTERVAL_SECONDS)


async def _count_unbalanced_journals(db) -> int:
    res = await db.execute(
        text(
            """
            SELECT COUNT(*)::int
            FROM (
              SELECT journal_id
              FROM paylink.ledger_entries
              GROUP BY journal_id
              HAVING
                SUM(CASE WHEN LOWER(direction::text)='debit' THEN amount ELSE 0 END)
                <>
                SUM(CASE WHEN LOWER(direction::text)='credit' THEN amount ELSE 0 END)
            ) t
            """
        )
    )
    return int(res.scalar_one() or 0)


def _parse_telegram_notify_chat_ids() -> list[int]:
    raw = str(getattr(settings, "TELEGRAM_NOTIFY_CHAT_IDS", "") or "").strip()
    if not raw:
        return []
    result: list[int] = []
    for item in raw.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            result.append(int(token))
        except Exception:
            continue
    return result


async def _send_ledger_alert(message: str) -> None:
    if settings.SLACK_WEBHOOK_URL and send_slack_message:
        try:
            maybe = send_slack_message(message)
            if inspect.isawaitable(maybe):
                await maybe
        except Exception as exc:
            logger.error("Ledger alert slack notification failed: %s", exc)

    chat_ids = _parse_telegram_notify_chat_ids()
    if chat_ids and send_telegram_message:
        for chat_id in chat_ids:
            try:
                await send_telegram_message(chat_id, message)
            except Exception as exc:
                logger.error(
                    "Ledger alert telegram notification failed chat_id=%s: %s",
                    chat_id,
                    exc,
                )


async def ledger_health_worker():
    last_count: int | None = None
    last_alert_at = 0.0
    interval_seconds = max(30, int(getattr(settings, "LEDGER_HEALTH_CHECK_INTERVAL_SECONDS", 120) or 120))
    alert_delta = max(1, int(getattr(settings, "LEDGER_HEALTH_ALERT_DELTA", 1) or 1))
    reminder_seconds = max(300, interval_seconds * 5)

    async for db in get_db():
        while True:
            try:
                count = await _count_unbalanced_journals(db)
                now = time.time()

                should_alert = False
                reason = "noop"
                if last_count is None:
                    should_alert = count > 0
                    reason = "startup_detected"
                elif count == 0 and last_count > 0:
                    should_alert = True
                    reason = "recovered"
                elif count > 0 and last_count == 0:
                    should_alert = True
                    reason = "new_issue"
                elif count > 0 and abs(count - last_count) >= alert_delta:
                    should_alert = True
                    reason = "count_changed"
                elif count > 0 and (now - last_alert_at) >= reminder_seconds:
                    should_alert = True
                    reason = "reminder"

                if should_alert:
                    status = "RECOVERED" if count == 0 else "UNBALANCED_JOURNALS"
                    message = (
                        f"[LEDGER][{status}] count={count} prev={last_count} "
                        f"reason={reason} env={settings.APP_ENV}"
                    )
                    logger.warning(message)
                    await _send_ledger_alert(message)
                    last_alert_at = now

                last_count = count
            except Exception as exc:
                logger.error("Ledger health worker error: %s", exc)
            await asyncio.sleep(interval_seconds)


async def ledger_daily_control_worker():
    configured_hour = int(getattr(settings, "LEDGER_DAILY_CHECK_UTC_HOUR", 7) or 7)
    hour_utc = max(0, min(23, configured_hour))
    alert_on_ok = bool(getattr(settings, "LEDGER_DAILY_ALERT_ON_OK", False))

    async for db in get_db():
        while True:
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            sleep_seconds = max(1, int((next_run - now).total_seconds()))
            await asyncio.sleep(sleep_seconds)

            try:
                count = await _count_unbalanced_journals(db)
                status = "UNBALANCED_JOURNALS" if count > 0 else "OK"
                message = (
                    f"[LEDGER][DAILY_CHECK][{status}] count={count} "
                    f"run_at={datetime.now(timezone.utc).isoformat()} env={settings.APP_ENV}"
                )
                if count > 0:
                    logger.warning(message)
                    await _send_ledger_alert(message)
                elif alert_on_ok:
                    logger.info(message)
                    await _send_ledger_alert(message)
                else:
                    logger.info(message)
            except Exception as exc:
                logger.error("Ledger daily control worker error: %s", exc)


async def idempotency_cleanup_worker():
    interval_seconds = max(
        60,
        int(getattr(settings, "IDEMPOTENCY_CLEANUP_INTERVAL_SECONDS", 1800) or 1800),
    )
    retention_hours = max(
        1,
        int(getattr(settings, "IDEMPOTENCY_RETENTION_HOURS", 72) or 72),
    )

    async for db in get_db():
        while True:
            try:
                res = await db.execute(
                    text(
                        """
                        WITH deleted AS (
                            DELETE FROM paylink.idempotency_keys
                            WHERE created_at < (NOW() - make_interval(hours => :retention_hours))
                            RETURNING 1
                        )
                        SELECT COUNT(*)::int FROM deleted
                        """
                    ),
                    {"retention_hours": retention_hours},
                )
                deleted_count = int(res.scalar_one() or 0)
                if deleted_count > 0:
                    logger.info(
                        "Idempotency cleanup removed %s key(s) older than %sh",
                        deleted_count,
                        retention_hours,
                    )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.error("Idempotency cleanup worker error: %s", exc)
            await asyncio.sleep(interval_seconds)


async def ensure_request_metrics_schema(db) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS paylink"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.request_metrics (
              id bigserial PRIMARY KEY,
              created_at timestamptz NOT NULL DEFAULT now(),
              method text NOT NULL,
              path text NOT NULL,
              status_code int NOT NULL,
              duration_ms numeric(12, 3) NOT NULL,
              request_id text NULL,
              error_type text NULL,
              is_error boolean NOT NULL DEFAULT false
            )
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE paylink.request_metrics
            ADD COLUMN IF NOT EXISTS error_type text NULL
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE paylink.request_metrics
            ADD COLUMN IF NOT EXISTS is_error boolean NOT NULL DEFAULT false
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_request_metrics_created_at
            ON paylink.request_metrics (created_at DESC)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_request_metrics_status
            ON paylink.request_metrics (status_code)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_request_metrics_path
            ON paylink.request_metrics (path)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_request_metrics_is_error
            ON paylink.request_metrics (is_error)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_request_metrics_error_type
            ON paylink.request_metrics (error_type)
            """
        )
    )


async def _persist_request_metric(payload: dict[str, object]) -> None:
    async for db in get_db():
        await db.execute(
            text(
                """
                INSERT INTO paylink.request_metrics
                (method, path, status_code, duration_ms, request_id, error_type, is_error)
                VALUES (:method, :path, :status_code, :duration_ms, :request_id, :error_type, :is_error)
                """
            ),
            payload,
        )
        await db.commit()
        break


async def ensure_core_schemas(db) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS paylink"))
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS escrow"))
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS p2p"))


default_origins = {
    "https://pesapaid.com",
    "https://app.pesapaid.com",
    "https://api.pesapaid.com",
    "https://www.pesapaid.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://paylink-frontend-production.up.railway.app",
    "https://web-production-448ce.up.railway.app"
  
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
    allow_origin_regex=r"(https://.*\.up\.railway\.app|https://([a-z0-9-]+\.)?pesapaid\.com|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(change_password_router)
app.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
app.include_router(wallet_payment_collections_router)
app.include_router(wallet_payment_requests_v2_router)
app.include_router(wallet_scheduled_transfers_router)
app.include_router(support_cases_router)
app.include_router(savings_router)
app.include_router(financial_insights_router)
app.include_router(referrals_router)
app.include_router(business_router)
app.include_router(merchant_api_router)
app.include_router(pots_router)
app.include_router(virtual_cards_router)
app.include_router(trust_router)
app.include_router(fx_router)
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
app.include_router(admin_product_automation_router.router)
app.include_router(admin_support_cases_router.router)
app.include_router(admin_virtual_cards_router.router)
app.include_router(admin_agent_offline_router.router)
app.include_router(invoices_router)
app.include_router(merchant_router)
app.include_router(loans_router)
app.include_router(transactions.router)
app.include_router(transfer_router)
app.include_router(tontine_router, prefix="/tontines", tags=["Tontines"])
app.include_router(ws_router)
app.include_router(risk_admin_router.router)
app.include_router(ws_security_router)
app.include_router(ws_tracking_router)
app.include_router(ops_payout_router)
app.include_router(ops_liquidity_router)
app.include_router(agent_ops_router)
app.include_router(admin_users_router)
app.include_router(admin_users_limits_router.router)
app.include_router(admin_wallets_router)
app.include_router(admin_transfers_router.router)
app.include_router(admin_settings_router.router)
app.include_router(admin_kyc_router.router)
app.include_router(admin_analytics_router.router)
app.include_router(admin_agents_router.router)
app.include_router(admin_ai_feedback_router.router)
app.include_router(admin_audit_search_router.router)
app.include_router(admin_ops_workflow_router.router)
app.include_router(admin_payments_router.router)
app.include_router(admin_mobilemoney_router.router)
app.include_router(admin_tontine_arrears_router.router)
app.include_router(admin_credit_lines_router.router)
app.include_router(admin_notifications_router.router)
app.include_router(admin_loan_stats_router.router)
app.include_router(admin_aml_router.router)
app.include_router(admin_credit_history_router.router)
app.include_router(admin_cash_requests_router.router)
app.include_router(admin_transactions_audit_router.router)
app.include_router(admin_error_logs_router.router)
app.include_router(admin_wallet_analysis_router.router)
app.include_router(agent_router, prefix="/agent", tags=["Agent Operations"])
app.include_router(agent_bonus_router)
app.include_router(agent_offline_router)
app.include_router(agent_chat_router)
app.include_router(agent_cash_chat_router)
app.include_router(agent_credit_chat_router)
app.include_router(agent_kyc_chat_router)
app.include_router(agent_transfer_support_chat_router)
app.include_router(agent_wallet_chat_router)
app.include_router(agent_wallet_support_chat_router)
app.include_router(agent_onboarding_chat_router)
app.include_router(agent_escrow_chat_router)
app.include_router(agent_p2p_chat_router)
app.include_router(agent_router_extern)
app.include_router(telegram_external_transfer_router)
app.include_router(debug.router)
app.include_router(ai_router)
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


def _get_request_id(request: Request) -> str | None:
    return (
        getattr(request.state, "request_id", None)
        or request.headers.get("x-request-id")
        or request.headers.get("X-Request-Id")
    )


SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-access-token",
    "x-csrf-token",
    "password",
    "token",
    "secret",
    "otp",
    "pin",
}


def _truncate(value: str | None, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    if len(text_value) <= limit:
        return text_value
    return f"{text_value[:limit]}...[truncated]"


def _redact_value(key: str, value):
    if key.lower() in SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    if isinstance(value, str):
        return _truncate(value, 2000)
    return value


def _sanitize_headers(request: Request) -> dict[str, object]:
    return {key: _redact_value(key, value) for key, value in request.headers.items()}


def _sanitize_query_params(request: Request) -> dict[str, object]:
    return {
        key: _redact_value(key, value)
        for key, value in request.query_params.items()
    }


async def _sanitize_request_body(request: Request) -> str | None:
    try:
        body = await request.body()
    except Exception:
        return None

    if not body:
        return None

    raw_text = body.decode("utf-8", errors="replace")
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            payload = json.loads(raw_text)
            if isinstance(payload, dict):
                return _truncate(json.dumps(_redact_value("body", payload), ensure_ascii=False), 4000)
            if isinstance(payload, list):
                return _truncate(json.dumps(_redact_value("body", payload), ensure_ascii=False), 4000)
        except Exception:
            pass
    return _truncate(raw_text, 4000)


def _extract_user_id_from_request(request: Request | WebSocket) -> str | None:
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        return str(user_id) if user_id else None
    except JWTError:
        return None


async def persist_app_error(
    request: Request | WebSocket,
    exc: Exception,
    *,
    status_code: int,
    handled: bool,
    error_type: str | None = None,
    stack_trace: str | None = None,
) -> None:
    request_id = _get_request_id(request)
    user_id = _extract_user_id_from_request(request)
    is_websocket = isinstance(request, WebSocket)
    request_method = "WEBSOCKET" if is_websocket else _truncate(getattr(request, "method", None), 16) or "GET"
    request_body = None if is_websocket else await _sanitize_request_body(request)
    payload = {
        "error_id": str(uuid.uuid4()),
        "request_id": request_id,
        "status_code": int(status_code or 500),
        "error_type": _truncate(error_type or exc.__class__.__name__, 255) or "Exception",
        "message": _truncate(str(exc), 4000) or "Internal Server Error",
        "request_path": _truncate(request.url.path, 500) or "",
        "request_method": request_method,
        "user_id": user_id,
        "client_ip": _truncate(request.client.host if request.client else None, 128),
        "handled": handled,
        "stack_trace": _truncate(stack_trace, 12000),
        "headers": json.dumps(_sanitize_headers(request), ensure_ascii=False),
        "query_params": json.dumps(_sanitize_query_params(request), ensure_ascii=False),
        "request_body": request_body,
    }

    try:
        async for db in get_db():
            await db.execute(
                text(
                    """
                    INSERT INTO paylink.app_errors (
                      error_id,
                      request_id,
                      status_code,
                      error_type,
                      message,
                      request_path,
                      request_method,
                      user_id,
                      client_ip,
                      handled,
                      stack_trace,
                      headers,
                      query_params,
                      request_body
                    )
                    VALUES (
                      CAST(:error_id AS uuid),
                      :request_id,
                      :status_code,
                      :error_type,
                      :message,
                      :request_path,
                      :request_method,
                      CAST(:user_id AS uuid),
                      :client_ip,
                      :handled,
                      :stack_trace,
                      CAST(:headers AS jsonb),
                      CAST(:query_params AS jsonb),
                      :request_body
                    )
                    """
                ),
                payload,
            )
            await db.commit()
            break
    except Exception as persist_exc:
        logger.warning(
            "App error persistence failed path=%s request_id=%s err=%s",
            request.url.path,
            request_id,
            persist_exc,
        )


@app.middleware("http")
async def request_metrics_middleware(request: Request, call_next):
    if not getattr(settings, "REQUEST_METRICS_ENABLED", True):
        return await call_next(request)

    # Skip noisy health/metrics routes to keep business signal clean.
    skip_prefixes = ("/health", "/metrics", "/api/metrics", "/ws", "/auth/login")
    if request.url.path.startswith(skip_prefixes):
        return await call_next(request)

    started = time.perf_counter()
    request_id = _get_request_id(request)
    response = None

    try:
        response = await call_next(request)
        payload = build_request_metric_payload(
            method=request.method,
            path=request.url.path,
            status_code=int(response.status_code or 0),
            duration_ms=(time.perf_counter() - started) * 1000,
            request_id=request_id,
        )
        try:
            await _persist_request_metric(payload)
        except Exception as persist_exc:
            logger.warning("Request metrics insert failed path=%s err=%s", request.url.path, persist_exc)
    except Exception as exc:
        payload = build_request_metric_payload(
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=(time.perf_counter() - started) * 1000,
            request_id=request_id,
            error_type=exc.__class__.__name__,
        )
        try:
            await _persist_request_metric(payload)
        except Exception as persist_exc:
            logger.warning("Request metrics insert failed path=%s err=%s", request.url.path, persist_exc)
        raise

    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = _get_request_id(request)
    await persist_app_error(
        request,
        exc,
        status_code=exc.status_code,
        handled=True,
        error_type="HTTPException",
    )
    logger.warning(
        "HTTP exception path=%s method=%s status=%s request_id=%s detail=%s",
        request.url.path,
        request.method,
        exc.status_code,
        request_id,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "path": request.url.path,
            "method": request.method,
            "request_id": request_id,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = _get_request_id(request)
    validation_errors = jsonable_encoder(exc.errors())
    await persist_app_error(
        request,
        exc,
        status_code=422,
        handled=True,
        error_type="RequestValidationError",
        stack_trace=_truncate(json.dumps(validation_errors, ensure_ascii=False), 12000),
    )
    logger.warning(
        "Validation exception path=%s method=%s request_id=%s errors=%s",
        request.url.path,
        request.method,
        request_id,
        validation_errors,
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": validation_errors,
            "path": request.url.path,
            "method": request.method,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = _get_request_id(request)
    await persist_app_error(
        request,
        exc,
        status_code=500,
        handled=False,
        error_type=exc.__class__.__name__,
        stack_trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    logger.exception(
        "Unhandled exception path=%s method=%s request_id=%s error=%s",
        request.url.path,
        request.method,
        request_id,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "error": str(exc),
            "path": request.url.path,
            "request_id": request_id,
        },
    )


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
    async for db in get_db():
        await ensure_core_schemas(db)
        await ensure_auth_refresh_schema(db)
        await ensure_idempotency_schema(db)
        await ensure_request_metrics_schema(db)
        await ensure_telegram_external_transfer_schema(db)
        await ensure_ai_runtime_schema(db)
        await ensure_payments_runtime_schema(db)
        await ensure_payment_requests_v2_schema(db)
        await ensure_support_cases_schema(db)
        await ensure_trust_schema(db)
        await ensure_fx_schema(db)
        await ensure_scheduled_transfers_schema(db)
        await ensure_savings_schema(db)
        await ensure_financial_insights_schema(db)
        await ensure_referrals_schema(db)
        await ensure_business_schema(db)
        await ensure_merchant_api_schema(db)
        await ensure_merchant_payments_schema(db)
        await ensure_agent_offline_schema(db)
        await ensure_pots_schema(db)
        await ensure_virtual_cards_schema(db)
        await ensure_operator_workflow_schema(db)
        await db.commit()
        break

    app.state.started_at_ts = time.time()
    background_tasks.append(asyncio.create_task(webhook_retry_worker()))
    background_tasks.append(asyncio.create_task(alerts_worker()))
    background_tasks.append(asyncio.create_task(p2p_expiration_worker()))
    if settings.PRODUCT_AUTOMATION_ENABLED:
        background_tasks.append(asyncio.create_task(product_automation_worker()))
    if settings.LEDGER_HEALTH_CHECK_ENABLED:
        background_tasks.append(asyncio.create_task(ledger_health_worker()))
    if settings.LEDGER_DAILY_CHECK_ENABLED:
        background_tasks.append(asyncio.create_task(ledger_daily_control_worker()))
    if settings.IDEMPOTENCY_CLEANUP_ENABLED:
        background_tasks.append(asyncio.create_task(idempotency_cleanup_worker()))
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
    return {"message": "PesaPaid backend en mode developpement"}


logger.info("Demarrage du backend paylink...")
