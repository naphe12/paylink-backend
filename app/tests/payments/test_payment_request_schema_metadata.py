from types import SimpleNamespace

from app.schemas.payment_requests import PaymentRequestRead


class _MetaDataLike:
    pass


def test_payment_request_read_uses_metadata_column_not_sqlalchemy_metadata():
    payload = SimpleNamespace(
        request_id="bdb0d298-e7e9-4580-8641-f41e44c37306",
        requester_user_id="1fcce64e-fec4-4389-b5de-f3ecf8b25368",
        payer_user_id=None,
        amount="1500.00",
        currency_code="BIF",
        status="pending",
        channel="direct",
        title="Facture internet",
        note=None,
        share_token=None,
        public_pay_url=None,
        scan_to_pay_payload={},
        due_at=None,
        expires_at=None,
        paid_at=None,
        declined_at=None,
        cancelled_at=None,
        last_reminder_at=None,
        manual_reminder_count=0,
        next_manual_reminder_at=None,
        can_send_manual_reminder=True,
        metadata_={"source": "request_service"},
        metadata=_MetaDataLike(),
        created_at="2026-04-08T10:00:00Z",
        updated_at="2026-04-08T10:00:00Z",
    )

    item = PaymentRequestRead.model_validate(payload)

    assert item.metadata_ == {"source": "request_service"}
