from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_action_registry import AiActionRegistry
from app.models.ai_intent_slots import AiIntentSlots
from app.models.ai_intents import AiIntents
from app.models.ai_synonyms import AiSynonyms


class RuntimeMetadata:
    def __init__(
        self,
        intents: dict[str, dict],
        slots: dict[str, list[dict]],
        synonyms: dict[str, dict[str, str]],
        actions: dict[str, dict],
    ) -> None:
        self.intents = intents
        self.slots = slots
        self.synonyms = synonyms
        self.actions = actions


async def load_runtime_metadata(db: AsyncSession) -> RuntimeMetadata:
    intents_rows = (await db.execute(select(AiIntents).where(AiIntents.enabled.is_(True)))).scalars().all()
    slots_rows = (await db.execute(select(AiIntentSlots))).scalars().all()
    synonyms_rows = (await db.execute(select(AiSynonyms))).scalars().all()
    action_rows = (await db.execute(select(AiActionRegistry).where(AiActionRegistry.enabled.is_(True)))).scalars().all()

    intents = {
        row.intent_code: {
            "intent_code": row.intent_code,
            "label": row.label,
            "description": row.description,
            "domain": row.domain,
            "requires_confirmation": bool(row.requires_confirmation),
        }
        for row in intents_rows
    }
    slots: dict[str, list[dict]] = defaultdict(list)
    for row in slots_rows:
        slots[str(row.intent_code)].append(
            {
                "slot_name": row.slot_name,
                "slot_type": row.slot_type,
                "required": bool(row.required),
                "position_hint": row.position_hint,
                "validation_rule": row.validation_rule,
                "example": row.example,
            }
        )
    synonyms: dict[str, dict[str, str]] = defaultdict(dict)
    for row in synonyms_rows:
        synonyms[str(row.domain)][str(row.synonym).strip().lower()] = str(row.canonical_value)
    actions = {
        row.intent_code: {
            "action_code": row.action_code,
            "service_name": row.service_name,
            "method_name": row.method_name,
            "confirmation_template": row.confirmation_template,
            "success_template": row.success_template,
            "failure_template": row.failure_template,
        }
        for row in action_rows
    }
    return RuntimeMetadata(intents=intents, slots=dict(slots), synonyms=dict(synonyms), actions=actions)

