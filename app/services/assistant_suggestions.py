from typing import Iterable


ASSISTANT_EXAMPLE_CATALOG: dict[str, dict[str, list[str]]] = {
    "wallet": {
        "all": [
            "Demande ton solde wallet.",
            "Demande tes limites journalieres et mensuelles.",
            "Demande les derniers mouvements.",
            "Demande le statut de ton compte.",
            "Explique les mouvements wallet du 2026-03-25.",
            "Explique la ligne de credit du 2026-03-25.",
            "Explique les mouvements wallet et ligne de credit du 2026-03-25.",
            "Demande la situation de ta ligne de credit.",
        ],
    },
    "wallet_support": {
        "all": [
            "Pourquoi mon solde a baisse ?",
            "Je ne vois pas mon depot.",
            "Pourquoi mon retrait est bloque ?",
            "Pourquoi je ne peux plus envoyer ?",
            "Quel est mon dernier mouvement wallet ?",
            "Mon compte est-il gele ?",
            "Quelles sont mes limites restantes aujourd'hui et ce mois ?",
            "Quelle est la prochaine action recommandee pour debloquer mon dossier ?",
        ],
        "blocked_withdraw": [
            "Pourquoi mon retrait est bloque ?",
            "Quelle est la prochaine action recommandee pour mon retrait ?",
        ],
        "cant_send": [
            "Pourquoi je ne peux plus envoyer ?",
            "Quelle limite me bloque aujourd'hui ou ce mois ?",
        ],
        "missing_deposit": [
            "Je ne vois pas mon depot.",
            "Que dois-je faire si mon depot n'apparait toujours pas ?",
        ],
    },
    "cash": {
        "all": [
            "Demande un depot cash.",
            "Demande un retrait cash.",
            "Demande une capacite cash.",
            "Demande le statut de ta derniere demande cash.",
            "Exemple: depot 25000 BIF.",
            "Exemple: retrait 120 USD via Ecocash au +250788123456.",
        ],
        "deposit": [
            "Exemple: depot 25000 BIF.",
            "Exemple: depot 100 USD.",
        ],
        "withdraw": [
            "Exemple: retrait 25000 BIF via Lumicash au +25761234567.",
            "Exemple: cash-out 100 USD via Ecocash au +250788123456.",
        ],
        "capacity": [
            "Demande la capacite cash actuelle.",
            "Demande combien tu peux retirer maintenant.",
        ],
        "request_status": [
            "Demande le statut de ta derniere demande cash.",
            "Demande si ton retrait est encore pending.",
        ],
    },
    "credit": {
        "all": [
            "Demande la capacite financiere actuelle.",
            "Demande le credit disponible restant.",
            "Demande si un montant peut passer, par exemple 200 USD.",
            "Demande pourquoi une demande de transfert est pending.",
            "Exemple: est-ce que 250 USD peut passer ?",
            "Exemple: pourquoi mon transfert est en attente ?",
        ],
        "capacity": [
            "Demande le credit disponible restant.",
            "Demande ta capacite financiere actuelle.",
        ],
        "simulate_transfer": [
            "Exemple: est-ce que 200 USD peut passer ?",
            "Exemple: simule 150000 BIF avec frais.",
        ],
        "pending_reason": [
            "Demande pourquoi une demande de transfert est pending.",
            "Demande la raison du blocage de ton dernier transfert.",
        ],
    },
    "transfer_support": {
        "all": [
            "Demande le statut de ta derniere demande.",
            "Donne une reference comme EXT-AB12CD34.",
            "Demande pourquoi une demande est en pending.",
            "Demande l'explication des statuts pending, approved et completed.",
            "Demande la capacite financiere actuelle.",
            "Suis la reference EXT-AB12CD34.",
            "Demande la prochaine action recommandee pour un transfert pending.",
            "Demande si une limite journaliere ou mensuelle bloque le transfert.",
        ],
        "track_transfer": [
            "Suis la reference EXT-AB12CD34.",
            "Quel est le statut de mon dernier transfert externe ?",
            "Quelle est la prochaine etape de mon dernier transfert externe ?",
        ],
        "pending_reason": [
            "Pourquoi mon transfert est en pending ?",
            "Pourquoi ma demande externe est bloquee ?",
            "Quelle est la prochaine action recommandee pour mon transfert ?",
            "Est-ce une limite journaliere ou mensuelle qui bloque ?",
        ],
        "status_help": [
            "Explique les statuts pending, approved et completed.",
            "Que veut dire approved pour un transfert externe ?",
        ],
        "capacity": [
            "Demande la capacite financiere actuelle.",
            "Combien puis-je utiliser pour un transfert externe ?",
            "Combien me manque-t-il pour lancer mon prochain transfert ?",
        ],
    },
    "agent_transfer": {
        "all": [
            "Exemple: envoie 100 EUR a Jean via Lumicash vers Burundi au +25761234567.",
            "Exemple: transfert 75 USD pour Aline via Ecocash vers Rwanda au +250788123456.",
            "Demande la capacite disponible avant un transfert.",
            "Combien puis-je envoyer maintenant ?",
        ],
        "external_transfer": [
            "Exemple: envoie 100 EUR a Jean via Lumicash vers Burundi au +25761234567.",
            "Exemple: transfert 75 USD pour Aline via Ecocash vers Rwanda au +250788123456.",
        ],
        "capacity": [
            "Demande la capacite disponible avant un transfert.",
            "Combien puis-je envoyer maintenant ?",
        ],
    },
    "kyc": {
        "all": [
            "Demande ton niveau KYC actuel.",
            "Demande quels documents manquent.",
            "Demande les limites journalieres et mensuelles.",
            "Demande ce que debloque le niveau suivant.",
            "Demande pourquoi ton dossier KYC est bloque.",
            "Demande le statut exact de verification.",
        ],
    },
    "escrow": {
        "all": [
            "Quel est le statut de mon dernier escrow ?",
            "Pourquoi mon escrow est en attente ?",
            "Quelle est la prochaine etape de mon escrow ?",
            "Suis la commande 00000000-0000-0000-0000-000000000000",
            "Explique l'etape en cours de mon escrow.",
            "Que dois-je faire maintenant sur mon escrow ?",
            "Le payout est-il en cours de verification ?",
            "Mon escrow est-il en refund ou en revue ?",
        ],
        "why_pending": [
            "Pourquoi mon escrow est en attente ?",
            "Le payout est-il en cours de verification ?",
            "Que dois-je faire maintenant sur mon escrow ?",
        ],
        "next_step": [
            "Quelle est la prochaine etape de mon escrow ?",
            "Que dois-je faire maintenant sur mon escrow ?",
        ],
    },
    "p2p": {
        "all": [
            "Quel est le statut de mon dernier trade P2P ?",
            "Pourquoi mon trade P2P est bloque ?",
            "Quelle est la prochaine etape de mon trade ?",
            "Resume mes offres P2P",
            "Suis le trade 00000000-0000-0000-0000-000000000000",
            "Explique pourquoi mon trade est en litige.",
            "Qui doit agir maintenant sur mon trade ?",
            "Le vendeur a-t-il deja confirme le fiat ?",
        ],
        "why_blocked": [
            "Pourquoi mon trade P2P est bloque ?",
            "Qui doit agir maintenant sur mon trade ?",
            "Le vendeur a-t-il deja confirme le fiat ?",
        ],
        "next_step": [
            "Quelle est la prochaine etape de mon trade ?",
            "Qui doit agir maintenant sur mon trade ?",
        ],
    },
}


ASSISTANT_FIELD_HINTS: dict[str, dict[str, str]] = {
    "cash": {
        "amount": "Precise le montant, par exemple 25000 BIF.",
        "provider_name": "Precise le reseau, par exemple Lumicash ou Ecocash.",
        "mobile_number": "Ajoute le numero mobile complet du beneficiaire.",
    },
    "credit": {
        "amount": "Precise le montant, par exemple 200 USD.",
        "currency": "Precise la devise, par exemple BIF ou USD.",
    },
    "agent_transfer": {
        "partner_name": "Precise le partenaire, par exemple Lumicash ou Ecocash.",
        "country_destination": "Precise le pays de destination, par exemple Burundi.",
        "recipient_phone": "Ajoute le numero du beneficiaire pour l'execution automatique.",
    },
}


def build_assistant_suggestions(
    assistant_key: str,
    *,
    intent: str | None = None,
    missing_fields: Iterable[str] | None = None,
    extra_examples: Iterable[str] | None = None,
    limit: int = 8,
) -> list[str]:
    catalog = ASSISTANT_EXAMPLE_CATALOG.get(assistant_key, {})
    field_hints = ASSISTANT_FIELD_HINTS.get(assistant_key, {})
    ordered: list[str] = []
    seen: set[str] = set()

    def _push(items: Iterable[str] | None) -> None:
        for item in items or []:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(text)
            if len(ordered) >= limit:
                return

    _push(extra_examples)
    if intent and intent != "unknown":
        _push(catalog.get(intent))
    _push(field_hints.get(field_name) for field_name in (missing_fields or []))
    _push(catalog.get("all"))
    return ordered[:limit]
