import hashlib
import hmac
import base64
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.security.rate_limit import rate_limit
from app.models.external_transfers import ExternalTransfers
from app.models.users import Users
from app.services.external_transfer_provider_workflow import (
    apply_provider_status_update,
    reconcile_external_transfer_providers,
)

router = APIRouter(prefix="/providers/ihela", tags=["Providers - iHela"])


def _require_admin_or_agent(current_user: Users) -> None:
    if str(getattr(current_user, "role", "") or "").lower() not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Acces refuse")


def _join_url(base_url: str, path: str) -> str:
    base = str(base_url or "").rstrip("/")
    p = str(path or "").strip()
    if not p:
        return base
    return f"{base}{p if p.startswith('/') else f'/{p}'}"


def _ihela_base_url() -> str:
    base_url = str(getattr(settings, "IHELA_API_BASE_URL", "") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="IHELA_API_BASE_URL manquant")
    return base_url


def _bridge_base_url() -> str:
    return str(getattr(settings, "IHELA_BRIDGE_BASE_URL", "") or "").strip()


def _bridge_api_key() -> str:
    return str(getattr(settings, "IHELA_BRIDGE_API_KEY", "") or "").strip()


def _bridge_configured() -> bool:
    return bool(_bridge_base_url() and _bridge_api_key())


def _ihela_oauth_credentials() -> tuple[str, str]:
    client_id = str(getattr(settings, "IHELA_OAUTH_CLIENT_ID", "") or "").strip()
    client_secret = str(getattr(settings, "IHELA_OAUTH_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="IHELA_OAUTH_CLIENT_ID / IHELA_OAUTH_CLIENT_SECRET manquants")
    return client_id, client_secret


async def _ihela_fetch_oauth_token() -> dict[str, Any]:
    base_url = _ihela_base_url()
    client_id, client_secret = _ihela_oauth_credentials()
    token_path = str(getattr(settings, "IHELA_OAUTH_TOKEN_PATH", "/oAuth2/token/") or "/oAuth2/token/")
    token_url = _join_url(base_url, token_path)
    pair = f"{client_id}:{client_secret}".encode("ascii")
    basic = base64.b64encode(pair).decode("ascii")
    timeout = float(getattr(settings, "IHELA_TIMEOUT_SECONDS", 12.0) or 12.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                token_url,
                headers={"Authorization": f"Basic {basic}"},
                data={"grant_type": "client_credentials"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Timeout iHela sur OAuth2 token") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur reseau iHela OAuth2: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:500] if response.text else f"HTTP {response.status_code}"
        raise HTTPException(status_code=502, detail=f"Echec OAuth2 iHela: {detail}")

    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Reponse OAuth2 iHela non-JSON") from exc
    if not isinstance(body, dict) or not str(body.get("access_token") or "").strip():
        raise HTTPException(status_code=502, detail="access_token manquant dans la reponse OAuth2 iHela")
    return body


async def _bridge_post(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    base_url = _bridge_base_url()
    if not base_url:
        raise HTTPException(status_code=400, detail="IHELA_BRIDGE_BASE_URL manquant")
    api_key = _bridge_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="IHELA_BRIDGE_API_KEY manquant")
    timeout = float(getattr(settings, "IHELA_TIMEOUT_SECONDS", 12.0) or 12.0)
    url = _join_url(base_url, path)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Timeout bridge iHela sur {path}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur reseau bridge iHela sur {path}: {exc}") from exc

    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {"raw_text": response.text[:1000]}
    return response.status_code, body


def _extract_webhook_fields(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    provider_ref = str(
        payload.get("provider_ref")
        or payload.get("provider_reference")
        or payload.get("transaction_id")
        or payload.get("id")
        or ""
    ).strip() or None
    provider_status = str(
        payload.get("status")
        or payload.get("state")
        or payload.get("payment_status")
        or ""
    ).strip() or None
    transfer_ref = str(
        payload.get("reference")
        or payload.get("client_reference")
        or payload.get("transfer_reference")
        or ""
    ).strip() or None
    return provider_ref, provider_status, transfer_ref


@router.post("/webhook")
async def ihela_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    await rate_limit(request, key=f"ip:{ip}:ihela_webhook", limit=120, window_seconds=60)

    raw_body = await request.body()
    signature_header = str(getattr(settings, "IHELA_WEBHOOK_SIGNATURE_HEADER", "X-IHela-Signature") or "X-IHela-Signature")
    signature = request.headers.get(signature_header)
    secret = str(getattr(settings, "IHELA_WEBHOOK_SECRET", "") or "").strip() or str(getattr(settings, "HMAC_SECRET", "") or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="IHELA_WEBHOOK_SECRET manquant")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload iHela invalide")

    provider_ref, provider_status, transfer_ref = _extract_webhook_fields(payload)
    if not provider_status:
        raise HTTPException(status_code=400, detail="provider_status manquant dans le webhook iHela")

    transfer = None
    if provider_ref:
        transfer = await db.scalar(
            select(ExternalTransfers).where(
                ExternalTransfers.provider == "ihela",
                ExternalTransfers.provider_ref == provider_ref,
            )
        )
    if not transfer and transfer_ref:
        transfer = await db.scalar(
            select(ExternalTransfers).where(
                ExternalTransfers.reference_code == transfer_ref,
            )
        )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfert iHela introuvable")

    update = await apply_provider_status_update(
        db,
        transfer=transfer,
        provider_status=provider_status,
        provider_ref=provider_ref,
        last_error=str(payload.get("error") or payload.get("message") or "").strip() or None,
        provider_payload=payload,
    )
    await db.commit()
    return {
        "status": "ok",
        "transfer_id": str(transfer.transfer_id),
        "provider_status": update.get("provider_status"),
        "transfer_status": update.get("transfer_status"),
    }


@router.post("/reconcile")
async def ihela_reconcile_now(
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    _require_admin_or_agent(current_user)

    summary = await reconcile_external_transfer_providers()
    return {"status": "ok", "summary": summary}


@router.post("/test/withdrawal")
async def ihela_test_withdrawal(
    payload: dict[str, Any] = Body(...),
    current_user: Users = Depends(get_current_user),
):
    _require_admin_or_agent(current_user)
    if _bridge_configured():
        path = str(getattr(settings, "IHELA_BRIDGE_WITHDRAWAL_PATH", "/ihela/transfer") or "/ihela/transfer")
        status_code, body = await _bridge_post(path, payload)
        return {
            "ok": status_code < 400,
            "http_status": status_code,
            "transport": "bridge",
            "bridge_url": _join_url(_bridge_base_url(), path),
            "response": body,
        }

    oauth = await _ihela_fetch_oauth_token()
    access_token = str(oauth.get("access_token") or "").strip()
    timeout = float(getattr(settings, "IHELA_TIMEOUT_SECONDS", 12.0) or 12.0)
    base_url = _ihela_base_url()
    api_prefix = str(getattr(settings, "IHELA_BANKING_API_PREFIX", "/ihela/api/v1") or "/ihela/api/v1")
    url = _join_url(base_url, f"{api_prefix.rstrip('/')}/make-withdrawal/")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Timeout iHela sur make-withdrawal") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur reseau iHela make-withdrawal: {exc}") from exc

    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {"raw_text": response.text[:1000]}

    return {
        "ok": response.status_code < 400,
        "http_status": response.status_code,
        "transport": "direct",
        "oauth": {
            "token_type": oauth.get("token_type"),
            "expires_in": oauth.get("expires_in"),
            "scope": oauth.get("scope"),
        },
        "response": body,
    }


@router.post("/test/transaction-status")
async def ihela_test_transaction_status(
    payload: dict[str, Any] = Body(...),
    current_user: Users = Depends(get_current_user),
):
    _require_admin_or_agent(current_user)
    if _bridge_configured():
        path = str(
            getattr(settings, "IHELA_BRIDGE_STATUS_PATH", "/ihela/transaction-status")
            or "/ihela/transaction-status"
        )
        status_code, body = await _bridge_post(path, payload)
        return {
            "ok": status_code < 400,
            "http_status": status_code,
            "transport": "bridge",
            "bridge_url": _join_url(_bridge_base_url(), path),
            "response": body,
        }

    oauth = await _ihela_fetch_oauth_token()
    access_token = str(oauth.get("access_token") or "").strip()
    timeout = float(getattr(settings, "IHELA_TIMEOUT_SECONDS", 12.0) or 12.0)
    base_url = _ihela_base_url()
    api_prefix = str(getattr(settings, "IHELA_BANKING_API_PREFIX", "/ihela/api/v1") or "/ihela/api/v1")
    url = _join_url(base_url, f"{api_prefix.rstrip('/')}/transaction-status/")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Timeout iHela sur transaction-status") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur reseau iHela transaction-status: {exc}") from exc

    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {"raw_text": response.text[:1000]}

    return {
        "ok": response.status_code < 400,
        "http_status": response.status_code,
        "transport": "direct",
        "response": body,
    }
