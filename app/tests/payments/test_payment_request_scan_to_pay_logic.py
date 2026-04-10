from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.models.payment_requests import PaymentRequests
from app.services import payment_request_service as service


def test_build_scan_to_pay_payload_contains_share_link(monkeypatch):
    monkeypatch.setattr(service.settings, "FRONTEND_URL", "https://app.pesapaid.com")
    request_obj = PaymentRequests(
        request_id=uuid4(),
        requester_user_id=uuid4(),
        requester_wallet_id=uuid4(),
        amount=Decimal("45.00"),
        currency_code="USD",
        status="pending",
        channel="static_qr",
        share_token="PR-BIZ1",
        created_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
    )

    payload = service._build_scan_to_pay_payload(request_obj)
    assert payload["mode"] == "static"
    assert payload["share_token"] == "PR-BIZ1"
    assert payload["pay_url"] == "https://app.pesapaid.com/pay/request/PR-BIZ1"


def test_business_channel_aliases_cover_scan_to_pay_modes():
    assert service.BUSINESS_PAYMENT_CHANNEL_ALIASES["business_link"] == "business_link"
    assert service.BUSINESS_PAYMENT_CHANNEL_ALIASES["link"] == "business_link"
    assert service.BUSINESS_PAYMENT_CHANNEL_ALIASES["static_qr"] == "static_qr"
    assert service.BUSINESS_PAYMENT_CHANNEL_ALIASES["qr_static"] == "static_qr"
    assert service.BUSINESS_PAYMENT_CHANNEL_ALIASES["dynamic_qr"] == "dynamic_qr"
    assert service.BUSINESS_PAYMENT_CHANNEL_ALIASES["qr_dynamic"] == "dynamic_qr"
