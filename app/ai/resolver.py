from difflib import SequenceMatcher
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.agent_onboarding_chat.catalog import GUIDES, SCENARIOS
from app.ai.metadata_service import RuntimeMetadata
from app.ai.schemas import ParsedIntent, ResolvedCommand, WalletBalanceData
from app.models.credit_lines import CreditLines
from app.models.escrow_order import EscrowOrder
from app.models.external_beneficiaries import ExternalBeneficiaries
from app.models.external_transfers import ExternalTransfers
from app.models.kyc_verifications import KycVerifications
from app.models.p2p_dispute import P2PDispute
from app.models.p2p_offer import P2POffer
from app.models.p2p_trade import P2PTrade
from app.models.p2p_trade_history import P2PTradeStatusHistory
from app.models.tontinemembers import TontineMembers
from app.models.transactions import Transactions
from app.models.users import Users
from app.models.wallet_cash_requests import WalletCashRequestStatus, WalletCashRequests
from app.models.wallets import Wallets

AML_ALERT_THRESHOLD = 50
AML_MANUAL_REVIEW_THRESHOLD = 60
AML_AUTO_FREEZE_THRESHOLD = 80
AML_REASON_LABELS = {
    "AML_KYC_UNVERIFIED": "le niveau KYC du compte est non verifie",
    "AML_KYC_BASIC": "le compte est encore sur un niveau KYC basique",
    "AML_NEW_ACCOUNT_LT_7D": "le compte est tres recent",
    "AML_NEW_ACCOUNT_LT_30D": "le compte est recent",
    "AML_AMOUNT_GE_1000000": "le montant est tres eleve",
    "AML_AMOUNT_GE_300000": "le montant est eleve",
    "AML_EXTERNAL_CHANNEL": "l'operation passe par le canal transfert externe",
    "AML_SCORE_ALERT": "le score AML a declenche une alerte",
    "AML_SCORE_MANUAL_REVIEW": "le score AML impose une revue manuelle",
    "AML_SCORE_CRITICAL": "le score AML est critique",
}


def _wallet_priority_stmt(user_id: UUID):
    return (
        select(Wallets)
        .where(Wallets.user_id == user_id)
        .order_by(Wallets.wallet_id.asc())
        .limit(1)
    )


async def _load_wallet_balance(db: AsyncSession, current_user: Users) -> WalletBalanceData:
    wallet = await db.scalar(_wallet_priority_stmt(current_user.user_id))
    if wallet is None:
        wallet = Wallets(
            user_id=current_user.user_id,
            type="consumer",
            currency_code="EUR",
            available=Decimal("0"),
            pending=Decimal("0"),
        )
        db.add(wallet)
        await db.flush()

    credit_line = await db.scalar(
        select(CreditLines)
        .where(
            CreditLines.user_id == current_user.user_id,
            CreditLines.deleted_at.is_(None),
            CreditLines.status == "active",
        )
        .order_by(CreditLines.created_at.desc())
    )
    if credit_line:
        credit_available = max(Decimal(credit_line.outstanding_amount or 0), Decimal("0"))
    else:
        credit_limit = Decimal(getattr(current_user, "credit_limit", 0) or 0)
        credit_used = Decimal(getattr(current_user, "credit_used", 0) or 0)
        credit_available = max(credit_limit - credit_used, Decimal("0"))

    return WalletBalanceData(
        wallet_available=Decimal(wallet.available or 0),
        wallet_currency=str(wallet.currency_code or "EUR"),
        credit_available=credit_available,
        bonus_balance=Decimal(wallet.bonus_balance or 0),
    )


def _describe_aml_reason(aml_score: Any, *, manual_review: bool) -> str:
    if aml_score is None:
        return "Un controle AML manuel est en cours."
    try:
        score = int(aml_score)
    except Exception:
        return f"Un controle AML manuel est en cours. Score enregistre: {aml_score}."

    if score >= AML_AUTO_FREEZE_THRESHOLD:
        return (
            f"Le score AML enregistre est {score}. C'est un niveau critique: "
            "le dossier demande une intervention conformite prioritaire."
        )
    if score >= AML_MANUAL_REVIEW_THRESHOLD:
        return (
            f"Le score AML enregistre est {score}. Il depasse le seuil de revue manuelle "
            f"({AML_MANUAL_REVIEW_THRESHOLD}) pour les transferts externes."
        )
    if manual_review or score >= AML_ALERT_THRESHOLD:
        return (
            f"Le score AML enregistre est {score}. Il a declenche une alerte de conformite "
            f"(seuil {AML_ALERT_THRESHOLD}) et le dossier reste en verification."
        )
    return f"Le score AML enregistre est {score}. Une verification de conformite reste associee a ce dossier."


def _describe_aml_reason_codes(reason_codes: list[str]) -> str | None:
    labels = [AML_REASON_LABELS.get(code) for code in reason_codes if AML_REASON_LABELS.get(code)]
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} et {labels[1]}"
    return f"{', '.join(labels[:-1])} et {labels[-1]}"


def _normalize_match_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_beneficiary_account(value: Any) -> str:
    return str(value or "").strip().lower()


def _score_beneficiary_match(query: str, candidate: str) -> float:
    query_norm = _normalize_match_text(query)
    candidate_norm = _normalize_match_text(candidate)
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        return 0.96
    return SequenceMatcher(None, query_norm, candidate_norm).ratio()


async def _load_beneficiary_candidates(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    saved_rows = (
        await db.execute(
            select(ExternalBeneficiaries)
            .where(
                ExternalBeneficiaries.user_id == user_id,
                ExternalBeneficiaries.is_active.is_(True),
            )
            .order_by(desc(ExternalBeneficiaries.updated_at), desc(ExternalBeneficiaries.created_at))
            .limit(20)
        )
    ).scalars().all()
    transfer_rows = (
        await db.execute(
            select(ExternalTransfers)
            .where(ExternalTransfers.user_id == user_id)
            .order_by(desc(ExternalTransfers.created_at))
            .limit(20)
        )
    ).scalars().all()

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in saved_rows:
        phone = str(row.recipient_phone or "").strip()
        account = _normalize_beneficiary_account(row.recipient_email)
        key = (
            _normalize_match_text(row.recipient_name),
            _normalize_match_text(row.partner_name),
            phone,
            account,
        )
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "recipient_name": str(row.recipient_name or "").strip(),
                "recipient_phone": phone,
                "account_ref": account or None,
                "partner_name": str(row.partner_name or "").strip(),
                "country_destination": str(row.country_destination or "").strip(),
                "source": "saved_beneficiary",
            }
        )

    for row in transfer_rows:
        metadata = dict(getattr(row, "metadata_", {}) or {})
        phone = str(row.recipient_phone or "").strip()
        account = _normalize_beneficiary_account(metadata.get("recipient_email"))
        key = (
            _normalize_match_text(row.recipient_name),
            _normalize_match_text(row.partner_name),
            phone,
            account,
        )
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "recipient_name": str(row.recipient_name or "").strip(),
                "recipient_phone": phone,
                "account_ref": account or None,
                "partner_name": str(row.partner_name or "").strip(),
                "country_destination": str(row.country_destination or "").strip(),
                "source": "transfer_history",
            }
        )
    return candidates


async def _resolve_transfer_beneficiary(
    db: AsyncSession,
    *,
    current_user: Users,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    recipient_name = str(payload.get("recipient_name") or "").strip()
    recipient_phone = str(payload.get("recipient_phone") or "").strip()
    partner_name = str(payload.get("partner_name") or "").strip()
    warnings: list[str] = []
    extra_missing_fields: list[str] = []
    if not recipient_name and not recipient_phone:
        return payload, warnings, extra_missing_fields

    candidates = await _load_beneficiary_candidates(db, current_user.user_id)
    if not candidates:
        return payload, warnings, extra_missing_fields

    exact_match = None
    exact_matches: list[dict[str, Any]] = []
    if recipient_phone:
        for item in candidates:
            if recipient_phone == str(item.get("recipient_phone") or "").strip():
                if not partner_name or _normalize_match_text(partner_name) == _normalize_match_text(item.get("partner_name")):
                    exact_matches.append(item)
        if len(exact_matches) == 1:
            exact_match = exact_matches[0]
        elif len(exact_matches) > 1:
            resolved_payload = dict(payload)
            resolved_payload["beneficiary_candidates"] = [
                {
                    "recipient_name": str(item.get("recipient_name") or "").strip() or None,
                    "recipient_phone": str(item.get("recipient_phone") or "").strip() or None,
                    "account_ref": str(item.get("account_ref") or "").strip() or None,
                    "partner_name": str(item.get("partner_name") or "").strip() or None,
                    "country_destination": str(item.get("country_destination") or "").strip() or None,
                    "source": str(item.get("source") or "").strip() or None,
                    "score": 1.0,
                }
                for item in exact_matches[:3]
            ]
            extra_missing_fields.append("beneficiary_selection")
            warnings.append("Plusieurs beneficiaires ont le meme numero ou le meme contexte. Je ne selectionne pas automatiquement.")
            return resolved_payload, warnings, extra_missing_fields

    best = exact_match
    best_score = 1.0 if exact_match else 0.0
    ambiguous_candidates: list[dict[str, Any]] = []
    if best is None and recipient_name:
        for item in candidates:
            score = _score_beneficiary_match(recipient_name, str(item.get("recipient_name") or ""))
            if partner_name and _normalize_match_text(partner_name) == _normalize_match_text(item.get("partner_name")):
                score += 0.1
            if score > best_score:
                best = item
                best_score = score
            if score >= 0.72:
                ambiguous_candidates.append(
                    {
                        "recipient_name": str(item.get("recipient_name") or "").strip(),
                        "recipient_phone": str(item.get("recipient_phone") or "").strip() or None,
                        "partner_name": str(item.get("partner_name") or "").strip() or None,
                        "country_destination": str(item.get("country_destination") or "").strip() or None,
                        "source": str(item.get("source") or "").strip() or None,
                        "score": round(score, 3),
                    }
                )

    if best is None or best_score < 0.72:
        return payload, warnings, extra_missing_fields

    if not exact_match and len(ambiguous_candidates) > 1:
        sorted_candidates = sorted(
            ambiguous_candidates,
            key=lambda item: (float(item.get("score") or 0), str(item.get("partner_name") or "")),
            reverse=True,
        )[:3]
        if float(sorted_candidates[0].get("score") or 0) - float(sorted_candidates[1].get("score") or 0) < 0.08:
            resolved_payload = dict(payload)
            resolved_payload["beneficiary_candidates"] = sorted_candidates
            extra_missing_fields.append("beneficiary_selection")
            warnings.append("Plusieurs beneficiaires correspondent. Je ne selectionne pas automatiquement.")
            return resolved_payload, warnings, extra_missing_fields

    resolved_payload = dict(payload)
    matched_name = str(best.get("recipient_name") or "").strip()
    if not resolved_payload.get("recipient_name") and matched_name:
        resolved_payload["recipient_name"] = matched_name
    if not resolved_payload.get("recipient_phone") and best.get("recipient_phone"):
        resolved_payload["recipient_phone"] = best["recipient_phone"]
    if not resolved_payload.get("account_ref") and best.get("account_ref"):
        resolved_payload["account_ref"] = best["account_ref"]
    if not resolved_payload.get("partner_name") and best.get("partner_name"):
        resolved_payload["partner_name"] = best["partner_name"]
    if not resolved_payload.get("country_destination") and best.get("country_destination"):
        resolved_payload["country_destination"] = best["country_destination"]
    resolved_payload["beneficiary_match_source"] = best.get("source")
    resolved_payload["beneficiary_match_name"] = matched_name or None
    warnings.append(
        f"Beneficiaire reconnu via {best.get('source')}: {matched_name or 'beneficiaire connu'}."
    )
    return resolved_payload, warnings, extra_missing_fields


async def resolve_intent(
    db: AsyncSession,
    current_user: Users,
    parsed: ParsedIntent,
    metadata: RuntimeMetadata,
) -> ResolvedCommand:
    if parsed.intent == "agent_onboarding.scenario":
        scenario_code = str(parsed.entities.get("scenario") or "").strip()
        scenario = SCENARIOS.get(scenario_code)
        if scenario is None:
            return ResolvedCommand(
                intent="agent_onboarding.scenario",
                action_code="agent_onboarding.get_scenario",
                payload={"scenario": scenario_code},
                requires_confirmation=False,
                warnings=["Scenario onboarding non reconnu."],
            )
        return ResolvedCommand(
            intent="agent_onboarding.scenario",
            action_code="agent_onboarding.get_scenario",
            payload={
                "scenario": scenario_code,
                "message": scenario.get("message"),
                "assumptions": list(scenario.get("assumptions", [])),
                "summary": dict(scenario.get("summary", {})),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "agent_onboarding.guide":
        guide_topic = str(parsed.entities.get("guide_topic") or "").strip()
        guide = GUIDES.get(guide_topic)
        if guide is None:
            return ResolvedCommand(
                intent="agent_onboarding.guide",
                action_code="agent_onboarding.get_guide",
                payload={"guide_topic": guide_topic},
                requires_confirmation=False,
                warnings=["Guide onboarding non reconnu."],
            )
        return ResolvedCommand(
            intent="agent_onboarding.guide",
            action_code="agent_onboarding.get_guide",
            payload={
                "guide_topic": guide_topic,
                "message": guide.get("message"),
                "assumptions": list(guide.get("assumptions", [])),
                "summary": dict(guide.get("summary", {})),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "credit.capacity":
        balance = await _load_wallet_balance(db, current_user)
        return ResolvedCommand(
            intent="credit.capacity",
            action_code="credit.get_capacity",
            payload={
                "wallet_available": str(balance.wallet_available),
                "wallet_currency": balance.wallet_currency,
                "credit_available": str(balance.credit_available),
                "bonus_balance": str(balance.bonus_balance or 0),
                "total_capacity": str(balance.wallet_available + balance.credit_available),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "cash.capacity":
        balance = await _load_wallet_balance(db, current_user)
        pending_cash_requests = await db.scalar(
            select(func.count())
            .select_from(WalletCashRequests)
            .where(
                WalletCashRequests.user_id == current_user.user_id,
                cast(WalletCashRequests.status, String) == WalletCashRequestStatus.PENDING.value,
            )
        )
        return ResolvedCommand(
            intent="cash.capacity",
            action_code="cash.get_capacity",
            payload={
                "wallet_available": str(balance.wallet_available),
                "wallet_currency": balance.wallet_currency,
                "credit_available": str(balance.credit_available),
                "pending_cash_requests": int(pending_cash_requests or 0),
            },
            requires_confirmation=False,
        )

    if parsed.intent in {"cash.deposit", "cash.withdraw"}:
        balance = await _load_wallet_balance(db, current_user)
        payload = {
            "amount": str(parsed.entities.get("amount")) if parsed.entities.get("amount") is not None else None,
            "currency": parsed.entities.get("currency") or balance.wallet_currency,
            "mobile_number": parsed.entities.get("mobile_number"),
            "provider_name": parsed.entities.get("provider_name"),
            "note": parsed.entities.get("note"),
            "wallet_currency": balance.wallet_currency,
        }
        missing_fields = []
        if payload["amount"] in (None, "", "0"):
            missing_fields.append("amount")
        if parsed.intent == "cash.withdraw":
            if not payload.get("provider_name"):
                missing_fields.append("provider_name")
            if not payload.get("mobile_number"):
                missing_fields.append("mobile_number")
        return ResolvedCommand(
            intent=parsed.intent,
            action_code="cash.create_deposit_request" if parsed.intent == "cash.deposit" else "cash.create_withdraw_request",
            payload=payload,
            requires_confirmation=not missing_fields,
            missing_fields=missing_fields,
        )

    if parsed.intent == "cash.request_status":
        latest_request = await db.scalar(
            select(WalletCashRequests)
            .where(WalletCashRequests.user_id == current_user.user_id)
            .order_by(desc(WalletCashRequests.created_at))
        )
        if latest_request is None:
            return ResolvedCommand(
                intent="cash.request_status",
                action_code="cash.get_request_status",
                payload={},
                requires_confirmation=False,
                warnings=["Aucune demande cash recente n'a ete trouvee."],
            )
        request_type = str(getattr(latest_request.type, "value", latest_request.type) or "").lower()
        request_status = str(getattr(latest_request.status, "value", latest_request.status) or "").lower()
        reference_code = (getattr(latest_request, "metadata_", {}) or {}).get("reference_code")
        human_type = "depot" if request_type == "deposit" else "retrait" if request_type == "withdraw" else request_type
        return ResolvedCommand(
            intent="cash.request_status",
            action_code="cash.get_request_status",
            payload={
                "request_type": human_type,
                "request_status": request_status,
                "amount": str(getattr(latest_request, "amount", "") or ""),
                "currency": str(getattr(latest_request, "currency_code", "") or ""),
                "reference_code": str(reference_code or "") or None,
            },
            requires_confirmation=False,
        )

    if parsed.intent == "wallet.block_reason":
        latest_cash_request = await db.scalar(
            select(WalletCashRequests)
            .where(WalletCashRequests.user_id == current_user.user_id)
            .order_by(desc(WalletCashRequests.created_at))
        )
        latest_external_transfer = await db.scalar(
            select(ExternalTransfers)
            .where(ExternalTransfers.user_id == current_user.user_id)
            .order_by(desc(ExternalTransfers.created_at))
        )
        reasons: list[str] = []
        account_status = str(getattr(current_user, "status", "") or "").lower()
        if account_status in {"frozen", "suspended"}:
            reasons.append("Le statut du compte bloque actuellement l'operation.")
        if Decimal(getattr(current_user, "used_daily", 0) or 0) >= Decimal(getattr(current_user, "daily_limit", 0) or 0):
            reasons.append("La limite journaliere est atteinte.")
        if Decimal(getattr(current_user, "used_monthly", 0) or 0) >= Decimal(getattr(current_user, "monthly_limit", 0) or 0):
            reasons.append("La limite mensuelle est atteinte.")
        if latest_cash_request and str(getattr(latest_cash_request.status, "value", latest_cash_request.status) or "").lower() == "pending":
            reasons.append("Une demande cash recente est encore en attente de traitement.")
        if latest_external_transfer and str(getattr(latest_external_transfer, "status", "") or "").lower() in {"pending", "initiated"}:
            reasons.append("Un transfert recent est encore en cours de revue ou d'execution.")
        if not reasons:
            reasons.append("Le blocage probable vient du solde, d'une verification manuelle ou d'une contrainte contextuelle.")
        return ResolvedCommand(
            intent="wallet.block_reason",
            action_code="wallet.explain_block_reason",
            payload={
                "account_status": str(getattr(current_user, "status", "") or ""),
                "kyc_status": str(getattr(current_user, "kyc_status", "") or ""),
                "daily_limit": str(getattr(current_user, "daily_limit", 0) or 0),
                "used_daily": str(getattr(current_user, "used_daily", 0) or 0),
                "monthly_limit": str(getattr(current_user, "monthly_limit", 0) or 0),
                "used_monthly": str(getattr(current_user, "used_monthly", 0) or 0),
                "reasons": reasons,
                "explanation": " ".join(reasons),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "credit.simulate_capacity":
        balance = await _load_wallet_balance(db, current_user)
        amount_raw = parsed.entities.get("amount")
        currency = str(parsed.entities.get("currency") or balance.wallet_currency or "EUR").upper()
        try:
            amount = Decimal(str(amount_raw)) if amount_raw is not None else None
        except Exception:
            amount = None
        return ResolvedCommand(
            intent="credit.simulate_capacity",
            action_code="credit.simulate_capacity",
            payload={
                "amount": str(amount) if amount is not None else None,
                "currency": currency,
                "wallet_available": str(balance.wallet_available),
                "wallet_currency": balance.wallet_currency,
                "credit_available": str(balance.credit_available),
                "bonus_balance": str(balance.bonus_balance or 0),
            },
            requires_confirmation=False,
            missing_fields=[] if amount is not None else ["amount"],
        )

    if parsed.intent == "credit.pending_reason":
        reference_code = parsed.entities.get("reference_code")
        if reference_code:
            transfer = await db.scalar(
                select(ExternalTransfers)
                .where(
                    ExternalTransfers.user_id == current_user.user_id,
                    ExternalTransfers.reference_code == reference_code,
                )
                .order_by(desc(ExternalTransfers.created_at))
            )
        else:
            transfer = await db.scalar(
                select(ExternalTransfers)
                .where(ExternalTransfers.user_id == current_user.user_id)
                .order_by(desc(ExternalTransfers.created_at))
            )
        if transfer is None:
            return ResolvedCommand(
                intent="credit.pending_reason",
                action_code="credit.get_pending_reason",
                payload={"reference_code": reference_code},
                requires_confirmation=False,
                warnings=["Aucun transfert en attente correspondant n'a ete trouve."],
            )

        metadata_payload = dict(getattr(transfer, "metadata_", {}) or {})
        review_reasons = [str(item) for item in (metadata_payload.get("review_reasons") or [])]
        aml_reason_codes = [str(item) for item in (metadata_payload.get("aml_reason_codes") or [])]
        shortfall_amount = str(metadata_payload.get("required_credit_topup") or "").strip()
        aml_score = metadata_payload.get("aml_risk_score")
        aml_manual_review = bool(metadata_payload.get("aml_manual_review_required"))

        if "insufficient_funds" in review_reasons and "aml" in review_reasons:
            explanation = "Le transfert attend une verification de fonds et un controle AML."
        elif "insufficient_funds" in review_reasons:
            explanation = (
                f"Le transfert attend encore une couverture de fonds de {shortfall_amount}."
                if shortfall_amount
                else "Le transfert attend une couverture de fonds suffisante."
            )
        elif "aml" in review_reasons or aml_manual_review:
            explanation = _describe_aml_reason(aml_score, manual_review=aml_manual_review)
            aml_reason_detail = _describe_aml_reason_codes(aml_reason_codes)
            if aml_reason_detail:
                explanation = f"{explanation} Les principaux signaux releves sont: {aml_reason_detail}."
        else:
            explanation = "Le transfert attend encore une validation manuelle."

        return ResolvedCommand(
            intent="credit.pending_reason",
            action_code="credit.get_pending_reason",
            payload={
                "reference_code": transfer.reference_code,
                "review_reasons": review_reasons,
                "aml_reason_codes": aml_reason_codes,
                "required_credit_topup": shortfall_amount or None,
                "aml_risk_score": aml_score,
                "aml_manual_review_required": aml_manual_review,
                "explanation": explanation,
            },
            requires_confirmation=False,
        )

    if parsed.intent == "kyc.status":
        verification = None
        try:
            verification = await db.scalar(
                select(KycVerifications)
                .where(KycVerifications.user_id == current_user.user_id)
                .order_by(KycVerifications.created_at.desc())
            )
        except ProgrammingError as exc:
            if "kyc_verifications" not in str(getattr(exc, "orig", exc)).lower():
                raise
            await db.rollback()

        missing_docs: list[str] = []
        if verification:
            required_docs = list(getattr(verification, "required_docs", []) or [])
            collected_docs = set(getattr(verification, "collected_docs", []) or [])
            missing_docs = [doc for doc in required_docs if doc not in collected_docs]
        if not missing_docs:
            if not getattr(current_user, "kyc_document_front_url", None):
                missing_docs.append("id_front")
            if not getattr(current_user, "selfie_url", None):
                missing_docs.append("selfie_liveness")

        return ResolvedCommand(
            intent="kyc.status",
            action_code="kyc.get_status",
            payload={
                "kyc_status": str(getattr(current_user, "kyc_status", "") or "unknown"),
                "kyc_tier": int(getattr(current_user, "kyc_tier", 0) or 0),
                "daily_limit": str(getattr(current_user, "daily_limit", 0) or 0),
                "monthly_limit": str(getattr(current_user, "monthly_limit", 0) or 0),
                "used_daily": str(getattr(current_user, "used_daily", 0) or 0),
                "used_monthly": str(getattr(current_user, "used_monthly", 0) or 0),
                "verification_status": str(getattr(verification, "status", "") or ""),
                "verification_tier": str(getattr(verification, "tier", "") or ""),
                "missing_docs": missing_docs,
                "kyc_view": parsed.entities.get("kyc_view"),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "wallet.balance":
        balance = await _load_wallet_balance(db, current_user)
        tontines_count = await db.scalar(
            select(func.count()).select_from(TontineMembers).where(TontineMembers.user_id == current_user.user_id)
        )
        return ResolvedCommand(
            intent="wallet.balance",
            action_code="wallet.get_balance",
            payload={
                "wallet_available": str(balance.wallet_available),
                "wallet_currency": balance.wallet_currency,
                "credit_available": str(balance.credit_available),
                "bonus_balance": str(balance.bonus_balance or 0),
                "tontines_count": int(tontines_count or 0),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "wallet.limits":
        balance = await _load_wallet_balance(db, current_user)
        return ResolvedCommand(
            intent="wallet.limits",
            action_code="wallet.get_limits",
            payload={
                "wallet_currency": balance.wallet_currency,
                "daily_limit": str(getattr(current_user, "daily_limit", 0) or 0),
                "used_daily": str(getattr(current_user, "used_daily", 0) or 0),
                "monthly_limit": str(getattr(current_user, "monthly_limit", 0) or 0),
                "used_monthly": str(getattr(current_user, "used_monthly", 0) or 0),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "escrow.status":
        order_id = parsed.entities.get("order_id")
        if order_id:
            order = await db.scalar(
                select(EscrowOrder)
                .where(
                    EscrowOrder.user_id == current_user.user_id,
                    EscrowOrder.id == order_id,
                )
                .order_by(desc(EscrowOrder.created_at))
            )
        else:
            order = await db.scalar(
                select(EscrowOrder)
                .where(EscrowOrder.user_id == current_user.user_id)
                .order_by(desc(EscrowOrder.created_at))
            )
        if order is None:
            return ResolvedCommand(
                intent="escrow.status",
                action_code="escrow.get_status",
                payload={"order_id": order_id},
                requires_confirmation=False,
                warnings=["Aucun escrow correspondant n'a ete trouve."],
            )
        status_value = str(getattr(getattr(order, "status", None), "value", getattr(order, "status", "")) or "")
        network_value = str(getattr(getattr(order, "deposit_network", None), "value", getattr(order, "deposit_network", "")) or "")
        return ResolvedCommand(
            intent="escrow.status",
            action_code="escrow.get_status",
            payload={
                "order_id": str(order.id),
                "status": status_value,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "network": network_value,
                "deposit_address": str(getattr(order, "deposit_address", "") or ""),
                "usdc_expected": str(getattr(order, "usdc_expected", "") or ""),
                "bif_target": str(getattr(order, "bif_target", "") or ""),
                "payout_provider": str(getattr(order, "payout_provider", "") or ""),
                "payout_account": str(getattr(order, "payout_account_number", "") or ""),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "p2p.offers_summary":
        offers = (
            await db.execute(
                select(P2POffer)
                .where(
                    P2POffer.user_id == current_user.user_id,
                    P2POffer.is_active.is_(True),
                )
                .order_by(desc(P2POffer.created_at))
            )
        ).scalars().all()
        latest_offer = offers[0] if offers else None
        return ResolvedCommand(
            intent="p2p.offers_summary",
            action_code="p2p.get_offers_summary",
            payload={
                "open_offers_count": len(offers),
                "latest_offer_side": str(getattr(getattr(latest_offer, "side", None), "value", getattr(latest_offer, "side", "")) or ""),
                "latest_offer_token": str(getattr(getattr(latest_offer, "token", None), "value", getattr(latest_offer, "token", "")) or ""),
                "latest_offer_available": str(getattr(latest_offer, "available_amount", "") or ""),
                "latest_offer_payment_method": str(getattr(getattr(latest_offer, "payment_method", None), "value", getattr(latest_offer, "payment_method", "")) or ""),
            },
            requires_confirmation=False,
        )

    if parsed.intent == "p2p.trade_status":
        trade_id = parsed.entities.get("trade_id")
        if trade_id:
            trade = await db.scalar(
                select(P2PTrade).where(
                    P2PTrade.trade_id == trade_id,
                    (P2PTrade.buyer_id == current_user.user_id) | (P2PTrade.seller_id == current_user.user_id),
                )
            )
        else:
            trade = await db.scalar(
                select(P2PTrade)
                .where((P2PTrade.buyer_id == current_user.user_id) | (P2PTrade.seller_id == current_user.user_id))
                .order_by(desc(P2PTrade.created_at))
            )
        if trade is None:
            return ResolvedCommand(
                intent="p2p.trade_status",
                action_code="p2p.get_trade_status",
                payload={"trade_id": trade_id},
                requires_confirmation=False,
                warnings=["Aucun trade P2P correspondant n'a ete trouve."],
            )
        dispute = await db.scalar(
            select(P2PDispute).where(P2PDispute.trade_id == trade.trade_id).order_by(desc(P2PDispute.created_at))
        )
        last_history = await db.scalar(
            select(P2PTradeStatusHistory)
            .where(P2PTradeStatusHistory.trade_id == trade.trade_id)
            .order_by(desc(P2PTradeStatusHistory.created_at))
        )
        trade_status = str(getattr(getattr(trade, "status", None), "value", getattr(trade, "status", "")) or "")
        next_step = {
            "CREATED": "Le trade vient d'etre cree. Attendez l'allocation escrow ou l'etape crypto.",
            "AWAITING_CRYPTO": "Le vendeur doit encore verrouiller ou envoyer la crypto dans l'escrow.",
            "CRYPTO_LOCKED": "La crypto est verrouillee. L'acheteur peut maintenant envoyer le paiement fiat.",
            "AWAITING_FIAT": "Le trade attend le paiement fiat de l'acheteur.",
            "FIAT_SENT": "Le vendeur doit verifier puis confirmer la reception du fiat.",
            "FIAT_CONFIRMED": "La confirmation fiat est faite. Le trade va vers la liberation.",
            "RELEASED": "Le trade est termine.",
            "DISPUTED": "Le trade est en litige et attend une resolution.",
        }.get(str(trade_status).upper(), "Verifier la timeline du trade pour connaitre l'etape suivante.")
        return ResolvedCommand(
            intent="p2p.trade_status",
            action_code="p2p.get_trade_status",
            payload={
                "trade_id": str(trade.trade_id),
                "trade_status": trade_status,
                "token_amount": str(getattr(trade, "token_amount", "") or ""),
                "token": str(getattr(getattr(trade, "token", None), "value", getattr(trade, "token", "")) or ""),
                "bif_amount": str(getattr(trade, "bif_amount", "") or ""),
                "payment_method": str(getattr(getattr(trade, "payment_method", None), "value", getattr(trade, "payment_method", "")) or ""),
                "created_at": trade.created_at.isoformat() if getattr(trade, "created_at", None) else None,
                "dispute_status": str(getattr(getattr(dispute, "status", None), "value", getattr(dispute, "status", "")) or ""),
                "last_note": str(getattr(last_history, "note", "") or "") or None,
                "p2p_view": parsed.entities.get("p2p_view"),
                "next_step": next_step,
            },
            requires_confirmation=False,
        )

    if parsed.intent == "transfer.status":
        reference_code = parsed.entities.get("reference_code")
        if reference_code:
            transfer = await db.scalar(
                select(ExternalTransfers)
                .where(
                    ExternalTransfers.user_id == current_user.user_id,
                    ExternalTransfers.reference_code == reference_code,
                )
                .order_by(desc(ExternalTransfers.created_at))
            )
        else:
            transfer = await db.scalar(
                select(ExternalTransfers)
                .where(ExternalTransfers.user_id == current_user.user_id)
                .order_by(desc(ExternalTransfers.created_at))
            )
        if transfer is None:
            return ResolvedCommand(
                intent="transfer.status",
                action_code="transfer.get_status",
                payload={"reference_code": reference_code},
                requires_confirmation=False,
                warnings=["Aucun transfert correspondant n'a ete trouve."],
            )
        linked_tx = await db.scalar(
            select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
        )
        return ResolvedCommand(
            intent="transfer.status",
            action_code="transfer.get_status",
            payload={
                "transfer_id": str(transfer.transfer_id),
                "reference_code": transfer.reference_code,
                "transfer_status": str(transfer.status or ""),
                "transaction_status": str(getattr(linked_tx, "status", "") or "") or None,
                "recipient_name": transfer.recipient_name,
                "recipient_phone": transfer.recipient_phone,
                "partner_name": transfer.partner_name,
                "country_destination": transfer.country_destination,
                "amount": str(transfer.amount or 0),
                "currency": str(transfer.currency or ""),
                "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
            },
            requires_confirmation=False,
        )

    if parsed.intent == "help.explain_block_reason":
        reference_code = parsed.entities.get("reference_code")
        if reference_code:
            transfer = await db.scalar(
                select(ExternalTransfers)
                .where(
                    ExternalTransfers.user_id == current_user.user_id,
                    ExternalTransfers.reference_code == reference_code,
                )
                .order_by(desc(ExternalTransfers.created_at))
            )
        else:
            transfer = await db.scalar(
                select(ExternalTransfers)
                .where(ExternalTransfers.user_id == current_user.user_id)
                .order_by(desc(ExternalTransfers.created_at))
            )
        if transfer is None:
            return ResolvedCommand(
                intent="help.explain_block_reason",
                action_code="transfer.explain_block_reason",
                payload={"reference_code": reference_code},
                requires_confirmation=False,
                warnings=["Aucun transfert correspondant n'a ete trouve."],
            )

        metadata_payload = dict(getattr(transfer, "metadata_", {}) or {})
        review_reasons = [str(item) for item in (metadata_payload.get("review_reasons") or [])]
        aml_reason_codes = [str(item) for item in (metadata_payload.get("aml_reason_codes") or [])]
        linked_tx = await db.scalar(
            select(Transactions).where(Transactions.related_entity_id == transfer.transfer_id)
        )
        normalized_status = str(getattr(transfer, "status", "") or "").lower()
        shortfall_amount = str(metadata_payload.get("required_credit_topup") or "").strip()
        aml_score = metadata_payload.get("aml_risk_score")
        tx_status = str(getattr(linked_tx, "status", "") or "").lower()

        aml_manual_review = bool(metadata_payload.get("aml_manual_review_required"))
        aml_reason_detail = _describe_aml_reason_codes(aml_reason_codes)
        if "insufficient_funds" in review_reasons and "aml" in review_reasons:
            if shortfall_amount:
                explanation = (
                    f"Le transfert est en attente pour deux raisons: il manque encore {shortfall_amount} "
                    f"pour le financer completement et {_describe_aml_reason(aml_score, manual_review=aml_manual_review).lower()}"
                )
            else:
                explanation = (
                    "Le transfert est en attente pour deux raisons: financement insuffisant et "
                    f"{_describe_aml_reason(aml_score, manual_review=aml_manual_review).lower()}"
                )
            if aml_reason_detail:
                explanation = f"{explanation} Les principaux signaux releves sont: {aml_reason_detail}."
        elif "insufficient_funds" in review_reasons:
            if shortfall_amount:
                explanation = f"Le transfert est en attente car il manque encore {shortfall_amount} pour couvrir l'operation."
            else:
                explanation = "Le transfert est en attente car la couverture disponible etait insuffisante."
        elif "aml" in review_reasons or aml_manual_review:
            explanation = _describe_aml_reason(aml_score, manual_review=aml_manual_review)
            if aml_reason_detail:
                explanation = f"{explanation} Les principaux signaux releves sont: {aml_reason_detail}."
        elif metadata_payload.get("funding_pending"):
            if shortfall_amount:
                explanation = f"Le transfert est en attente d'un financement complementaire de {shortfall_amount} avant validation."
            else:
                explanation = "Le transfert est en attente d'un financement complementaire avant validation."
        elif normalized_status == "approved" and tx_status in {"pending", "initiated"}:
            explanation = "Le transfert est deja valide cote controle, mais l'execution finale par le partenaire est encore en cours."
        elif normalized_status == "completed":
            explanation = "Le transfert n'est plus bloque. Il est deja marque comme execute."
        elif normalized_status in {"pending", "initiated"}:
            explanation = "Le transfert est encore en revue manuelle. Aucune raison plus precise n'est enregistree."
        elif normalized_status == "approved":
            explanation = "Le transfert est valide, mais il attend encore l'execution finale par l'agent ou le partenaire."
        else:
            explanation = f"Le transfert n'est pas bloque. Son statut actuel est {normalized_status or 'inconnu'}."

        return ResolvedCommand(
            intent="help.explain_block_reason",
            action_code="transfer.explain_block_reason",
            payload={
                "transfer_id": str(transfer.transfer_id),
                "reference_code": transfer.reference_code,
                "transfer_status": str(transfer.status or ""),
                "transaction_status": str(getattr(linked_tx, "status", "") or "") or None,
                "review_reasons": review_reasons,
                "aml_reason_codes": aml_reason_codes,
                "funding_pending": bool(metadata_payload.get("funding_pending")),
                "aml_manual_review_required": aml_manual_review,
                "required_credit_topup": shortfall_amount or None,
                "aml_risk_score": aml_score,
                "aml_thresholds": {
                    "alert": AML_ALERT_THRESHOLD,
                    "manual_review_external": AML_MANUAL_REVIEW_THRESHOLD,
                    "auto_freeze": AML_AUTO_FREEZE_THRESHOLD,
                },
                "explanation": explanation,
            },
            requires_confirmation=False,
        )

    if parsed.intent == "beneficiary.add":
        payload: dict[str, Any] = {
            "recipient_name": parsed.entities.get("recipient_name"),
            "recipient_phone": parsed.entities.get("recipient_phone"),
            "account_ref": parsed.entities.get("account_ref") or parsed.entities.get("recipient_email"),
            "partner_name": parsed.entities.get("partner_name"),
            "country_destination": parsed.entities.get("country_destination"),
        }
        missing_fields = parsed.missing_fields or []
        action = metadata.actions.get("beneficiary.add", {}).get("action_code", "beneficiary_service.save_external_beneficiary")
        return ResolvedCommand(
            intent="beneficiary.add",
            action_code=action,
            payload=payload,
            requires_confirmation=not missing_fields,
            missing_fields=missing_fields,
        )

    if parsed.intent == "beneficiary.list":
        candidates = await _load_beneficiary_candidates(db, current_user.user_id)
        items = [
            {
                "recipient_name": str(item.get("recipient_name") or "").strip() or None,
                "recipient_phone": str(item.get("recipient_phone") or "").strip() or None,
                "account_ref": str(item.get("account_ref") or "").strip() or None,
                "partner_name": str(item.get("partner_name") or "").strip() or None,
                "country_destination": str(item.get("country_destination") or "").strip() or None,
                "source": str(item.get("source") or "").strip() or None,
            }
            for item in candidates[:5]
        ]
        return ResolvedCommand(
            intent="beneficiary.list",
            action_code=metadata.actions.get("beneficiary.list", {}).get("action_code", "beneficiary_service.list_external_beneficiaries"),
            payload={
                "count": len(candidates),
                "items": items,
            },
            requires_confirmation=False,
        )

    if parsed.intent == "transfer.create":
        payload: dict[str, Any] = {
            "partner_name": parsed.entities.get("partner_name"),
            "country_destination": parsed.entities.get("country_destination"),
            "recipient_name": parsed.entities.get("recipient_name"),
            "recipient_phone": parsed.entities.get("recipient_phone"),
            "account_ref": parsed.entities.get("account_ref") or parsed.entities.get("recipient_email"),
            "amount": str(parsed.entities.get("amount")) if parsed.entities.get("amount") is not None else None,
            "origin_currency": parsed.entities.get("origin_currency"),
            "sender_name": parsed.entities.get("sender_name"),
        }
        payload, warnings, extra_missing_fields = await _resolve_transfer_beneficiary(
            db,
            current_user=current_user,
            payload=payload,
        )
        missing_fields = parsed.missing_fields or []
        if warnings:
            missing_fields = [
                slot.get("slot_name")
                for slot in metadata.slots.get("transfer.create", [])
                if slot.get("required") and payload.get(str(slot.get("slot_name"))) in (None, "", [])
            ]
        for item in extra_missing_fields:
            if item not in missing_fields:
                missing_fields.append(item)
        action = metadata.actions.get("transfer.create", {}).get("action_code", "transfer_service.create_external_transfer")
        return ResolvedCommand(
            intent="transfer.create",
            action_code=action,
            payload=payload,
            requires_confirmation=not missing_fields,
            missing_fields=missing_fields,
            warnings=warnings,
        )

    return ResolvedCommand(
        intent="unknown",
        action_code="unknown",
        payload={},
        requires_confirmation=False,
        missing_fields=[],
        warnings=["Intent non supporte pour le MVP IA"],
    )
