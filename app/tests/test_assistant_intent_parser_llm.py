from app.services import assistant_intent_parser_llm as llm_parser
from app.wallet_chat import parser as wallet_parser


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_resolve_intent_uses_ollama_result_in_hybrid(monkeypatch):
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_MODE", "hybrid")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_PROVIDER", "ollama")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_MODEL", "llama3.1:8b")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_MIN_CONFIDENCE", 0.55)

    def fake_post(url, json=None, timeout=None):
        assert url == "http://localhost:11434/api/generate"
        assert json["model"] == "llama3.1:8b"
        return _FakeResponse({"response": '{"intent":"limits","confidence":0.91,"reason":"mentions plafond"}'})

    monkeypatch.setattr(llm_parser.httpx, "post", fake_post)

    resolved = llm_parser.resolve_intent(
        domain="wallet",
        message="quelles sont mes limites ?",
        intents={"limits": "Limits question", "unknown": "Fallback"},
        heuristic_intent="unknown",
    )

    assert resolved.intent == "limits"
    assert resolved.source == "llm:ollama"
    assert resolved.confidence == 0.91


def test_resolve_intent_uses_openai_compatible_result(monkeypatch):
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_MODE", "hybrid")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_PROVIDER", "openai_compatible")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_MODEL", "mistral-small")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setattr(llm_parser.settings, "ASSISTANT_INTENT_PARSER_API_KEY", "secret")

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "http://localhost:8000/v1/chat/completions"
        assert headers["Authorization"] == "Bearer secret"
        assert json["model"] == "mistral-small"
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"intent":"status_help","confidence":0.84,"reason":"asks about statuses"}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(llm_parser.httpx, "post", fake_post)

    resolved = llm_parser.resolve_intent(
        domain="transfer_support",
        message="que veut dire le statut processing ?",
        intents={"status_help": "Status catalog", "unknown": "Fallback"},
        heuristic_intent="unknown",
    )

    assert resolved.intent == "status_help"
    assert resolved.source == "llm:openai_compatible"
    assert resolved.confidence == 0.84


def test_parse_wallet_message_exposes_intent_parser_metadata(monkeypatch):
    def fake_resolve_intent(domain, message, intents, heuristic_intent):
        assert domain == "wallet"
        assert heuristic_intent == "balance"
        return llm_parser.IntentResolution(intent="limits", source="llm:ollama", confidence=0.88)

    monkeypatch.setattr(wallet_parser, "resolve_intent", fake_resolve_intent)

    draft = wallet_parser.parse_wallet_message("quel est mon solde ?")

    assert draft.intent == "limits"
    assert draft.semantic_hints["intent_parser_source"] == "llm:ollama"
    assert draft.semantic_hints["intent_confidence"] == 0.88
