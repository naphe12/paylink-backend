import json

from sqlalchemy import insert

from app.models.security_events import SecurityEvents, SecuritySeverityEnum


def _normalize_severity(severity: str | SecuritySeverityEnum) -> str:
    if isinstance(severity, SecuritySeverityEnum):
        return severity.value
    return SecuritySeverityEnum(severity.lower()).value


async def log_event(db, user_id: str, severity: str | SecuritySeverityEnum, event_type: str, message: str):
    stmt = insert(SecurityEvents).values(
        user_id=user_id,
        severity=_normalize_severity(severity),
        event_type=event_type,
        details=json.dumps({"message": message}),
    )
    await db.execute(stmt)
    await db.commit()
