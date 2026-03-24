from uuid import UUID


def resolve_target_user_id(current_user, target_user_id: UUID | None = None):
    if str(getattr(current_user, "role", "") or "").lower() == "admin" and target_user_id:
        return target_user_id
    return getattr(current_user, "user_id", None)
