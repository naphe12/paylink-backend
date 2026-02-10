from fastapi import HTTPException, status

def require_operator(user) -> None:
    # adapte: user.role, user.is_admin, scopes, etc.
    if getattr(user, "role", None) not in ("OPERATOR", "SUPERVISOR", "ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator role required")
