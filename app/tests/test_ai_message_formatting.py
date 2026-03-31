from app.ai.orchestrator import _with_structured_context


def test_with_structured_context_appends_dossier_actor_and_blocker():
    message = _with_structured_context(
        "Le transfert est pending.",
        {
            "dossier_type": "funding",
            "who_must_act_now": "client",
            "primary_blocker": "Le dossier n'est pas encore suffisamment finance.",
        },
    )

    assert "Type de dossier: financement requis." in message
    assert "Acteur attendu maintenant: client." in message
    assert "Blocage principal: Le dossier n'est pas encore suffisamment finance." in message


def test_with_structured_context_appends_current_user_role_when_present():
    message = _with_structured_context(
        "Le trade est en litige.",
        {
            "dossier_type": "dispute",
            "who_must_act_now": "operations",
            "current_user_role": "buyer",
            "primary_blocker": "Le trade est en litige et attend une resolution.",
        },
    )

    assert "Type de dossier: en litige." in message
    assert "Acteur attendu maintenant: operations." in message
    assert "Votre role actuel: acheteur." in message
