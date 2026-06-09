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


def _ihela_token_paths_for_mode(token_mode: str) -> list[str]:
    configured_path = str(getattr(settings, "IHELA_OAUTH_TOKEN_PATH", "") or "").strip()
    if configured_path:
        return [configured_path]
    if token_mode == "password":
        return ["/ihela/api/v1/auth-token/", "/api/v1/auth-token/"]
    return ["/oAuth2/token/"]


def _ihela_password_credentials_available() -> bool:
    username = str(getattr(settings, "IHELA_AUTH_USERNAME", "") or "").strip()
    password = str(getattr(settings, "IHELA_AUTH_PASSWORD", "") or "").strip()
    return bool(username and password)


async def _ihela_post_token_request(client: httpx.AsyncClient, token_mode: str, token_url: str) -> httpx.Response:
    if token_mode == "password":
        username = str(getattr(settings, "IHELA_AUTH_USERNAME", "") or "").strip()
        password = str(getattr(settings, "IHELA_AUTH_PASSWORD", "") or "").strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="IHELA_AUTH_USERNAME / IHELA_AUTH_PASSWORD manquants")
        return await client.post(
            token_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"username": username, "password": password},
        )

    client_id, client_secret = _ihela_oauth_credentials()
    pair = f"{client_id}:{client_secret}".encode("ascii")
    basic = base64.b64encode(pair).decode("ascii")
    return await client.post(
        token_url,
        headers={"Authorization": f"Basic {basic}"},
        files={"grant_type": (None, "client_credentials")},
    )


def _ihela_token_error_text(response: httpx.Response) -> str:
    return response.text[:500] if response.text else f"HTTP {response.status_code}"


def _ihela_banking_api_prefixes() -> list[str]:
    configured_prefix = str(getattr(settings, "IHELA_BANKING_API_PREFIX", "/ihela/api/v1") or "/ihela/api/v1").strip()
    prefixes = [configured_prefix]
    token_paths = _ihela_token_paths_for_mode(
        str(getattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials") or "client_credentials").strip().lower()
    )
    uses_testenv = any(str(path).strip().startswith("/testenv/") for path in token_paths)
    if uses_testenv and not configured_prefix.startswith("/testenv/"):
        prefixes.append(f"/testenv/{configured_prefix.lstrip('/')}")
    return list(dict.fromkeys(prefixes))


async def _ihela_direct_post(
    endpoint: str,
    payload: dict[str, Any],
    access_token: str,
    timeout: float,
) -> tuple[httpx.Response, list[str]]:
    base_url = _ihela_base_url()
    attempted_urls: list[str] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = None
        for api_prefix in _ihela_banking_api_prefixes():
            url = _join_url(base_url, f"{api_prefix.rstrip('/')}/{endpoint.strip('/')}/")
            attempted_urls.append(url)
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
            if response.status_code != 404:
                return response, attempted_urls
        if response is None:
            raise HTTPException(status_code=502, detail=f"Aucune requete iHela envoyee sur {endpoint}")
        return response, attempted_urls


async def _ihela_fetch_oauth_token() -> dict[str, Any]:
    base_url = _ihela_base_url()
    token_mode = str(getattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials") or "client_credentials").strip().lower()
    timeout = float(getattr(settings, "IHELA_TIMEOUT_SECONDS", 12.0) or 12.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = None
            for token_path in _ihela_token_paths_for_mode(token_mode):
                token_url = _join_url(base_url, token_path)
                response = await _ihela_post_token_request(client, token_mode, token_url)
                if response.status_code < 400:
                    break
                if token_mode != "password" or response.status_code != 404:
                    break
            if response is None:
                raise HTTPException(status_code=502, detail="Aucune requete token iHela envoyee")
            if (
                response.status_code >= 400
                and token_mode != "password"
                and "unsupported_grant_type" in response.text
                and _ihela_password_credentials_available()
            ):
                token_mode = "password"
                for token_path in _ihela_token_paths_for_mode(token_mode):
                    token_url = _join_url(base_url, token_path)
                    response = await _ihela_post_token_request(client, token_mode, token_url)
                    if response.status_code < 400:
                        break
                    if response.status_code != 404:
                        break
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Timeout iHela sur OAuth2 token") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur reseau iHela OAuth2: {exc}") from exc

    if response.status_code >= 400:
        detail = _ihela_token_error_text(response)
        if "unsupported_grant_type" in detail and token_mode != "password":
            detail = f"{detail} - Configure IHELA_AUTH_TOKEN_MODE=password avec IHELA_AUTH_USERNAME / IHELA_AUTH_PASSWORD"
        raise HTTPException(status_code=502, detail=f"Echec OAuth2 iHela: {detail}")

    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Reponse OAuth2 iHela non-JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="Reponse token iHela invalide")
    access_token = str(body.get("access_token") or body.get("access") or "").strip()
    if not access_token:
        raise HTTPException(status_code=502, detail="access_token manquant dans la reponse token iHela")
    body["access_token"] = access_token
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


@router.get("/test/oauth-debug")
async def ihela_test_oauth_debug(
    current_user: Users = Depends(get_current_user),
):
    _require_admin_or_agent(current_user)
    base_url = _ihela_base_url()
    token_mode = str(getattr(settings, "IHELA_AUTH_TOKEN_MODE", "client_credentials") or "client_credentials").strip().lower()
    token_paths = _ihela_token_paths_for_mode(token_mode)
    api_prefix = str(getattr(settings, "IHELA_BANKING_API_PREFIX", "/ihela/api/v1") or "/ihela/api/v1")
    return {
        "transport": "bridge" if _bridge_configured() else "direct",
        "ihela_api_base_url": base_url,
        "auth_token_mode": token_mode,
        "oauth_token_path_configured": str(getattr(settings, "IHELA_OAUTH_TOKEN_PATH", "") or "").strip(),
        "token_urls": [_join_url(base_url, token_path) for token_path in token_paths],
        "banking_api_prefix": api_prefix,
        "withdrawal_url": _join_url(base_url, f"{api_prefix.rstrip('/')}/make-withdrawal/"),
        "status_url": _join_url(base_url, f"{api_prefix.rstrip('/')}/transaction-status/"),
        "has_oauth_client_id": bool(str(getattr(settings, "IHELA_OAUTH_CLIENT_ID", "") or "").strip()),
        "has_oauth_client_secret": bool(str(getattr(settings, "IHELA_OAUTH_CLIENT_SECRET", "") or "").strip()),
        "has_auth_username": bool(str(getattr(settings, "IHELA_AUTH_USERNAME", "") or "").strip()),
        "has_auth_password": bool(str(getattr(settings, "IHELA_AUTH_PASSWORD", "") or "").strip()),
    }


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

    try:
        response, attempted_urls = await _ihela_direct_post("make-withdrawal", payload, access_token, timeout)
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
        "attempted_urls": attempted_urls,
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

    try:
        response, attempted_urls = await _ihela_direct_post("transaction-status", payload, access_token, timeout)
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
        "attempted_urls": attempted_urls,
        "response": body,
    }
