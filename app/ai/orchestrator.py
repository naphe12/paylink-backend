from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import response_builder
from app.ai.confirmation_service import clear_conversation_state, create_pending_action, load_conversation_state, save_conversation_state
from app.ai.metadata_service import load_runtime_metadata
from app.ai.parser import parse_user_message
from app.ai.policy_guard import check_policy
from app.ai.resolver import resolve_intent as resolve_command
from app.ai.schemas import AiResponse, ParsedIntent
from app.models.users import Users


def _format_amount(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{amount:,.2f}"
    return formatted.replace(",", " ")


def _build_financial_overview_message(data: dict[str, Any]) -> str:
    currency = str(data.get("wallet_currency") or "EUR")
    wallet_available = _format_amount(data.get("wallet_available"))
    credit_remaining = _format_amount(data.get("credit_remaining"))
    daily_remaining = _format_amount(data.get("daily_remaining"))
    monthly_remaining = _format_amount(data.get("monthly_remaining"))
    status = str(data.get("status") or "inconnu").lower()
    kyc_status = str(data.get("kyc_status") or "inconnu").lower()
    diagnostic = str(data.get("diagnostic_probable") or "A_VERIFIER_COTE_LOGS_OU_FRONT")

    segments = [
        f"Situation financiere : compte {status}, KYC {kyc_status}.",
        f"Wallet disponible : {wallet_available} {currency}.",
        f"Credit disponible : {credit_remaining} {currency}.",
        f"Reste de limite : {daily_remaining} {currency} aujourd'hui et {monthly_remaining} {currency} ce mois.",
    ]

    if data.get("reference_code"):
        transfer_amount = _format_amount(data.get("last_transfer_amount"))
        transfer_currency = str(data.get("last_transfer_currency") or currency)
        transfer_status = str(data.get("transfer_status") or "inconnu")
        segments.append(
            f"Dernier transfert : {data.get('reference_code')} de {transfer_amount} {transfer_currency}, statut {transfer_status}."
        )

    diagnostic_labels = {
        "COMPTE_NON_ACTIF": "Diagnostic probable : compte non actif.",
        "TRANSFERTS_EXTERNES_SUSPENDUS": "Diagnostic probable : transferts externes suspendus.",
        "LIMITE_JOURNALIERE_DEPASSEE_POUR_600": "Diagnostic probable : un transfert de 600 depasserait la limite journaliere.",
        "LIMITE_MENSUELLE_DEPASSEE_POUR_600": "Diagnostic probable : un transfert de 600 depasserait la limite mensuelle.",
        "COUVERTURE_INSUFFISANTE_POUR_600_HORS_FRAIS": "Diagnostic probable : la couverture disponible reste insuffisante pour 600 hors frais.",
        "TRANSFERT_EN_ATTENTE_DE_FINANCEMENT": "Diagnostic probable : le dernier transfert reste en attente de financement.",
        "REVUE_AML_MANUELLE": "Diagnostic probable : le dernier transfert est en revue AML manuelle.",
        "A_VERIFIER_COTE_LOGS_OU_FRONT": "Diagnostic probable : rien de bloquant n'apparait ici, verifier les logs ou le front.",
    }
    segments.append(diagnostic_labels.get(diagnostic, f"Diagnostic probable : {diagnostic}."))
    return " ".join(segments)


def _merge_entities(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if value not in (None, "", []):
            merged[key] = value
    return merged


def _missing_fields_message(missing_fields: list[str]) -> str:
    labels = {
        "partner_name": "le canal ou partenaire",
        "country_destination": "le pays de destination",
        "recipient_name": "le nom du beneficiaire",
        "recipient_phone": "le numero du beneficiaire",
        "account_ref": "le compte ou identifiant du beneficiaire",
        "beneficiary_selection": "le beneficiaire exact",
        "amount": "le montant",
        "origin_currency": "la devise",
    }
    humanized = [labels.get(item, item) for item in missing_fields]
    if len(humanized) == 1:
        return f"Il me manque {humanized[0]}."
    return f"Il me manque {', '.join(humanized[:-1])} et {humanized[-1]}."


def _build_limits_message(data: dict[str, Any]) -> str:
    currency = str(data.get("wallet_currency") or "EUR")
    daily_limit = _format_amount(data.get("daily_limit"))
    used_daily = _format_amount(data.get("used_daily"))
    daily_remaining = _format_amount(data.get("daily_remaining"))
    monthly_limit = _format_amount(data.get("monthly_limit"))
    used_monthly = _format_amount(data.get("used_monthly"))
    monthly_remaining = _format_amount(data.get("monthly_remaining"))
    return (
        f"Limite journaliere : {used_daily} / {daily_limit} {currency}, "
        f"reste {daily_remaining} {currency}. "
        f"Limite mensuelle : {used_monthly} / {monthly_limit} {currency}, "
        f"reste {monthly_remaining} {currency}."
    )


def _build_transfer_confirmation(payload: dict[str, Any]) -> str:
    amount = payload.get("amount") or "0"
    currency = payload.get("origin_currency") or payload.get("currency") or "EUR"
    recipient_name = payload.get("recipient_name") or "le beneficiaire"
    partner = payload.get("partner_name") or "le canal choisi"
    phone = payload.get("recipient_phone") or "numero non precise"
    country = payload.get("country_destination") or "destination non precisee"
    return f"Je vais preparer un transfert de {amount} {currency} a {recipient_name} via {partner} au numero {phone} pour {country}. Confirmer ?"


def _build_beneficiary_confirmation(payload: dict[str, Any]) -> str:
    recipient_name = payload.get("recipient_name") or "le beneficiaire"
    partner = payload.get("partner_name") or "le canal choisi"
    phone = payload.get("recipient_phone") or "numero non precise"
    country = payload.get("country_destination") or "destination non precisee"
    return f"Je vais enregistrer {recipient_name} comme beneficiaire {partner} au numero {phone} pour {country}. Confirmer ?"


def _prepend_warnings(message: str, warnings: list[str]) -> str:
    if not warnings:
        return message
    return f"{' '.join(warnings)} {message}"


def _beneficiary_selection_message(payload: dict[str, Any]) -> str:
    candidates = list(payload.get("beneficiary_candidates") or [])
    if not candidates:
        return "Plusieurs beneficiaires correspondent. Precise le bon beneficiaire."
    options = []
    for item in candidates[:3]:
        recipient_name = str(item.get("recipient_name") or "beneficiaire").strip()
        partner_name = str(item.get("partner_name") or "canal inconnu").strip()
        phone = str(item.get("recipient_phone") or "numero inconnu").strip()
        country = str(item.get("country_destination") or "destination inconnue").strip()
        options.append(f"{recipient_name} via {partner_name} au {phone} pour {country}")
    return f"Plusieurs beneficiaires correspondent. Precise lequel tu veux utiliser: {' ; '.join(options)}."


async def handle_message(
    db: AsyncSession,
    *,
    current_user: Users,
    message: str,
    session_id: UUID | None,
) -> tuple[AiResponse, ParsedIntent | None, dict | None]:
    metadata = await load_runtime_metadata(db)
    parsed = parse_user_message(message, metadata)
    state = await load_conversation_state(db, session_id, current_user.user_id)

    if state and state.state == "active":
        base_entities = dict(state.collected_slots or {})
        if parsed.intent in {"unknown", None} and str(state.current_intent or "").strip():
            parsed.intent = state.current_intent
        if parsed.intent == state.current_intent and parsed.intent in {"transfer.create", "beneficiary.add"}:
            parsed.entities = _merge_entities(base_entities, parsed.entities)
            parsed.missing_fields = [
                slot["slot_name"]
                for slot in metadata.slots.get(parsed.intent, [])
                if slot.get("required") and parsed.entities.get(slot["slot_name"]) in (None, "", [])
            ]
            parsed.requires_confirmation = not parsed.missing_fields

    command = await resolve_command(db, current_user, parsed, metadata)
    policy = await check_policy(current_user, command)
    if not policy.allowed:
        return response_builder.refused(policy.reason or "Action refusee.", parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "wallet.balance":
        data = command.payload
        currency = data.get("wallet_currency") or "EUR"
        wallet_available = _format_amount(data.get("wallet_available"))
        credit_available = _format_amount(data.get("credit_available"))
        message_out = (
            f"Solde wallet disponible : {wallet_available} {currency}. "
            f"Credit disponible : {credit_available} {currency}."
        )
        await clear_conversation_state(db, session_id, current_user.user_id)
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "wallet.financial_overview":
        data = command.payload
        message_out = _build_financial_overview_message(data)
        await clear_conversation_state(db, session_id, current_user.user_id)
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "agent_onboarding.guide":
        data = command.payload
        message_out = str(data.get("message") or "Guide onboarding indisponible.")
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "agent_onboarding.scenario":
        data = command.payload
        message_out = str(data.get("message") or "Scenario onboarding indisponible.")
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "cash.capacity":
        data = command.payload
        wallet_currency = data.get("wallet_currency") or "EUR"
        message_out = (
            f"Capacite cash actuelle : wallet {_format_amount(data.get('wallet_available'))} {wallet_currency}, "
            f"credit {_format_amount(data.get('credit_available'))} {wallet_currency}."
        )
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "cash.request_status":
        data = command.payload
        if command.warnings:
            return (
                response_builder.answer(
                    "Je ne vois pas encore de demande cash recente sur ce compte.",
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        message_out = f"La derniere demande cash est un {data.get('request_type')} actuellement au statut {data.get('request_status')}."
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent in {"cash.deposit", "cash.withdraw"}:
        data = command.payload
        if command.missing_fields:
            return (
                response_builder.missing_information(
                    _missing_fields_message(command.missing_fields),
                    missing_fields=command.missing_fields,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        pending = await create_pending_action(
            db,
            current_user=current_user,
            session_id=session_id,
            intent_code=command.intent,
            action_code=command.action_code,
            payload=command.payload,
        )
        action_label = "depot" if command.intent == "cash.deposit" else "retrait"
        detail = ""
        if command.intent == "cash.withdraw":
            detail = f" via {data.get('provider_name')} au {data.get('mobile_number')}"
        message_out = f"Je vais preparer la demande de {action_label} de {data.get('amount')} {data.get('currency')}{detail}. Confirmer ?"
        return response_builder.confirmation_required(
            message_out,
            pending_action_id=pending.id,
            parsed_intent=parsed,
        ), parsed, command.model_dump(mode="json")

    if command.intent == "wallet.block_reason":
        data = command.payload
        return response_builder.answer(
            str(data.get("explanation") or "Aucune explication disponible."),
            data=data,
            parsed_intent=parsed,
        ), parsed, command.model_dump(mode="json")

    if command.intent == "wallet.limits":
        data = command.payload
        message_out = _build_limits_message(data)
        await clear_conversation_state(db, session_id, current_user.user_id)
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "credit.capacity":
        data = command.payload
        wallet_currency = data.get("wallet_currency") or "EUR"
        message_out = (
            f"Capacite actuelle : wallet {_format_amount(data.get('wallet_available'))} {wallet_currency}, "
            f"credit disponible {_format_amount(data.get('credit_available'))} {wallet_currency}."
        )
        await clear_conversation_state(db, session_id, current_user.user_id)
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "credit.simulate_capacity":
        data = command.payload
        if command.missing_fields:
            return (
                response_builder.missing_information(
                    _missing_fields_message(command.missing_fields),
                    missing_fields=command.missing_fields,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        amount = data.get("amount") or "0"
        currency = data.get("currency") or data.get("wallet_currency") or "EUR"
        message_out = (
            f"Je peux simuler {_format_amount(amount)} {currency}. Capacite actuelle : "
            f"wallet {_format_amount(data.get('wallet_available'))} {data.get('wallet_currency')}, "
            f"credit {_format_amount(data.get('credit_available'))} {data.get('wallet_currency')}."
        )
        await clear_conversation_state(db, session_id, current_user.user_id)
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "credit.pending_reason":
        data = command.payload
        if command.warnings:
            return (
                response_builder.answer(
                    "Je ne trouve pas de demande de transfert en attente recente.",
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        return response_builder.answer(
            str(data.get("explanation") or "Aucune explication disponible."),
            data=data,
            parsed_intent=parsed,
        ), parsed, command.model_dump(mode="json")

    if command.intent == "kyc.status":
        data = command.payload
        view = str(data.get("kyc_view") or "status")
        if view == "missing_docs":
            message_out = (
                "Documents encore attendus: " + ", ".join(data.get("missing_docs") or []) + "."
                if data.get("missing_docs")
                else "Je ne vois pas de document KYC manquant dans les donnees disponibles."
            )
        elif view == "limits":
            message_out = (
                f"Tes plafonds actuels sont {data.get('daily_limit')} par jour et {data.get('monthly_limit')} par mois. "
                f"Utilisation en cours: {data.get('used_daily')} aujourd'hui et {data.get('used_monthly')} ce mois."
            )
        elif view == "upgrade_benefits":
            current_tier = int(data.get("kyc_tier") or 0)
            next_tier = min(current_tier + 1, 3)
            message_out = (
                f"Le niveau suivant est {next_tier}. Il augmentera les plafonds apres validation du dossier KYC."
                if next_tier != current_tier
                else "Tu es deja au niveau KYC le plus eleve configure actuellement."
            )
        else:
            message_out = (
                f"Statut KYC actuel: {data.get('kyc_status')}. Niveau: {data.get('kyc_tier')}. "
                f"Limites actuelles: {data.get('daily_limit')} par jour et {data.get('monthly_limit')} par mois."
            )
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "escrow.status":
        data = command.payload
        if command.warnings:
            return (
                response_builder.answer(
                    (
                        f"Je ne trouve aucune commande escrow avec l'identifiant {data.get('order_id')}."
                        if data.get("order_id")
                        else "Je ne trouve pas encore de commande escrow pour ce compte."
                    ),
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        order_id = data.get("order_id")
        status_text = data.get("status") or "inconnu"
        message_out = (
            f"La commande escrow {order_id} est actuellement au statut {status_text}."
            if order_id
            else f"Le dernier escrow est actuellement au statut {status_text}."
        )
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "p2p.offers_summary":
        data = command.payload
        count = int(data.get("open_offers_count") or 0)
        message_out = (
            f"Vous avez actuellement {count} offre(s) P2P active(s)."
            if count
            else "Je ne vois pas d'offre P2P active pour le moment."
        )
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "p2p.trade_status":
        data = command.payload
        if command.warnings:
            return (
                response_builder.answer(
                    "Je ne trouve pas de trade P2P correspondant a cette demande.",
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        view = str(data.get("p2p_view") or "latest_trade")
        if view == "why_blocked":
            message_out = f"Le trade est au statut {data.get('trade_status')}. Voici les causes probables du blocage ou de l'attente."
        elif view == "next_step":
            message_out = str(data.get("next_step") or "Verifier la timeline du trade.")
        else:
            message_out = f"Votre trade P2P est actuellement au statut {data.get('trade_status')}."
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "transfer.status":
        data = command.payload
        if command.warnings:
            return (
                response_builder.answer(
                    (
                        f"Je ne trouve aucune demande avec la reference {data.get('reference_code')}."
                        if data.get("reference_code")
                        else "Je ne trouve pas encore de demande de transfert pour ce compte."
                    ),
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        status_text = data.get("transfer_status") or "inconnu"
        reference_text = data.get("reference_code") or data.get("transfer_id")
        message_out = (
            f"Le transfert {reference_text} est actuellement {status_text}."
            if reference_text
            else f"Le dernier transfert est actuellement {status_text}."
        )
        return response_builder.answer(message_out, data=data, parsed_intent=parsed), parsed, command.model_dump(mode="json")

    if command.intent == "help.explain_block_reason":
        data = command.payload
        if command.warnings:
            return (
                response_builder.answer(
                    (
                        f"Je ne trouve aucune demande avec la reference {data.get('reference_code')}."
                        if data.get("reference_code")
                        else "Je ne trouve pas encore de transfert a analyser pour ce compte."
                    ),
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        return (
            response_builder.answer(
                str(data.get("explanation") or "Aucune explication disponible."),
                data=data,
                parsed_intent=parsed,
            ),
            parsed,
            command.model_dump(mode="json"),
        )

    if command.intent == "transfer.create":
        if command.missing_fields:
            missing_message = (
                _beneficiary_selection_message(command.payload)
                if "beneficiary_selection" in command.missing_fields
                else _missing_fields_message(command.missing_fields)
            )
            await save_conversation_state(
                db,
                session_id=session_id,
                current_user=current_user,
                current_intent=command.intent,
                collected_slots=command.payload,
            )
            return (
                response_builder.missing_information(
                    _prepend_warnings(missing_message, command.warnings),
                    missing_fields=command.missing_fields,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )

        pending = await create_pending_action(
            db,
            current_user=current_user,
            session_id=session_id,
            intent_code=command.intent,
            action_code=command.action_code,
            payload=command.payload,
        )
        await clear_conversation_state(db, session_id, current_user.user_id)
        return (
            response_builder.confirmation_required(
                _prepend_warnings(_build_transfer_confirmation(command.payload), command.warnings),
                pending_action_id=pending.id,
                parsed_intent=parsed,
            ),
            parsed,
            command.model_dump(mode="json"),
        )

    if command.intent == "beneficiary.add":
        if command.missing_fields:
            await save_conversation_state(
                db,
                session_id=session_id,
                current_user=current_user,
                current_intent=command.intent,
                collected_slots=command.payload,
            )
            return (
                response_builder.missing_information(
                    _missing_fields_message(command.missing_fields),
                    missing_fields=command.missing_fields,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )

        pending = await create_pending_action(
            db,
            current_user=current_user,
            session_id=session_id,
            intent_code=command.intent,
            action_code=command.action_code,
            payload=command.payload,
        )
        await clear_conversation_state(db, session_id, current_user.user_id)
        return (
            response_builder.confirmation_required(
                _build_beneficiary_confirmation(command.payload),
                pending_action_id=pending.id,
                parsed_intent=parsed,
            ),
            parsed,
                command.model_dump(mode="json"),
            )

    if command.intent == "beneficiary.list":
        data = command.payload
        items = list(data.get("items") or [])
        if not items:
            return (
                response_builder.answer(
                    "Je ne vois pas encore de beneficiaire enregistre pour ce compte.",
                    data=data,
                    parsed_intent=parsed,
                ),
                parsed,
                command.model_dump(mode="json"),
            )
        preview = []
        for item in items[:3]:
            preview.append(
                f"{item.get('recipient_name')} via {item.get('partner_name')} au {item.get('recipient_phone')}"
            )
        message_out = f"J'ai trouve {data.get('count')} beneficiaire(s): {' ; '.join(preview)}."
        return (
            response_builder.answer(message_out, data=data, parsed_intent=parsed),
            parsed,
            command.model_dump(mode="json"),
        )

    return response_builder.refused("Je n'ai pas compris la demande pour ce MVP IA.", parsed_intent=parsed), parsed, command.model_dump(mode="json")
