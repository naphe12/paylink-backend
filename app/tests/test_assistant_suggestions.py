from app.services.assistant_suggestions import build_assistant_suggestions


def test_cash_unknown_suggestions_cover_multiple_capabilities():
    suggestions = build_assistant_suggestions("cash", intent="unknown")

    assert len(suggestions) >= 6
    assert any("depot" in item.lower() for item in suggestions)
    assert any("retrait" in item.lower() for item in suggestions)
    assert any("capacite" in item.lower() for item in suggestions)
    assert any("statut" in item.lower() for item in suggestions)


def test_agent_transfer_missing_fields_keep_contextual_hints_and_examples():
    suggestions = build_assistant_suggestions(
        "agent_transfer",
        intent="external_transfer",
        missing_fields=["partner_name", "recipient_phone"],
        extra_examples=["Beneficiaires habituels reconnus: Jean, Aline."],
    )

    assert suggestions[0] == "Beneficiaires habituels reconnus: Jean, Aline."
    assert any("partenaire" in item.lower() for item in suggestions)
    assert any("numero" in item.lower() for item in suggestions)
    assert any("exemple:" in item.lower() for item in suggestions)
