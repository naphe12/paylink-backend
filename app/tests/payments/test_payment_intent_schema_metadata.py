from types import SimpleNamespace

from app.schemas.payments import PaymentIntentRead


class _MetaDataLike:
    pass


def test_payment_intent_read_uses_metadata_column_not_sqlalchemy_metadata():
    payload = SimpleNamespace(
        intent_id="8f52e59a-6b41-4437-a2e9-fd545dc07b5f",
        direction="deposit",
        rail="mobile_money",
        status="pending",
        provider_code="lumicash_aggregator",
        provider_channel="Lumicash",
        amount="1000.00",
        currency_code="BIF",
        merchant_reference="PMT-123",
        provider_reference=None,
        payer_identifier="+25770000001",
        target_instructions={"wallet_type": "consumer"},
        metadata_={"source": "admin_list"},
        metadata=_MetaDataLike(),
        settled_at=None,
        credited_at=None,
        expires_at=None,
        created_at="2026-04-08T10:00:00Z",
    )

    item = PaymentIntentRead.model_validate(payload)

    assert item.metadata_ == {"source": "admin_list"}
