from app.agent_chat.schemas import AgentChatDraft


def apply_selected_beneficiary(draft: AgentChatDraft) -> AgentChatDraft:
    if draft.selected_beneficiary_index is None or not draft.beneficiary_candidates:
        return draft
    if draft.selected_beneficiary_index < 1 or draft.selected_beneficiary_index > len(draft.beneficiary_candidates):
        return draft
    selected = draft.beneficiary_candidates[draft.selected_beneficiary_index - 1] or {}
    if not draft.recipient:
        draft.recipient = selected.get("recipient_name")
    if not draft.recipient_phone:
        draft.recipient_phone = selected.get("recipient_phone")
    if not draft.partner_name:
        draft.partner_name = selected.get("partner_name")
    if not draft.country_destination:
        draft.country_destination = selected.get("country_destination")
    if not draft.account_ref:
        draft.account_ref = selected.get("account_ref") or selected.get("recipient_email")
    return draft
