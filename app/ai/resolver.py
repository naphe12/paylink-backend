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
from app.services.external_transfer_capacity import effective_external_transfer_capacity

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


def _safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _build_limit_snapshot(*, current_user: Users, transfer_amount: Decimal) -> dict[str, Any]:
    daily_limit = _safe_decimal(getattr(current_user, "daily_limit", 0))
    used_daily = _safe_decimal(getattr(current_user, "used_daily", 0))
    monthly_limit = _safe_decimal(getattr(current_user, "monthly_limit", 0))
    used_monthly = _safe_decimal(getattr(current_user, "used_monthly", 0))

    daily_remaining = max(daily_limit - used_daily, Decimal("0"))
    monthly_remaining = max(monthly_limit - used_monthly, Decimal("0"))

    daily_exceeded = daily_limit > 0 and used_daily + transfer_amount > daily_limit
    monthly_exceeded = monthly_limit > 0 and used_monthly + transfer_amount > monthly_limit

    daily_overage = max((used_daily + transfer_amount) - daily_limit, Decimal("0")) if daily_exceeded else Decimal("0")
    monthly_overage = max((used_monthly + transfer_amount) - monthly_limit, Decimal("0")) if monthly_exceeded else Decimal("0")

    return {
        "transfer_amount": str(transfer_amount),
        "daily_limit": str(daily_limit),
        "used_daily": str(used_daily),
        "daily_remaining": str(daily_remaining),
        "daily_exceeded": daily_exceeded,
        "daily_overage": str(daily_overage),
        "monthly_limit": str(monthly_limit),
        "used_monthly": str(used_monthly),
        "monthly_remaining": str(monthly_remaining),
        "monthly_exceeded": monthly_exceeded,
        "monthly_overage": str(monthly_overage),
    }


def _describe_limit_block(limit_snapshot: dict[str, Any], currency: str) -> str | None:
    transfer_amount = _safe_decimal(limit_snapshot.get("transfer_amount"))
    details: list[str] = []

    if limit_snapshot.get("daily_exceeded"):
        details.append(
            "la limite journaliere serait depassee "
            f"(reste {limit_snapshot.get('daily_remaining')} {currency}, "
            f"depassement {limit_snapshot.get('daily_overage')} {currency} "
            f"pour un transfert de {transfer_amount} {currency})"
        )

    if limit_snapshot.get("monthly_exceeded"):
        details.append(
            "la limite mensuelle serait depassee "
            f"(reste {limit_snapshot.get('monthly_remaining')} {currency}, "
            f"depassement {limit_snapshot.get('monthly_overage')} {currency} "
            f"pour un transfert de {transfer_amount} {currency})"
        )

    if not details:
        return None
    if len(details) == 1:
        return details[0]
    return f"{details[0]} et {details[1]}"


def _wallet_block_next_step(*, account_status: str, reasons: list[str]) -> str:
    normalized_status = str(account_status or "").lower()
    joined = " ".join(str(item) for item in reasons)
    if normalized_status in {"frozen", "suspended"}:
        return "Verifier le statut du compte et faire intervenir le support ou la conformite pour lever le blocage."
    if "limite journaliere" in joined.lower():
        return "Attendre le renouvellement de la limite journaliere ou reduire le montant a un niveau compatible."
    if "limite mensuelle" in joined.lower():
        return "Attendre le renouvellement de la limite mensuelle ou reduire le montant pour rester dans la capacite restante."
    if "cash recente" in joined.lower():
        return "Attendre la fin de traitement de la demande cash en cours avant de relancer l'operation."
    if "transfert recent" in joined.lower():
        return "Attendre la resolution ou l'execution du transfert recent avant de relancer une nouvelle demande."
    return "Verifier le solde, les limites et les dossiers en attente avant de relancer l'operation."


def _wallet_dossier_type(*, account_status: str, reasons: list[str]) -> str:
    normalized_status = str(account_status or "").lower()
    joined = " ".join(str(item) for item in reasons).lower()
    if normalized_status in {"frozen", "suspended"}:
        return "account_review"
    if "demande cash recente" in joined:
        return "withdraw_blocked"
    if "transfert recent" in joined or "limite " in joined:
        return "send_blocked"
    return "standard"


def _wallet_who_must_act_now(*, account_status: str) -> str:
    normalized_status = str(account_status or "").lower()
    if normalized_status in {"frozen", "suspended"}:
        return "operations"
    return "client"


def _wallet_primary_blocker(reasons: list[str]) -> str | None:
    return str(reasons[0]) if reasons else None


def _transfer_next_step(*, status: str, review_reasons: list[str], metadata_payload: dict[str, Any], limit_block_detail: str | None) -> str:
    normalized_status = str(status or "").lower()
    if limit_block_detail:
        return "Ajuster le montant ou attendre le renouvellement des limites avant de relancer le transfert."
    if "insufficient_funds" in review_reasons or metadata_payload.get("funding_pending"):
        return "Approvisionner le wallet ou la couverture de credit, puis relancer ou attendre la reprise du dossier."
    if "aml" in review_reasons or metadata_payload.get("aml_manual_review_required"):
        return "Attendre la revue conformite ou fournir les justificatifs demandes si le support les reclame."
    if normalized_status in {"approved"}:
        return "Attendre l'execution finale du partenaire ou verifier le suivi agent."
    if normalized_status in {"pending", "initiated"}:
        return "Verifier les details du dossier et attendre la prochaine etape de validation."
    if normalized_status in {"completed", "succeeded"}:
        return "Le transfert est deja termine. Verifier simplement la reception cote beneficiaire."
    if normalized_status in {"failed", "cancelled", "reversed"}:
        return "Verifier la cause de l'echec puis recreer un nouveau transfert si necessaire."
    return "Verifier la reference du transfert et l'etat du dossier pour definir la prochaine action."


def _transfer_dossier_type(*, status: str, review_reasons: list[str], metadata_payload: dict[str, Any], limit_block_detail: str | None) -> str:
    normalized_status = str(status or "").lower()
    if limit_block_detail or "insufficient_funds" in review_reasons or metadata_payload.get("funding_pending"):
        return "funding"
    if "aml" in review_reasons or metadata_payload.get("aml_manual_review_required"):
        return "review"
    if normalized_status in {"failed", "cancelled", "reversed"}:
        return "failed"
    if normalized_status in {"completed", "succeeded"}:
        return "completed"
    return "standard"


def _transfer_who_must_act_now(*, status: str, review_reasons: list[str], metadata_payload: dict[str, Any], limit_block_detail: str | None) -> str:
    normalized_status = str(status or "").lower()
    if normalized_status in {"completed", "succeeded"}:
        return "none"
    if limit_block_detail or "insufficient_funds" in review_reasons or metadata_payload.get("funding_pending"):
        return "client"
    if "aml" in review_reasons or metadata_payload.get("aml_manual_review_required") or normalized_status in {"pending", "initiated", "approved"}:
        return "operations"
    return "client"


def _transfer_primary_blocker(*, review_reasons: list[str], metadata_payload: dict[str, Any], limit_block_detail: str | None) -> str | None:
    if limit_block_detail:
        return limit_block_detail
    if "insufficient_funds" in review_reasons or metadata_payload.get("funding_pending"):
        shortfall_amount = str(metadata_payload.get("required_credit_topup") or "").strip()
        if shortfall_amount:
            return f"Le dossier manque encore {shortfall_amount} pour etre finance."
        return "Le dossier n'est pas encore suffisamment finance."
    if "aml" in review_reasons or metadata_payload.get("aml_manual_review_required"):
        return "Le dossier attend une revue AML ou conformite."
    return None


def _escrow_pending_reasons(*, status: str, flags: list[str]) -> list[str]:
    reasons: list[str] = []
    normalized_status = str(status or "").upper()
    if normalized_status == "CREATED":
        reasons.append("Le depot USDC n'a pas encore ete detecte ou confirme.")
    elif normalized_status == "FUNDED":
        reasons.append("Le depot est recu mais la conversion ou le swap n'est pas encore finalise.")
    elif normalized_status == "SWAPPED":
        reasons.append("Le swap est termine mais le payout fiat n'a pas encore ete prepare.")
    elif normalized_status == "PAYOUT_PENDING":
        reasons.append("Le payout fiat est en cours de traitement ou de verification operateur.")
    elif normalized_status in {"REFUND_PENDING", "REFUNDED"}:
        reasons.append("Le dossier est en parcours de remboursement.")
    elif normalized_status in {"FAILED", "CANCELLED", "EXPIRED"}:
        reasons.append("Le dossier a quitte le flux nominal et demande une verification de l'issue.")
    if flags:
        reasons.append(f"Flags detectes: {', '.join(str(flag) for flag in flags)}.")
    if not reasons:
        reasons.append("Le dossier escrow suit encore son flux normal.")
    return reasons


def _escrow_dossier_type(*, status: str, flags: list[str]) -> str:
    normalized_status = str(status or "").upper()
    if normalized_status in {"REFUND_PENDING", "REFUNDED"}:
        return "refund"
    if flags:
        return "review"
    if normalized_status in {"FAILED", "CANCELLED", "EXPIRED"}:
        return "failed"
    return "standard"


def _escrow_who_must_act_now(status: str) -> str:
    normalized_status = str(status or "").upper()
    if normalized_status == "CREATED":
        return "depositor"
    if normalized_status in {"FUNDED", "SWAPPED", "PAYOUT_PENDING", "REFUND_PENDING"}:
        return "operations"
    return "none"


def _escrow_primary_blocker(*, status: str, flags: list[str], pending_reasons: list[str]) -> str | None:
    if flags:
        return f"Verification operateur requise ({', '.join(str(flag) for flag in flags)})."
    if pending_reasons:
        return str(pending_reasons[0])
    if str(status or "").upper() in {"FAILED", "CANCELLED", "EXPIRED"}:
        return "Le dossier est sorti du flux nominal et doit etre verifie."
    return None


def _escrow_next_step(status: str) -> str:
    normalized_status = str(status or "").upper()
    if normalized_status == "CREATED":
        return "Envoyer le depot USDC vers l'adresse escrow puis attendre la detection."
    if normalized_status == "FUNDED":
        return "Attendre la conversion ou le swap avant le lancement du payout."
    if normalized_status == "SWAPPED":
        return "Attendre la preparation du payout fiat ou verifier l'operateur de paiement."
    if normalized_status == "PAYOUT_PENDING":
        return "Attendre la validation et l'execution finale du payout fiat."
    if normalized_status == "PAID_OUT":
        return "Verifier simplement la bonne reception du payout par le beneficiaire."
    if normalized_status in {"REFUND_PENDING", "REFUNDED"}:
        return "Suivre le remboursement ou confirmer sa bonne reception."
    if normalized_status in {"FAILED", "CANCELLED", "EXPIRED"}:
        return "Verifier la cause de sortie du flux puis recreer un ordre si necessaire."
    return "Verifier le detail de la commande escrow pour connaitre l'etape suivante."


def _p2p_dossier_type(*, status: str, dispute_status: str | None) -> str:
    normalized_status = str(status or "").upper()
    if dispute_status or normalized_status == "DISPUTED":
        return "dispute"
    if normalized_status == "RELEASED":
        return "completed"
    if normalized_status in {"CANCELLED", "CANCELED"}:
        return "cancelled"
    return "standard"


def _p2p_who_must_act_now(*, status: str, dispute_status: str | None) -> str:
    normalized_status = str(status or "").upper()
    if dispute_status or normalized_status == "DISPUTED":
        return "operations"
    if normalized_status in {"CREATED", "AWAITING_CRYPTO"}:
        return "seller"
    if normalized_status in {"CRYPTO_LOCKED", "AWAITING_FIAT"}:
        return "buyer"
    if normalized_status == "FIAT_SENT":
        return "seller"
    return "none"


def _p2p_primary_blocker(blocked_reasons: list[str]) -> str | None:
    return str(blocked_reasons[0]) if blocked_reasons else None


def _p2p_blocked_reasons(*, status: str, dispute_status: str | None, last_note: str | None) -> list[str]:
    reasons: list[str] = []
    normalized_status = str(status or "").upper()
    if normalized_status in {"CREATED", "AWAITING_CRYPTO"}:
        reasons.append("La crypto n'est pas encore verrouillee dans l'escrow.")
    elif normalized_status in {"CRYPTO_LOCKED", "AWAITING_FIAT"}:
        reasons.append("Le trade attend encore le paiement fiat de l'acheteur.")
    elif normalized_status == "FIAT_SENT":
        reasons.append("Le vendeur n'a pas encore confirme la reception du fiat.")
    elif normalized_status == "DISPUTED":
        reasons.append("Le trade est en litige et attend une resolution.")
    if dispute_status:
        reasons.append(f"Litige actuel: {dispute_status}.")
    if last_note:
        reasons.append(f"Derniere note: {last_note}")
    if not reasons:
        reasons.append("Le trade suit encore son flux normal.")
    return reasons


def _escrow_eta_hint(status: str) -> str | None:
    normalized_status = str(status or "").upper()
    if normalized_status == "CREATED":
        return "Aucun delai fiable tant que le depot USDC n'est pas detecte."
    if normalized_status == "FUNDED":
        return "Le traitement prend generalement quelques minutes avant conversion ou swap."
    if normalized_status == "SWAPPED":
        return "Le payout fiat est souvent prepare dans les prochaines minutes."
    if normalized_status == "PAYOUT_PENDING":
        return "Le payout fiat peut prendre de quelques minutes a quelques heures selon l'operateur."
    if normalized_status == "PAID_OUT":
        return "Ordre termine."
    if normalized_status in {"REFUND_PENDING", "REFUNDED"}:
        return "Le delai depend du traitement du remboursement."
    return None


def _p2p_eta_hint(status: str) -> str | None:
    normalized_status = str(status or "").upper()
    if normalized_status in {"CREATED", "AWAITING_CRYPTO"}:
        return "Le delai depend surtout du verrouillage crypto par le vendeur."
    if normalized_status in {"CRYPTO_LOCKED", "AWAITING_FIAT"}:
        return "Le delai depend maintenant de l'envoi du paiement fiat par l'acheteur."
    if normalized_status == "FIAT_SENT":
        return "Le delai depend de la confirmation du vendeur apres reception du fiat."
    if normalized_status == "DISPUTED":
        return "Le delai depend de la resolution du litige par l'equipe operations."
    if normalized_status == "RELEASED":
        return "Trade termine."
    return None


def _transfer_eta_hint(*, status: str, review_reasons: list[str], metadata_payload: dict[str, Any], limit_block_detail: str | None) -> str | None:
    normalized_status = str(status or "").lower()
    if limit_block_detail:
        return "Aucun delai fiable tant que les limites ou le montant ne sont pas ajustes."
    if "insufficient_funds" in review_reasons or metadata_payload.get("funding_pending"):
        return "Aucun delai fiable tant que la couverture financiere n'est pas complete."
    if "aml" in review_reasons or metadata_payload.get("aml_manual_review_required"):
        return "Le delai depend de la revue conformite et peut prendre plus de temps qu'un flux nominal."
    if normalized_status == "approved":
        return "Execution finale attendue prochainement selon le partenaire."
    if normalized_status in {"pending", "initiated"}:
        return "Le dossier reste en validation, sans ETA ferme a ce stade."
    if normalized_status in {"completed", "succeeded"}:
        return "Transfert termine."
    return None


def _financial_diagnostic(
    *,
    current_user: Users,
    wallet_available: Decimal,
    credit_remaining: Decimal,
    latest_transfer_metadata: dict[str, Any],
) -> str:
    if str(getattr(current_user, "status", "") or "").lower() != "active":
        return "COMPTE_NON_ACTIF"
    if bool(getattr(current_user, "external_transfers_blocked", False)):
        return "TRANSFERTS_EXTERNES_SUSPENDUS"

    daily_limit = _safe_decimal(getattr(current_user, "daily_limit", 0))
    used_daily = _safe_decimal(getattr(current_user, "used_daily", 0))
    if daily_limit > 0 and used_daily + Decimal("600") > daily_limit:
        return "LIMITE_JOURNALIERE_DEPASSEE_POUR_600"

    monthly_limit = _safe_decimal(getattr(current_user, "monthly_limit", 0))
    used_monthly = _safe_decimal(getattr(current_user, "used_monthly", 0))
    if monthly_limit > 0 and used_monthly + Decimal("600") > monthly_limit:
        return "LIMITE_MENSUELLE_DEPASSEE_POUR_600"

    if effective_external_transfer_capacity(wallet_available, credit_remaining) < Decimal("600"):
        return "COUVERTURE_INSUFFISANTE_POUR_600_HORS_FRAIS"

    if str(latest_transfer_metadata.get("funding_pending") or "").lower() == "true":
        return "TRANSFERT_EN_ATTENTE_DE_FINANCEMENT"
    if str(latest_transfer_metadata.get("aml_manual_review_required") or "").lower() == "true":
        return "REVUE_AML_MANUELLE"
    return "A_VERIFIER_COTE_LOGS_OU_FRONT"


async def _load_financial_overview(db: AsyncSession, current_user: Users) -> dict[str, Any]:
    balance = await _load_wallet_balance(db, current_user)
    wallet = await db.scalar(_wallet_priority_stmt(current_user.user_id))
    latest_transfer = await db.scalar(
        select(ExternalTransfers)
        .where(ExternalTransfers.user_id == current_user.user_id)
        .order_by(desc(ExternalTransfers.created_at))
    )

    linked_tx = None
    if latest_transfer is not None:
        linked_tx = await db.scalar(
            select(Transactions)
            .where(Transactions.related_entity_id == latest_transfer.transfer_id)
            .order_by(desc(Transactions.created_at))
        )

    wallet_pending = _safe_decimal(getattr(wallet, "pending", 0) if wallet is not None else 0)
    bonus_balance = _safe_decimal(getattr(wallet, "bonus_balance", 0) if wallet is not None else balance.bonus_balance)
    daily_limit = _safe_decimal(getattr(current_user, "daily_limit", 0))
    used_daily = _safe_decimal(getattr(current_user, "used_daily", 0))
    monthly_limit = _safe_decimal(getattr(current_user, "monthly_limit", 0))
    used_monthly = _safe_decimal(getattr(current_user, "used_monthly", 0))
    credit_limit = _safe_decimal(getattr(current_user, "credit_limit", 0))
    credit_used = _safe_decimal(getattr(current_user, "credit_used", 0))
    credit_remaining = max(credit_limit - credit_used, Decimal("0"))
    metadata_payload = dict(getattr(latest_transfer, "metadata_", {}) or {}) if latest_transfer is not None else {}

    return {
        "user_id": str(current_user.user_id),
        "full_name": str(getattr(current_user, "full_name", "") or ""),
        "email": str(getattr(current_user, "email", "") or "") or None,
        "phone_e164": str(getattr(current_user, "phone_e164", "") or "") or None,
        "status": str(getattr(current_user, "status", "") or ""),
        "kyc_status": str(getattr(current_user, "kyc_status", "") or ""),
        "kyc_tier": int(getattr(current_user, "kyc_tier", 0) or 0),
        "external_transfers_blocked": bool(getattr(current_user, "external_transfers_blocked", False)),
        "daily_limit": str(daily_limit),
        "used_daily": str(used_daily),
        "daily_remaining": str(max(daily_limit - used_daily, Decimal("0"))),
        "monthly_limit": str(monthly_limit),
        "used_monthly": str(used_monthly),
        "monthly_remaining": str(max(monthly_limit - used_monthly, Decimal("0"))),
        "wallet_currency": balance.wallet_currency,
        "wallet_available": str(balance.wallet_available),
        "wallet_pending": str(wallet_pending),
        "bonus_balance": str(bonus_balance),
        "credit_limit": str(credit_limit),
        "credit_used": str(credit_used),
        "credit_remaining": str(credit_remaining),
        "risk_score": int(getattr(current_user, "risk_score", 0) or 0),
        "reference_code": str(getattr(latest_transfer, "reference_code", "") or "") or None,
        "transfer_status": str(getattr(latest_transfer, "status", "") or "") or None,
        "last_transfer_amount": str(_safe_decimal(getattr(latest_transfer, "amount", 0))) if latest_transfer is not None else None,
        "last_transfer_currency": str(getattr(latest_transfer, "currency", "") or "") or None,
        "local_amount": str(_safe_decimal(getattr(latest_transfer, "local_amount", 0))) if latest_transfer is not None else None,
        "rate": str(_safe_decimal(getattr(latest_transfer, "rate", 0))) if latest_transfer is not None else None,
        "partner_name": str(getattr(latest_transfer, "partner_name", "") or "") or None,
        "country_destination": str(getattr(latest_transfer, "country_destination", "") or "") or None,
        "recipient_name": str(getattr(latest_transfer, "recipient_name", "") or "") or None,
        "recipient_phone": str(getattr(latest_transfer, "recipient_phone", "") or "") or None,
        "last_transfer_created_at": latest_transfer.created_at.isoformat() if latest_transfer is not None and latest_transfer.created_at else None,
        "last_transfer_processed_at": latest_transfer.processed_at.isoformat() if latest_transfer is not None and latest_transfer.processed_at else None,
        "transaction_status": str(getattr(linked_tx, "status", "") or "") if linked_tx is not None else None,
        "review_reason": metadata_payload.get("review_reason"),
        "review_reasons": metadata_payload.get("review_reasons"),
        "funding_pending": metadata_payload.get("funding_pending"),
        "required_credit_topup": metadata_payload.get("required_credit_topup"),
        "aml_manual_review_required": metadata_payload.get("aml_manual_review_required"),
        "aml_risk_score": metadata_payload.get("aml_risk_score"),
        "aml_reason_codes": metadata_payload.get("aml_reason_codes"),
        "diagnostic_probable": _financial_diagnostic(
            current_user=current_user,
            wallet_available=balance.wallet_available,
            credit_remaining=credit_remaining,
            latest_transfer_metadata=metadata_payload,
        ),
    }


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
                "total_capacity": str(
                    effective_external_transfer_capacity(balance.wallet_available, balance.credit_available)
                ),
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
        dossier_type = _wallet_dossier_type(account_status=account_status, reasons=reasons)
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
                "dossier_type": dossier_type,
                "who_must_act_now": _wallet_who_must_act_now(account_status=account_status),
                "primary_blocker": _wallet_primary_blocker(reasons),
                "next_step": _wallet_block_next_step(
                    account_status=str(getattr(current_user, "status", "") or ""),
                    reasons=reasons,
                ),
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

    if parsed.intent == "wallet.financial_overview":
        return ResolvedCommand(
            intent="wallet.financial_overview",
            action_code="wallet.get_financial_overview",
            payload=await _load_financial_overview(db, current_user),
            requires_confirmation=False,
        )

    if parsed.intent == "wallet.limits":
        balance = await _load_wallet_balance(db, current_user)
        daily_limit = _safe_decimal(getattr(current_user, "daily_limit", 0))
        used_daily = _safe_decimal(getattr(current_user, "used_daily", 0))
        monthly_limit = _safe_decimal(getattr(current_user, "monthly_limit", 0))
        used_monthly = _safe_decimal(getattr(current_user, "used_monthly", 0))
        return ResolvedCommand(
            intent="wallet.limits",
            action_code="wallet.get_limits",
            payload={
                "wallet_currency": balance.wallet_currency,
                "daily_limit": str(daily_limit),
                "used_daily": str(used_daily),
                "daily_remaining": str(max(daily_limit - used_daily, Decimal("0"))),
                "monthly_limit": str(monthly_limit),
                "used_monthly": str(used_monthly),
                "monthly_remaining": str(max(monthly_limit - used_monthly, Decimal("0"))),
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
        flags = [str(item) for item in (getattr(order, "flags", []) or [])]
        pending_reasons = _escrow_pending_reasons(status=status_value, flags=flags)
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
                "flags": flags,
                "dossier_type": _escrow_dossier_type(status=status_value, flags=flags),
                "who_must_act_now": _escrow_who_must_act_now(status_value),
                "primary_blocker": _escrow_primary_blocker(status=status_value, flags=flags, pending_reasons=pending_reasons),
                "pending_reasons": pending_reasons,
                "next_step": _escrow_next_step(status_value),
                "eta_hint": _escrow_eta_hint(status_value),
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
        current_user_role = "buyer" if str(getattr(trade, "buyer_id", "") or "") == str(current_user.user_id) else "seller"
        dispute_status = str(getattr(getattr(dispute, "status", None), "value", getattr(dispute, "status", "")) or "") or None
        blocked_reasons = _p2p_blocked_reasons(
            status=trade_status,
            dispute_status=dispute_status,
            last_note=str(getattr(last_history, "note", "") or "") or None,
        )
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
                "dispute_status": dispute_status or "",
                "last_note": str(getattr(last_history, "note", "") or "") or None,
                "p2p_view": parsed.entities.get("p2p_view"),
                "dossier_type": _p2p_dossier_type(status=trade_status, dispute_status=dispute_status),
                "who_must_act_now": _p2p_who_must_act_now(status=trade_status, dispute_status=dispute_status),
                "primary_blocker": _p2p_primary_blocker(blocked_reasons),
                "current_user_role": current_user_role,
                "blocked_reasons": blocked_reasons,
                "next_step": next_step,
                "eta_hint": _p2p_eta_hint(trade_status),
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
        metadata_payload = dict(getattr(transfer, "metadata_", {}) or {})
        review_reasons = [str(item) for item in (metadata_payload.get("review_reasons") or [])]
        transfer_status = str(transfer.status or "")
        dossier_type = _transfer_dossier_type(
            status=transfer_status,
            review_reasons=review_reasons,
            metadata_payload=metadata_payload,
            limit_block_detail=None,
        )
        return ResolvedCommand(
            intent="transfer.status",
            action_code="transfer.get_status",
            payload={
                "transfer_id": str(transfer.transfer_id),
                "reference_code": transfer.reference_code,
                "transfer_status": transfer_status,
                "transaction_status": str(getattr(linked_tx, "status", "") or "") or None,
                "recipient_name": transfer.recipient_name,
                "recipient_phone": transfer.recipient_phone,
                "partner_name": transfer.partner_name,
                "country_destination": transfer.country_destination,
                "amount": str(transfer.amount or 0),
                "currency": str(transfer.currency or ""),
                "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
                "review_reasons": review_reasons,
                "dossier_type": dossier_type,
                "who_must_act_now": _transfer_who_must_act_now(
                    status=transfer_status,
                    review_reasons=review_reasons,
                    metadata_payload=metadata_payload,
                    limit_block_detail=None,
                ),
                "primary_blocker": _transfer_primary_blocker(
                    review_reasons=review_reasons,
                    metadata_payload=metadata_payload,
                    limit_block_detail=None,
                ),
                "next_step": _transfer_next_step(
                    status=transfer_status,
                    review_reasons=review_reasons,
                    metadata_payload=metadata_payload,
                    limit_block_detail=None,
                ),
                "eta_hint": _transfer_eta_hint(
                    status=transfer_status,
                    review_reasons=review_reasons,
                    metadata_payload=metadata_payload,
                    limit_block_detail=None,
                ),
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
        transfer_amount = _safe_decimal(getattr(transfer, "amount", 0))
        transfer_currency = str(getattr(transfer, "currency", "") or "") or str(getattr(current_user, "currency_code", "") or "") or "EUR"
        shortfall_amount = str(metadata_payload.get("required_credit_topup") or "").strip()
        aml_score = metadata_payload.get("aml_risk_score")
        tx_status = str(getattr(linked_tx, "status", "") or "").lower()
        limit_snapshot = _build_limit_snapshot(current_user=current_user, transfer_amount=transfer_amount)
        limit_block_detail = _describe_limit_block(limit_snapshot, transfer_currency)

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
            if limit_block_detail:
                explanation = f"{explanation} En plus, {limit_block_detail}."
        elif "aml" in review_reasons or aml_manual_review:
            explanation = _describe_aml_reason(aml_score, manual_review=aml_manual_review)
            if aml_reason_detail:
                explanation = f"{explanation} Les principaux signaux releves sont: {aml_reason_detail}."
        elif metadata_payload.get("funding_pending"):
            if shortfall_amount:
                explanation = f"Le transfert est en attente d'un financement complementaire de {shortfall_amount} avant validation."
            else:
                explanation = "Le transfert est en attente d'un financement complementaire avant validation."
            if limit_block_detail:
                explanation = f"{explanation} Cote limites, {limit_block_detail}."
        elif limit_block_detail:
            explanation = f"Le transfert n'a pas pu aboutir car {limit_block_detail}."
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
                "amount": str(transfer_amount),
                "currency": transfer_currency,
                "review_reasons": review_reasons,
                "aml_reason_codes": aml_reason_codes,
                "funding_pending": bool(metadata_payload.get("funding_pending")),
                "aml_manual_review_required": aml_manual_review,
                "required_credit_topup": shortfall_amount or None,
                "aml_risk_score": aml_score,
                "limits": limit_snapshot,
                "next_step": _transfer_next_step(
                    status=str(transfer.status or ""),
                    review_reasons=review_reasons,
                    metadata_payload=metadata_payload,
                    limit_block_detail=limit_block_detail,
                ),
                "eta_hint": _transfer_eta_hint(
                    status=str(transfer.status or ""),
                    review_reasons=review_reasons,
                    metadata_payload=metadata_payload,
                    limit_block_detail=limit_block_detail,
                ),
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
