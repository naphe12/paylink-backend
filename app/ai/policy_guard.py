from app.ai.schemas import PolicyDecision, ResolvedCommand
from app.models.users import Users


async def check_policy(current_user: Users, command: ResolvedCommand) -> PolicyDecision:
    status = str(getattr(current_user, "status", "") or "").lower()
    if status in {"frozen", "closed", "suspended"}:
        return PolicyDecision(allowed=False, reason="Votre compte ne permet pas cette operation actuellement.")

    if command.intent == "transfer.create":
        if bool(getattr(current_user, "external_transfers_blocked", False)):
            return PolicyDecision(allowed=False, reason="Les transferts externes sont bloques pour ce compte.")
        kyc_status = str(getattr(current_user, "kyc_status", "") or "").lower()
        if kyc_status not in {"verified", "reviewing"}:
            return PolicyDecision(allowed=False, reason="Le KYC doit etre verifie avant de preparer un transfert externe.")

    return PolicyDecision(allowed=True)

