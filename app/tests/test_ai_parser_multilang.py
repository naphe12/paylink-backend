from decimal import Decimal

from app.ai.metadata_service import RuntimeMetadata
from app.ai.parser import parse_user_message


def _metadata() -> RuntimeMetadata:
    return RuntimeMetadata(
        intents={
            "beneficiary.add": {"requires_confirmation": True},
            "beneficiary.list": {"requires_confirmation": False},
            "transfer.create": {"requires_confirmation": True},
            "wallet.block_reason": {"requires_confirmation": False},
        },
        slots={
            "beneficiary.add": [
                {"slot_name": "recipient_name", "required": True},
                {"slot_name": "partner_name", "required": True},
                {"slot_name": "recipient_phone", "required": True},
                {"slot_name": "country_destination", "required": True},
            ],
            "transfer.create": [
                {"slot_name": "amount", "required": True},
                {"slot_name": "origin_currency", "required": True},
                {"slot_name": "recipient_name", "required": True},
                {"slot_name": "partner_name", "required": True},
                {"slot_name": "recipient_phone", "required": True},
                {"slot_name": "country_destination", "required": True},
            ],
        },
        synonyms={
            "intent": {
                "add beneficiary": "beneficiary.add",
                "why can't i send": "wallet.block_reason",
                "rungika": "transfer.create",
                "kubera iki sinshobora kurungika": "wallet.block_reason",
                "tuma pesa": "transfer.create",
                "kwa nini siwezi kutuma": "wallet.block_reason",
                "my beneficiaries": "beneficiary.list",
            },
            "network": {
                "lumikash": "Lumicash",
                "ekokash": "Ecocash",
            },
        },
        actions={},
    )


def test_parse_user_message_english_beneficiary_add_uses_synonym_intent():
    parsed = parse_user_message(
        "add beneficiary Michel via Lumicash to +25761234567",
        _metadata(),
    )

    assert parsed.intent == "beneficiary.add"
    assert parsed.entities["partner_name"] == "Lumicash"
    assert parsed.entities["recipient_phone"] == "+25761234567"


def test_parse_user_message_network_synonym_normalizes_partner_name():
    parsed = parse_user_message(
        "send 100 eur to Michel via lumikash 23333",
        _metadata(),
    )

    assert parsed.intent == "transfer.create"
    assert parsed.entities["amount"] == Decimal("100")
    assert parsed.entities["origin_currency"] == "EUR"
    assert parsed.entities["partner_name"] == "Lumicash"


def test_parse_user_message_english_wallet_block_reason_uses_synonym_intent():
    parsed = parse_user_message(
        "why can't i send",
        _metadata(),
    )

    assert parsed.intent == "wallet.block_reason"
    assert parsed.requires_confirmation is False


def test_parse_user_message_kirundi_transfer_uses_synonym_intent():
    parsed = parse_user_message(
        "rungika 100 eur via lumikash 23333",
        _metadata(),
    )

    assert parsed.intent == "transfer.create"
    assert parsed.entities["amount"] == Decimal("100")
    assert parsed.entities["partner_name"] == "Lumicash"


def test_parse_user_message_kirundi_wallet_block_reason_uses_synonym_intent():
    parsed = parse_user_message(
        "kubera iki sinshobora kurungika",
        _metadata(),
    )

    assert parsed.intent == "wallet.block_reason"


def test_parse_user_message_swahili_transfer_uses_synonym_intent():
    parsed = parse_user_message(
        "tuma pesa 100 eur via lumikash 23333",
        _metadata(),
    )

    assert parsed.intent == "transfer.create"
    assert parsed.entities["amount"] == Decimal("100")
    assert parsed.entities["partner_name"] == "Lumicash"


def test_parse_user_message_swahili_wallet_block_reason_uses_synonym_intent():
    parsed = parse_user_message(
        "kwa nini siwezi kutuma",
        _metadata(),
    )

    assert parsed.intent == "wallet.block_reason"


def test_parse_user_message_beneficiary_list_uses_synonym_intent():
    parsed = parse_user_message(
        "my beneficiaries",
        _metadata(),
    )

    assert parsed.intent == "beneficiary.list"
