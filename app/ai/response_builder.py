from uuid import UUID

from app.ai.schemas import AiResponse, ParsedIntent


def answer(message: str, *, data: dict | None = None, parsed_intent: ParsedIntent | None = None) -> AiResponse:
    return AiResponse(type="answer", message=message, data=data, parsed_intent=parsed_intent)


def missing_information(message: str, *, missing_fields: list[str], parsed_intent: ParsedIntent | None = None) -> AiResponse:
    return AiResponse(
        type="missing_information",
        message=message,
        missing_fields=missing_fields,
        parsed_intent=parsed_intent,
    )


def confirmation_required(
    message: str,
    *,
    pending_action_id: UUID,
    parsed_intent: ParsedIntent | None = None,
) -> AiResponse:
    return AiResponse(
        type="confirmation_required",
        message=message,
        pending_action_id=pending_action_id,
        parsed_intent=parsed_intent,
    )


def refused(message: str, *, parsed_intent: ParsedIntent | None = None) -> AiResponse:
    return AiResponse(type="refused", message=message, parsed_intent=parsed_intent)

