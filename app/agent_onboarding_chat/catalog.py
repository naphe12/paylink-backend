GUIDES = {
    "cash_in": {
        "message": "Procedure cash-in: identifie le client, confirme le montant, execute l'operation cash-in, puis verifie le nouveau solde.",
        "assumptions": [
            "Verifier le numero ou l'identite du client avant l'operation.",
            "Confirmer la devise et le montant exacts.",
            "S'assurer que la confirmation de succes apparait avant de clore l'echange.",
        ],
        "summary": {
            "screen": "/dashboard/agent/cash-in",
            "action": "cash_in",
            "steps": [
                "Identifier le client et confirmer son identite.",
                "Saisir le montant exact et la bonne devise.",
                "Valider le cash-in puis verifier le nouveau solde affiche.",
            ],
            "quick_links": [
                {"label": "Ouvrir Cash-In", "to": "/dashboard/agent/cash-in"},
                {"label": "Operation client", "to": "/dashboard/agent/operation"},
                {"label": "Scan QR", "to": "/dashboard/agent/scan"},
            ],
        },
    },
    "cash_out": {
        "message": "Procedure cash-out: retrouve le client, verifie son solde et ses limites, confirme le montant, puis valide le cash-out.",
        "assumptions": [
            "Verifier que le client a un solde disponible suffisant.",
            "Verifier les limites et le statut KYC si l'operation bloque.",
            "Ne remettre le cash qu'apres confirmation de succes.",
        ],
        "summary": {
            "screen": "/dashboard/agent/cash-out",
            "action": "cash_out",
            "steps": [
                "Verifier le client, son solde et ses limites.",
                "Confirmer le montant et relire les informations.",
                "Valider le cash-out puis remettre le cash apres confirmation de succes.",
            ],
            "quick_links": [
                {"label": "Ouvrir Cash-Out", "to": "/dashboard/agent/cash-out"},
                {"label": "Operation client", "to": "/dashboard/agent/operation"},
                {"label": "Scan QR", "to": "/dashboard/agent/scan"},
            ],
        },
    },
    "scan_client": {
        "message": "Pour le scan client, ouvre l'ecran QR, scanne le code, controle l'identite affichee, puis choisis l'operation a lancer.",
        "assumptions": [
            "Ne jamais continuer si le QR renvoie un autre client que celui en face de toi.",
            "Verifier le nom et le telephone avant de confirmer.",
        ],
        "summary": {
            "screen": "/dashboard/agent/scan",
            "action": "scan_client",
            "steps": [
                "Ouvrir l'ecran de scan et lire le QR du client.",
                "Verifier que le nom et le telephone correspondent bien.",
                "Choisir ensuite l'operation a executer selon le besoin du client.",
            ],
            "quick_links": [
                {"label": "Ouvrir Scan QR", "to": "/dashboard/agent/scan"},
                {"label": "Cash-In", "to": "/dashboard/agent/cash-in"},
                {"label": "Cash-Out", "to": "/dashboard/agent/cash-out"},
            ],
        },
    },
    "external_transfer": {
        "message": "Pour un transfert externe agent, selectionne le client, choisis le beneficiaire ou saisis-le, verifie pays, partenaire, montant et telephone avant validation.",
        "assumptions": [
            "Verifier soigneusement le numero du beneficiaire.",
            "Confirmer le partenaire et le pays de destination.",
            "En cas de pending, orienter le suivi vers le support transfert.",
        ],
        "summary": {
            "screen": "/dashboard/agent/external-transfer",
            "action": "external_transfer",
            "steps": [
                "Selectionner le client et verifier sa capacite.",
                "Verifier beneficiaire, telephone, partenaire, pays et montant.",
                "Valider puis suivre le statut de la demande si elle passe en pending.",
            ],
            "quick_links": [
                {"label": "Transfert externe", "to": "/dashboard/agent/external-transfer"},
                {"label": "Transferts a cloturer", "to": "/dashboard/agent/transfers/close"},
                {"label": "Historique agent", "to": "/dashboard/agent/history"},
            ],
        },
    },
    "client_checks": {
        "message": "Avant toute operation terrain: verifier identite client, statut KYC, solde disponible, devise et montant demande.",
        "assumptions": [
            "Verifier que le client n'est pas gele ou suspendu.",
            "Verifier que l'operation demandee correspond bien au besoin du client.",
            "En cas d'ecart, stopper avant toute validation.",
        ],
        "summary": {
            "action": "client_checks",
            "steps": [
                "Verifier l'identite du client.",
                "Verifier KYC, statut du compte et disponibilite des fonds.",
                "Verifier que l'operation demandee correspond bien a la demande du client.",
            ],
            "quick_links": [
                {"label": "Operation client", "to": "/dashboard/agent/operation"},
                {"label": "Scan QR", "to": "/dashboard/agent/scan"},
                {"label": "Tableau agent", "to": "/dashboard/agent/dashboard"},
            ],
        },
    },
    "common_errors": {
        "message": "Erreurs frequentes agent: mauvais client selectionne, montant mal saisi, devise incorrecte, numero beneficiaire invalide, solde ou limite insuffisante.",
        "assumptions": [
            "Relire les donnees avant la confirmation finale.",
            "Si une operation bloque, verifier d'abord solde, limites, KYC et statut compte.",
            "En cas de transfert externe bloque, passer par Support transfert.",
        ],
        "summary": {
            "action": "common_errors",
            "steps": [
                "Relire le client selectionne et les informations saisies.",
                "Verifier solde, limites, statut compte et KYC si ca bloque.",
                "Rediriger vers le support approprie si le blocage persiste.",
            ],
            "quick_links": [
                {"label": "Historique agent", "to": "/dashboard/agent/history"},
                {"label": "Assignments payout", "to": "/dashboard/agent/assignments"},
                {"label": "Transferts a cloturer", "to": "/dashboard/agent/transfers/close"},
            ],
        },
    },
}

SCENARIOS = {
    "new_client": {
        "message": "Scenario nouveau client: commence par verifier l'identite, expliquer le flux, faire un scan QR ou une recherche client, puis choisir l'operation seulement apres validation des informations.",
        "assumptions": [
            "Prendre le temps d'expliquer au client ce qui va etre fait avant toute validation.",
            "Verifier telephone, nom et piece si necessaire avant la premiere operation.",
            "Si le client n'est pas encore suffisamment verifie, basculer vers KYC avant de continuer.",
        ],
        "summary": {
            "action": "new_client",
            "screen": "/dashboard/agent/operation",
            "steps": [
                "Identifier le client et expliquer brievement le service demande.",
                "Verifier le numero, l'identite et le niveau KYC avant toute operation sensible.",
                "Lancer ensuite le bon flux: scan, cash-in, cash-out ou transfert.",
            ],
            "quick_links": [
                {"label": "Operation client", "to": "/dashboard/agent/operation"},
                {"label": "Scan QR", "to": "/dashboard/agent/scan"},
                {"label": "Assistant onboarding", "to": "/dashboard/agent/onboarding"},
            ],
        },
    },
    "missing_kyc": {
        "message": "Scenario client sans KYC: ne force pas l'operation. Controle d'abord le niveau KYC, explique le blocage au client, puis oriente-le vers la regularisation avant de relancer le flux.",
        "assumptions": [
            "Un KYC incomplet peut bloquer cash-out, transfert ou limites de compte.",
            "Ne pas promettre une execution immediate si le niveau KYC n'est pas suffisant.",
            "Verifier aussi le statut du compte en plus du KYC.",
        ],
        "summary": {
            "action": "missing_kyc",
            "screen": "/dashboard/agent/operation",
            "steps": [
                "Verifier le niveau KYC et confirmer que le blocage vient bien de ce point.",
                "Expliquer au client quel document ou niveau manque.",
                "Inviter le client a completer KYC avant de reprendre l'operation.",
            ],
            "quick_links": [
                {"label": "Operation client", "to": "/dashboard/agent/operation"},
                {"label": "Scan QR", "to": "/dashboard/agent/scan"},
                {"label": "Historique agent", "to": "/dashboard/agent/history"},
            ],
        },
    },
    "blocked_cash_out": {
        "message": "Scenario cash-out bloque: verifier d'abord solde, limites, KYC et statut du compte. Si tout est correct, verifier ensuite si un traitement agent ou une revue manuelle bloque l'operation.",
        "assumptions": [
            "Le blocage vient souvent d'un solde insuffisant, d'une limite atteinte ou d'un KYC incomplet.",
            "Ne remettre aucun cash tant que l'application ne confirme pas le succes.",
            "Si le blocage persiste, conserver la trace et remonter au support approprie.",
        ],
        "summary": {
            "action": "blocked_cash_out",
            "screen": "/dashboard/agent/cash-out",
            "steps": [
                "Verifier le client, le solde disponible et les limites du compte.",
                "Verifier KYC et statut compte si l'operation ne passe pas.",
                "Relancer le bon flux ou escalader si le blocage persiste.",
            ],
            "quick_links": [
                {"label": "Ouvrir Cash-Out", "to": "/dashboard/agent/cash-out"},
                {"label": "Operation client", "to": "/dashboard/agent/operation"},
                {"label": "Historique agent", "to": "/dashboard/agent/history"},
            ],
        },
    },
}


def build_onboarding_suggestions() -> list[str]:
    return [
        "Comment faire un cash-in ?",
        "Comment faire un cash-out ?",
        "Comment scanner un client ?",
        "Comment faire un transfert externe ?",
        "Que verifier avant une operation client ?",
        "Quelles erreurs frequentes eviter ?",
        "Que faire pour un nouveau client ?",
        "Que faire si le client n'a pas son KYC ?",
    ]
