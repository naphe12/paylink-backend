from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings

PROVIDER_STATUS_CREATED = "created"
PROVIDER_STATUS_PROCESSING = "processing"
PROVIDER_STATUS_SENT = "sent"
PROVIDER_STATUS_SUCCESS = "success"
PROVIDER_STATUS_FAILED = "failed"
PROVIDER_STATUS_RETRY = "retry"
PROVIDER_STATUS_MANUAL_REVIEW = "manual_review"


class ExternalTransferProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ExternalTransferProviderTimeout(ExternalTransferProviderError):
    def __init__(self, message: str = "Provider timeout") -> None:
        super().__init__(message, retryable=True)


@dataclass
class ProviderSendResult:
    provider_status: str
    provider_ref: str | None = None
    terminal: bool = False
    raw_response: dict[str, Any] | None = None
    message: str | None = None


@dataclass
class ProviderStatusResult:
    provider_status: str
    terminal: bool
    raw_response: dict[str, Any] | None = None
    message: str | None = None


class ExternalTransferProvider:
    async def send(
        self,
        *,
        transfer_id: UUID,
        amount: str,
        currency: str,
        recipient_phone: str,
        recipient_name: str | None,
        reference: str,
        idempotency_key: str | None,
    ) -> ProviderSendResult:
        raise NotImplementedError

    async def get_status(self, *, provider_ref: str) -> ProviderStatusResult:
        raise NotImplementedError


def normalize_provider_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"ok", "success", "successful", "done", "completed", "paid"}:
        return PROVIDER_STATUS_SUCCESS
    if normalized in {"pending", "processing", "queued", "in_progress"}:
        return PROVIDER_STATUS_PROCESSING
    if normalized in {"sent", "submitted", "accepted"}:
        return PROVIDER_STATUS_SENT
    if normalized in {"retry", "retrying"}:
        return PROVIDER_STATUS_RETRY
    if normalized in {"manual_review", "manual"}:
        return PROVIDER_STATUS_MANUAL_REVIEW
    if normalized in {"failed", "error", "rejected", "cancelled", "canceled", "timeout"}:
        return PROVIDER_STATUS_FAILED
    return PROVIDER_STATUS_PROCESSING


class MockExternalTransferProvider(ExternalTransferProvider):
    async def send(
        self,
        *,
        transfer_id: UUID,
        amount: str,
        currency: str,
        recipient_phone: str,
        recipient_name: str | None,
        reference: str,
        idempotency_key: str | None,
    ) -> ProviderSendResult:
        return ProviderSendResult(
            provider_status=PROVIDER_STATUS_SUCCESS,
            provider_ref=f"mock-{transfer_id}",
            terminal=True,
            raw_response={"status": "SUCCESS", "reference": reference},
            message="Sandbox mock success",
        )

    async def get_status(self, *, provider_ref: str) -> ProviderStatusResult:
        return ProviderStatusResult(
            provider_status=PROVIDER_STATUS_SUCCESS,
            terminal=True,
            raw_response={"status": "SUCCESS", "provider_ref": provider_ref},
            message="Sandbox mock status success",
        )


class IHelaProvider(ExternalTransferProvider):
    def __init__(self) -> None:
        self.base_url = str(getattr(settings, "IHELA_API_BASE_URL", "") or "").rstrip("/")
        self.api_key = str(getattr(settings, "IHELA_API_KEY", "") or "").strip()
        self.timeout = float(getattr(settings, "IHELA_TIMEOUT_SECONDS", 12.0) or 12.0)
        self.send_path = str(getattr(settings, "IHELA_SEND_PATH", "/transfers") or "/transfers")
        self.status_path = str(
            getattr(settings, "IHELA_STATUS_PATH", "/transfers/{provider_ref}") or "/transfers/{provider_ref}"
        )
        self.auth_scheme = str(getattr(settings, "IHELA_AUTH_SCHEME", "Bearer") or "Bearer")

        if not self.base_url:
            raise ExternalTransferProviderError("IHELA_API_BASE_URL manquant", retryable=False)
        if not self.api_key:
            raise ExternalTransferProviderError("IHELA_API_KEY manquant", retryable=False)

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"{self.auth_scheme} {self.api_key}",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _send_url(self) -> str:
        return f"{self.base_url}{self.send_path if self.send_path.startswith('/') else f'/{self.send_path}'}"

    def _status_url(self, provider_ref: str) -> str:
        path = self.status_path.format(provider_ref=provider_ref)
        return f"{self.base_url}{path if path.startswith('/') else f'/{path}'}"

    async def send(
        self,
        *,
        transfer_id: UUID,
        amount: str,
        currency: str,
        recipient_phone: str,
        recipient_name: str | None,
        reference: str,
        idempotency_key: str | None,
    ) -> ProviderSendResult:
        payload = {
            "amount": amount,
            "currency": currency,
            "phone": recipient_phone,
            "recipient_name": recipient_name,
            "reference": reference,
            "client_transfer_id": str(transfer_id),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self._send_url(),
                    json=payload,
                    headers=self._headers(idempotency_key=idempotency_key),
                )
        except httpx.TimeoutException as exc:
            raise ExternalTransferProviderTimeout("iHela timeout sur send") from exc
        except httpx.HTTPError as exc:
            raise ExternalTransferProviderError(f"iHela erreur reseau send: {exc}", retryable=True) from exc

        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        if response.status_code >= 500:
            raise ExternalTransferProviderError(
                f"iHela erreur serveur ({response.status_code})",
                retryable=True,
            )
        if response.status_code >= 400:
            detail = body.get("message") or body.get("detail") or f"HTTP {response.status_code}"
            raise ExternalTransferProviderError(f"iHela rejet send: {detail}", retryable=False)

        raw_status = body.get("status") or body.get("state") or body.get("payment_status")
        provider_status = normalize_provider_status(raw_status)
        provider_ref = str(
            body.get("provider_ref")
            or body.get("transaction_id")
            or body.get("id")
            or ""
        ).strip() or None
        terminal = provider_status in {PROVIDER_STATUS_SUCCESS, PROVIDER_STATUS_FAILED}
        return ProviderSendResult(
            provider_status=provider_status,
            provider_ref=provider_ref,
            terminal=terminal,
            raw_response=body if isinstance(body, dict) else {"raw": str(body)},
            message=str(body.get("message") or "") if isinstance(body, dict) else None,
        )

    async def get_status(self, *, provider_ref: str) -> ProviderStatusResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self._status_url(provider_ref),
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise ExternalTransferProviderTimeout("iHela timeout sur get_status") from exc
        except httpx.HTTPError as exc:
            raise ExternalTransferProviderError(f"iHela erreur reseau get_status: {exc}", retryable=True) from exc

        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        if response.status_code >= 500:
            raise ExternalTransferProviderError(
                f"iHela erreur serveur status ({response.status_code})",
                retryable=True,
            )
        if response.status_code >= 400:
            detail = body.get("message") or body.get("detail") or f"HTTP {response.status_code}"
            raise ExternalTransferProviderError(f"iHela rejet status: {detail}", retryable=False)

        raw_status = body.get("status") or body.get("state") or body.get("payment_status")
        provider_status = normalize_provider_status(raw_status)
        terminal = provider_status in {PROVIDER_STATUS_SUCCESS, PROVIDER_STATUS_FAILED}
        return ProviderStatusResult(
            provider_status=provider_status,
            terminal=terminal,
            raw_response=body if isinstance(body, dict) else {"raw": str(body)},
            message=str(body.get("message") or "") if isinstance(body, dict) else None,
        )


def get_external_transfer_provider(provider_name: str) -> ExternalTransferProvider:
    normalized = str(provider_name or "").strip().lower()
    if normalized == "mock":
        return MockExternalTransferProvider()
    if normalized == "ihela":
        return IHelaProvider()
    raise ExternalTransferProviderError(f"Provider externe non supporte: {provider_name}", retryable=False)

