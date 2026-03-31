from app.ai.orchestrator import handle_message
from app.ai.metadata_service import load_runtime_metadata
from app.ai.parser import parse_user_message
from app.ai.resolver import resolve_intent as resolve_ai_command
from app.ai.orchestrator import _with_structured_context, _with_next_step, _with_eta, _build_financial_overview_message
from app.agent_chat.schemas import AgentChatDraft, ChatResponse
from app.agent_onboarding_chat.catalog import build_onboarding_suggestions
from app.agent_onboarding_chat.schemas import AgentOnboardingChatResponse, AgentOnboardingDraft
from app.cash_chat.schemas import CashChatResponse, CashDraft
from app.credit_chat.schemas import CreditChatResponse, CreditDraft
from app.escrow_chat.schemas import EscrowChatResponse, EscrowDraft
from app.kyc_chat.schemas import KycChatResponse, KycDraft
from app.p2p_chat.schemas import P2PChatResponse, P2PDraft
from app.transfer_support_chat.schemas import TransferSupportChatResponse, TransferSupportDraft
from app.wallet_chat.schemas import WalletChatResponse, WalletDraft
from app.wallet_support_chat.schemas import WalletSupportChatResponse, WalletSupportDraft

SUPPORTED_AGENT_TRANSFER_PARTNERS = {"Lumicash", "Ecocash", "eNoti"}


def _ai_type_to_support_status(ai_type: str) -> str:
    if ai_type in {"answer", "confirmation_required"}:
        return "INFO"
    if ai_type == "missing_information":
        return "NEED_INFO"
    if ai_type == "cancelled":
        return "CANCELLED"
    return "ERROR"


def _append_next_step(message: str, payload: dict | None) -> str:
    next_step = str((payload or {}).get("next_step") or "").strip()
    if not next_step:
        return message
    return f"{message} Prochaine action recommandee: {next_step}"


def _next_step_suggestions(payload: dict | None) -> list[str]:
    next_step = str((payload or {}).get("next_step") or "").strip()
    if not next_step:
        return []
    return [next_step]


async def handle_transfer_support_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[TransferSupportChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"transfer.status", "help.explain_block_reason"}:
        return (
            TransferSupportChatResponse(
                status="NEED_INFO",
                message="",
            ),
            False,
        )
    data = TransferSupportDraft(
        intent="track_transfer" if intent == "transfer.status" else "pending_reason",
        reference_code=(parsed.entities or {}).get("reference_code") if parsed else None,
        raw_message=message,
        semantic_hints={
            "ai_intent": intent,
            "ai_confidence": getattr(parsed, "confidence", None),
            "resolved_payload": resolved.get("payload") if isinstance(resolved, dict) else None,
        },
    )
    assumptions: list[str] = []
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    if payload.get("aml_reason_codes"):
        assumptions.append(f"Motifs AML: {', '.join(str(item) for item in payload.get('aml_reason_codes') or [])}.")
    if payload.get("review_reasons"):
        assumptions.append(f"Review reasons: {', '.join(str(item) for item in payload.get('review_reasons') or [])}.")
    return (
        TransferSupportChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=_append_next_step(ai_response.message, payload),
            data=data,
            missing_fields=list(ai_response.missing_fields or []),
            executable=False,
            assumptions=assumptions,
            summary=payload or None,
            suggestions=_next_step_suggestions(payload),
        ),
        True,
    )


async def handle_wallet_support_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[WalletSupportChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"wallet.balance", "wallet.financial_overview", "wallet.limits", "wallet.block_reason", "transfer.status", "help.explain_block_reason"}:
        return (
            WalletSupportChatResponse(
                status="NEED_INFO",
                message="",
            ),
            False,
        )
    draft_intent = "limits" if intent in {"wallet.limits", "wallet.financial_overview"} else "cant_send" if intent in {"wallet.block_reason", "transfer.status", "help.explain_block_reason"} else "unknown"
    data = WalletSupportDraft(intent=draft_intent, raw_message=message)
    assumptions = [
        f"Intent IA: {intent}.",
        f"Confiance: {getattr(parsed, 'confidence', None)}.",
    ]
    if intent == "wallet.limits":
        assumptions.append("Reponse alignee sur les limites journalieres et mensuelles du compte.")
    if intent == "wallet.financial_overview":
        assumptions.append("Reponse alignee sur la synthese financiere complete du compte.")
    if intent == "wallet.block_reason":
        assumptions.append("Reponse alignee sur les causes de blocage wallet calculees cote backend.")
    payload = (ai_response.data or None)
    if intent == "help.explain_block_reason" and payload and payload.get("aml_reason_codes"):
        assumptions.append(f"Motifs AML: {', '.join(str(item) for item in payload.get('aml_reason_codes') or [])}.")
    return (
        WalletSupportChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=_append_next_step(ai_response.message, payload),
            data=data,
            missing_fields=list(ai_response.missing_fields or []),
            executable=False,
            assumptions=assumptions,
            summary=payload,
            suggestions=_next_step_suggestions(payload),
        ),
        True,
    )


async def handle_agent_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[ChatResponse, bool]:
    metadata = await load_runtime_metadata(db)
    parsed = parse_user_message(message, metadata)
    if parsed.intent not in {
        "wallet.balance",
        "wallet.financial_overview",
        "wallet.limits",
        "credit.capacity",
        "kyc.status",
        "escrow.status",
        "transfer.create",
        "beneficiary.add",
        "beneficiary.list",
        "transfer.status",
        "help.explain_block_reason",
    }:
        return (
            ChatResponse(
                status="NEED_INFO",
                message="",
            ),
            False,
        )

    command = await resolve_ai_command(
        db,
        current_user=current_user,
        parsed=parsed,
        metadata=metadata,
    )
    if command.intent in {"wallet.balance", "credit.capacity"}:
        payload = command.payload
        wallet_currency = str(payload.get("wallet_currency") or "EUR")
        return (
            ChatResponse(
                status="DONE",
                message=(
                    f"Capacite financiere actuelle: wallet {payload.get('wallet_available')} {wallet_currency}, "
                    f"credit disponible {payload.get('credit_available')} {wallet_currency}."
                ),
                data=AgentChatDraft(
                    intent="capacity",
                    wallet_currency=wallet_currency,
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    if command.intent == "wallet.financial_overview":
        payload = command.payload
        wallet_currency = str(payload.get("wallet_currency") or "EUR")
        return (
            ChatResponse(
                status="DONE",
                message=_build_financial_overview_message(payload),
                data=AgentChatDraft(
                    intent="financial_overview",
                    wallet_currency=wallet_currency,
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    if command.intent == "wallet.limits":
        payload = command.payload
        wallet_currency = str(payload.get("wallet_currency") or "EUR")
        return (
            ChatResponse(
                status="DONE",
                message=(
                    f"Limites actuelles: {payload.get('used_daily')} / {payload.get('daily_limit')} {wallet_currency} aujourd'hui "
                    f"(reste {payload.get('daily_remaining')} {wallet_currency}), "
                    f"et {payload.get('used_monthly')} / {payload.get('monthly_limit')} {wallet_currency} ce mois "
                    f"(reste {payload.get('monthly_remaining')} {wallet_currency})."
                ),
                data=AgentChatDraft(
                    intent="wallet_limits",
                    wallet_currency=wallet_currency,
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    if command.intent == "kyc.status":
        payload = command.payload
        return (
            ChatResponse(
                status="DONE",
                message=(
                    f"Statut KYC actuel: {payload.get('kyc_status')}. Niveau: {payload.get('kyc_tier')}. "
                    f"Limites: {payload.get('daily_limit')} par jour et {payload.get('monthly_limit')} par mois."
                ),
                data=AgentChatDraft(
                    intent="kyc_status",
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    if command.intent == "escrow.status":
        payload = command.payload
        if command.warnings:
            message_out = (
                f"Je ne trouve aucune commande escrow avec l'identifiant {payload.get('order_id')}."
                if payload.get("order_id")
                else "Je ne trouve pas encore de commande escrow pour ce compte."
            )
        else:
            message_out = (
                f"La commande escrow {payload.get('order_id') or ''} est actuellement au statut {payload.get('status') or 'inconnu'}."
            ).strip()
            if payload.get("pending_reasons"):
                message_out = f"{message_out} Cause probable: {list(payload.get('pending_reasons') or [None])[0]}"
            message_out = _with_eta(_with_next_step(_with_structured_context(message_out, payload), payload), payload)
        return (
            ChatResponse(
                status="DONE",
                message=message_out,
                data=AgentChatDraft(
                    intent="escrow_status",
                    order_id=str(payload.get("order_id") or "") or None,
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    if command.intent == "transfer.status":
        payload = command.payload
        if command.warnings:
            message_out = (
                f"Je ne trouve aucune demande avec la reference {payload.get('reference_code')}."
                if payload.get("reference_code")
                else "Je ne trouve pas encore de demande de transfert pour ce compte."
            )
        else:
            message_out = (
                f"Le transfert {payload.get('reference_code') or payload.get('transfer_id') or ''} "
                f"est actuellement {payload.get('transfer_status') or 'inconnu'}."
            ).strip()
            message_out = _with_eta(_with_next_step(_with_structured_context(message_out, payload), payload), payload)
        return (
            ChatResponse(
                status="DONE",
                message=message_out,
                data=AgentChatDraft(
                    intent="transfer_status",
                    reference_code=str(payload.get("reference_code") or "") or None,
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    if command.intent == "help.explain_block_reason":
        payload = command.payload
        assumptions = [
            f"Intent IA: {parsed.intent}.",
            f"Confiance: {parsed.confidence}.",
        ]
        if payload.get("aml_reason_codes"):
            assumptions.append(f"Motifs AML: {', '.join(str(item) for item in payload.get('aml_reason_codes') or [])}.")
        return (
            ChatResponse(
                status="DONE",
                message=_with_eta(
                    _with_next_step(
                        _with_structured_context(str(payload.get("explanation") or "Aucune explication disponible."), payload),
                        payload,
                    ),
                    payload,
                ),
                data=AgentChatDraft(
                    intent="pending_reason",
                    reference_code=str(payload.get("reference_code") or "") or None,
                    raw_message=message,
                ),
                executable=False,
                assumptions=assumptions,
                summary=payload,
            ),
            True,
        )

    if command.intent == "beneficiary.add":
        payload = command.payload
        draft = AgentChatDraft(
            intent="beneficiary_add",
            recipient=payload.get("recipient_name"),
            recipient_phone=payload.get("recipient_phone"),
            account_ref=payload.get("account_ref") or payload.get("recipient_email"),
            partner_name=payload.get("partner_name"),
            country_destination=payload.get("country_destination"),
            raw_message=message,
        )
        if command.missing_fields:
            return (
                ChatResponse(
                    status="NEED_INFO",
                    message="Il manque encore des informations pour enregistrer ce beneficiaire.",
                    data=draft,
                    missing_fields=list(command.missing_fields or []),
                    executable=False,
                    assumptions=list(command.warnings or []),
                    summary=payload,
                ),
                True,
            )
        return (
            ChatResponse(
                status="CONFIRM",
                message=(
                    f"Je suis pret a enregistrer {draft.recipient} comme beneficiaire "
                    f"{draft.partner_name} au numero {draft.recipient_phone}."
                ),
                data=draft,
                missing_fields=[],
                executable=True,
                assumptions=list(command.warnings or []),
                summary=payload,
            ),
            True,
        )

    if command.intent == "beneficiary.list":
        payload = command.payload
        return (
            ChatResponse(
                status="DONE",
                message=ai_response.message,
                data=AgentChatDraft(
                    intent="beneficiary_list",
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {parsed.intent}.",
                    f"Confiance: {parsed.confidence}.",
                ],
                summary=payload,
            ),
            True,
        )

    payload = command.payload
    partner_name = str(payload.get("partner_name") or "") or None
    draft = AgentChatDraft(
        intent="external_transfer",
        amount=payload.get("amount"),
        currency=payload.get("origin_currency"),
        recipient=payload.get("recipient_name"),
        recipient_phone=payload.get("recipient_phone"),
        partner_name=partner_name,
        country_destination=payload.get("country_destination"),
        recognized_beneficiary=bool(payload.get("beneficiary_match_name")),
        raw_message=message,
    )
    executable = not command.missing_fields and partner_name in SUPPORTED_AGENT_TRANSFER_PARTNERS
    if command.missing_fields:
        message_out = " ".join(command.warnings) if command.warnings else "Il manque encore des informations pour preparer le transfert."
        if payload.get("beneficiary_candidates"):
            candidate_options = list(payload.get("beneficiary_candidates") or [])[:3]
            draft.beneficiary_candidates = candidate_options
            options = []
            for index, item in enumerate(candidate_options, start=1):
                options.append(
                    f"{index}. {item.get('recipient_name')} via {item.get('partner_name')} au {item.get('recipient_phone')}"
                )
            if options:
                message_out = f"{message_out} Choisis un index de beneficiaire: {' ; '.join(options)}."
        return (
            ChatResponse(
                status="NEED_INFO",
                message=message_out,
                data=draft,
                missing_fields=list(command.missing_fields or []),
                executable=False,
                assumptions=list(command.warnings or []),
                summary=payload,
            ),
            True,
        )

    confirmation_message = " ".join(command.warnings).strip()
    if confirmation_message:
        confirmation_message = f"{confirmation_message} "
    confirmation_message += (
        f"Je suis pret a preparer la demande de transfert de {draft.amount} {draft.currency} "
        f"a {draft.recipient} via {draft.partner_name} vers {draft.country_destination}."
    )
    return (
        ChatResponse(
            status="CONFIRM",
            message=confirmation_message,
            data=draft,
            missing_fields=[],
            executable=executable,
            assumptions=list(command.warnings or []),
            summary=payload,
        ),
        True,
    )


async def handle_escrow_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[EscrowChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent != "escrow.status":
        return (
            EscrowChatResponse(
                status="NEED_INFO",
                message="",
            ),
            False,
        )
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    return (
        EscrowChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=_append_next_step(ai_response.message, payload),
            data=EscrowDraft(
                intent="track_order" if (parsed.entities or {}).get("order_id") else "latest_status",
                order_id=(parsed.entities or {}).get("order_id") if parsed else None,
                raw_message=message,
            ),
            executable=False,
            assumptions=[
                f"Intent IA: {intent}.",
                f"Confiance: {getattr(parsed, 'confidence', None)}.",
            ],
            summary=payload or None,
            suggestions=_next_step_suggestions(payload),
        ),
        True,
    )


async def handle_cash_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[CashChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"wallet.balance", "cash.capacity", "cash.request_status", "cash.deposit", "cash.withdraw"}:
        return (
            CashChatResponse(
                status="NEED_INFO",
                message="",
            ),
            False,
        )
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    wallet_currency = str(payload.get("wallet_currency") or "EUR")
    if intent in {"cash.deposit", "cash.withdraw"}:
        draft = CashDraft(
            intent="deposit" if intent == "cash.deposit" else "withdraw",
            amount=payload.get("amount"),
            currency=str(payload.get("currency") or wallet_currency) or None,
            mobile_number=payload.get("mobile_number"),
            provider_name=payload.get("provider_name"),
            note=payload.get("note"),
            wallet_currency=wallet_currency,
            raw_message=message,
        )
        return (
            CashChatResponse(
                status="CONFIRM" if not ai_response.missing_fields else "NEED_INFO",
                message=(
                    ai_response.message
                    if ai_response.message
                    else "Je suis pret a preparer la demande cash."
                ),
                data=draft,
                missing_fields=list(ai_response.missing_fields or []),
                executable=not ai_response.missing_fields,
                assumptions=[
                    f"Intent IA: {intent}.",
                    f"Confiance: {getattr(parsed, 'confidence', None)}.",
                ],
                summary=payload or None,
            ),
            True,
        )
    if intent == "cash.request_status":
        return (
            CashChatResponse(
                status=_ai_type_to_support_status(ai_response.type),
                message=ai_response.message,
                data=CashDraft(
                    intent="request_status",
                    currency=str(payload.get("currency") or "") or None,
                    raw_message=message,
                ),
                executable=False,
                assumptions=[
                    f"Intent IA: {intent}.",
                    f"Confiance: {getattr(parsed, 'confidence', None)}.",
                ],
                summary=payload or None,
            ),
            True,
        )
    return (
        CashChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=(
                f"Capacite actuelle: wallet {payload.get('wallet_available')} {wallet_currency}, "
                f"credit {payload.get('credit_available')} {wallet_currency}."
            ),
            data=CashDraft(
                intent="capacity",
                currency=wallet_currency,
                wallet_currency=wallet_currency,
                raw_message=message,
            ),
            executable=False,
            assumptions=[
                f"Intent IA: {intent}.",
                f"Confiance: {getattr(parsed, 'confidence', None)}.",
            ],
            summary=payload or None,
        ),
        True,
    )


async def handle_kyc_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[KycChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent != "kyc.status":
        return (KycChatResponse(status="NEED_INFO", message=""), False)
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    return (
        KycChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=ai_response.message,
            data=KycDraft(intent=str((parsed.entities or {}).get("kyc_view") or "status"), raw_message=message),
            executable=False,
            assumptions=[
                f"Intent IA: {intent}.",
                f"Confiance: {getattr(parsed, 'confidence', None)}.",
            ],
            summary=payload or None,
        ),
        True,
    )


async def handle_p2p_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[P2PChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"p2p.trade_status", "p2p.offers_summary"}:
        return (P2PChatResponse(status="NEED_INFO", message=""), False)
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    draft_intent = "offers_summary" if intent == "p2p.offers_summary" else str((parsed.entities or {}).get("p2p_view") or "latest_trade")
    return (
        P2PChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=_append_next_step(ai_response.message, payload),
            data=P2PDraft(intent=draft_intent, trade_id=(parsed.entities or {}).get("trade_id"), raw_message=message),
            executable=False,
            assumptions=[
                f"Intent IA: {intent}.",
                f"Confiance: {getattr(parsed, 'confidence', None)}.",
            ],
            summary=payload or None,
            suggestions=_next_step_suggestions(payload),
        ),
        True,
    )


async def handle_credit_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[CreditChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"credit.capacity", "credit.simulate_capacity", "credit.pending_reason"}:
        return (CreditChatResponse(status="NEED_INFO", message=""), False)
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    if intent == "credit.capacity":
        wallet_currency = str(payload.get("wallet_currency") or "EUR")
        return (
            CreditChatResponse(
                status=_ai_type_to_support_status(ai_response.type),
                message=(
                    f"Capacite actuelle: wallet {payload.get('wallet_available')} {wallet_currency}, "
                    f"credit disponible {payload.get('credit_available')} {wallet_currency}."
                ),
                data=CreditDraft(intent="capacity", currency=wallet_currency, wallet_currency=wallet_currency, raw_message=message),
                executable=False,
                assumptions=[
                    f"Intent IA: {intent}.",
                    f"Confiance: {getattr(parsed, 'confidence', None)}.",
                ],
                summary=payload or None,
            ),
            True,
        )

    if intent == "credit.pending_reason":
        return (
            CreditChatResponse(
                status=_ai_type_to_support_status(ai_response.type),
                message=ai_response.message,
                data=CreditDraft(intent="pending_reason", raw_message=message),
                executable=False,
                assumptions=[
                    f"Intent IA: {intent}.",
                    f"Confiance: {getattr(parsed, 'confidence', None)}.",
                ],
                summary=payload or None,
            ),
            True,
        )

    amount_value = payload.get("amount")
    currency = str(payload.get("currency") or payload.get("wallet_currency") or "EUR")
    return (
        CreditChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=ai_response.message,
            data=CreditDraft(intent="simulate_transfer", amount=amount_value, currency=currency, wallet_currency=str(payload.get("wallet_currency") or "EUR"), raw_message=message),
            missing_fields=list(ai_response.missing_fields or []),
            executable=False,
            assumptions=[
                f"Intent IA: {intent}.",
                f"Confiance: {getattr(parsed, 'confidence', None)}.",
            ],
            summary=payload or None,
        ),
        True,
    )


async def handle_wallet_chat_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[WalletChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"wallet.balance", "wallet.financial_overview", "wallet.limits"}:
        return (WalletChatResponse(status="NEED_INFO", message=""), False)
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    draft_intent = "balance" if intent == "wallet.balance" else "limits"
    return (
        WalletChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=ai_response.message,
            data=WalletDraft(
                intent=draft_intent,
                raw_message=message,
                semantic_hints={
                    "ai_intent": intent,
                    "ai_confidence": getattr(parsed, "confidence", None),
                    "resolved_payload": resolved.get("payload") if isinstance(resolved, dict) else None,
                },
            ),
            executable=False,
            assumptions=[
                f"Intent IA: {intent}.",
                f"Confiance: {getattr(parsed, 'confidence', None)}.",
            ],
            summary=payload or None,
        ),
        True,
    )


async def handle_agent_onboarding_with_ai(
    db,
    *,
    current_user,
    message: str,
) -> tuple[AgentOnboardingChatResponse, bool]:
    ai_response, parsed, resolved = await handle_message(
        db,
        current_user=current_user,
        message=message,
        session_id=None,
    )
    intent = str(getattr(parsed, "intent", "") or "")
    if intent not in {"agent_onboarding.guide", "agent_onboarding.scenario"}:
        return (AgentOnboardingChatResponse(status="NEED_INFO", message=""), False)
    payload = (ai_response.data or {}) if hasattr(ai_response, "data") else {}
    draft = AgentOnboardingDraft(
        intent=str(payload.get("guide_topic") or "unknown"),
        scenario=str(payload.get("scenario") or "none"),
        raw_message=message,
    )
    if intent == "agent_onboarding.guide":
        draft.scenario = "none"
    if intent == "agent_onboarding.scenario":
        draft.intent = "unknown"
    return (
        AgentOnboardingChatResponse(
            status=_ai_type_to_support_status(ai_response.type),
            message=ai_response.message,
            data=draft,
            executable=False,
            suggestions=[] if payload else build_onboarding_suggestions(),
            assumptions=list(payload.get("assumptions") or []),
            summary=payload.get("summary") if payload else None,
        ),
        True,
    )
