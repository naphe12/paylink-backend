import asyncio
from decimal import Decimal
from types import SimpleNamespace

from app.ai import legacy_adapters
from app.ai.metadata_service import RuntimeMetadata
from app.ai.schemas import ParsedIntent, ResolvedCommand
from app.agent_chat.schemas import AgentChatDraft
from app.agent_chat.utils import apply_selected_beneficiary


def test_handle_agent_chat_with_ai_returns_beneficiary_candidates(monkeypatch):
    metadata = RuntimeMetadata(intents={}, slots={}, synonyms={}, actions={})
    parsed = ParsedIntent(intent="transfer.create", confidence=0.91, entities={})
    command = ResolvedCommand(
        intent="transfer.create",
        action_code="transfer.create_external_transfer",
        payload={
            "amount": Decimal("100"),
            "origin_currency": "EUR",
            "recipient_name": "Michel",
            "beneficiary_candidates": [
                {
                    "recipient_name": "Michel",
                    "recipient_phone": "23333",
                    "partner_name": "Lumicash",
                    "country_destination": "Burundi",
                    "account_ref": None,
                },
                {
                    "recipient_name": "Michel",
                    "recipient_phone": "24444",
                    "partner_name": "Ecocash",
                    "country_destination": "Zimbabwe",
                    "account_ref": "michel@ecocash",
                },
            ],
        },
        missing_fields=["beneficiary_selection"],
        warnings=["Plusieurs beneficiaires correspondent a Michel."],
    )

    async def fake_load_runtime_metadata(db):
        return metadata

    def fake_parse_user_message(message, loaded_metadata):
        assert loaded_metadata is metadata
        return parsed

    async def fake_resolve_ai_command(db, *, current_user, parsed, metadata):
        return command

    monkeypatch.setattr(legacy_adapters, "load_runtime_metadata", fake_load_runtime_metadata)
    monkeypatch.setattr(legacy_adapters, "parse_user_message", fake_parse_user_message)
    monkeypatch.setattr(legacy_adapters, "resolve_ai_command", fake_resolve_ai_command)

    response, used_ai = asyncio.run(
        legacy_adapters.handle_agent_chat_with_ai(
            db=object(),
            current_user=SimpleNamespace(user_id="user-1"),
            message="envoie 100 eur a Michel",
        )
    )

    assert used_ai is True
    assert response.status == "NEED_INFO"
    assert response.executable is False
    assert response.data is not None
    assert response.data.beneficiary_candidates[0]["partner_name"] == "Lumicash"
    assert response.data.beneficiary_candidates[1]["account_ref"] == "michel@ecocash"
    assert "Choisis un index de beneficiaire" in response.message
    assert response.missing_fields == ["beneficiary_selection"]


def test_apply_selected_beneficiary_enriches_missing_fields():
    draft = AgentChatDraft(
        intent="external_transfer",
        amount=Decimal("100"),
        currency="EUR",
        recipient="Michel",
        raw_message="envoie 100 eur a Michel",
        beneficiary_candidates=[
            {
                "recipient_name": "Michel",
                "recipient_phone": "23333",
                "partner_name": "Lumicash",
                "country_destination": "Burundi",
                "account_ref": None,
            },
            {
                "recipient_name": "Michel",
                "recipient_phone": "24444",
                "partner_name": "Ecocash",
                "country_destination": "Zimbabwe",
                "account_ref": "michel@ecocash",
            },
        ],
        selected_beneficiary_index=2,
    )

    enriched = apply_selected_beneficiary(draft)

    assert enriched.recipient == "Michel"
    assert enriched.recipient_phone == "24444"
    assert enriched.partner_name == "Ecocash"
    assert enriched.country_destination == "Zimbabwe"
    assert enriched.account_ref == "michel@ecocash"


def test_apply_selected_beneficiary_does_not_override_existing_values():
    draft = AgentChatDraft(
        intent="external_transfer",
        amount=Decimal("100"),
        currency="EUR",
        recipient="Michel",
        recipient_phone="99999",
        partner_name="Lumicash",
        country_destination="Burundi",
        account_ref="custom-ref",
        raw_message="envoie 100 eur a Michel",
        beneficiary_candidates=[
            {
                "recipient_name": "Michel",
                "recipient_phone": "24444",
                "partner_name": "Ecocash",
                "country_destination": "Zimbabwe",
                "account_ref": "michel@ecocash",
            }
        ],
        selected_beneficiary_index=1,
    )

    enriched = apply_selected_beneficiary(draft)

    assert enriched.recipient_phone == "99999"
    assert enriched.partner_name == "Lumicash"
    assert enriched.country_destination == "Burundi"
    assert enriched.account_ref == "custom-ref"
