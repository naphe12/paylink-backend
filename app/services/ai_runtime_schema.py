from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_ai_runtime_schema(db: AsyncSession) -> None:
    await db.execute(text("CREATE SCHEMA IF NOT EXISTS ia"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paylink.external_beneficiaries (
              beneficiary_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              recipient_name text NOT NULL,
              recipient_phone text NOT NULL,
              recipient_email text NULL,
              partner_name text NOT NULL,
              country_destination text NOT NULL,
              is_active boolean NOT NULL DEFAULT true,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            DROP INDEX IF EXISTS paylink.uq_external_beneficiaries_user_partner_phone
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_external_beneficiaries_user_partner_phone_account
            ON paylink.external_beneficiaries (user_id, partner_name, recipient_phone, coalesce(lower(recipient_email), ''))
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_intents (
              intent_code text PRIMARY KEY,
              label text NOT NULL,
              description text,
              domain text NOT NULL,
              requires_confirmation boolean NOT NULL DEFAULT true,
              enabled boolean NOT NULL DEFAULT true
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_intent_slots (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              intent_code text NOT NULL REFERENCES ia.ai_intents(intent_code) ON DELETE CASCADE,
              slot_name text NOT NULL,
              slot_type text NOT NULL,
              required boolean NOT NULL DEFAULT true,
              position_hint integer,
              validation_rule text,
              example text
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_synonyms (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              domain text NOT NULL,
              canonical_value text NOT NULL,
              synonym text NOT NULL,
              language_code text NOT NULL DEFAULT 'fr',
              is_active boolean NOT NULL DEFAULT true
            )
            """
        )
    )
    await db.execute(text("ALTER TABLE ia.ai_synonyms ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_action_registry (
              action_code text PRIMARY KEY,
              intent_code text NOT NULL REFERENCES ia.ai_intents(intent_code) ON DELETE CASCADE,
              service_name text NOT NULL,
              method_name text NOT NULL,
              confirmation_template text,
              success_template text,
              failure_template text,
              enabled boolean NOT NULL DEFAULT true
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_pending_actions (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              session_id uuid NULL,
              intent_code text NOT NULL,
              action_code text NOT NULL,
              payload jsonb NOT NULL,
              status text NOT NULL DEFAULT 'pending',
              result_payload jsonb NULL,
              expires_at timestamptz NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              confirmed_at timestamptz NULL,
              executed_at timestamptz NULL
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_conversation_state (
              session_id uuid PRIMARY KEY,
              user_id uuid NOT NULL REFERENCES paylink.users(user_id) ON DELETE CASCADE,
              current_intent text NULL,
              collected_slots jsonb NOT NULL DEFAULT '{}'::jsonb,
              state text NOT NULL DEFAULT 'active',
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_audit_logs (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
              session_id uuid NULL,
              raw_message text NOT NULL,
              parsed_intent jsonb NULL,
              resolved_command jsonb NULL,
              action_taken text NULL,
              status text NOT NULL,
              error_message text NULL,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_feedback_annotations (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              audit_log_id uuid NOT NULL REFERENCES ia.ai_audit_logs(id) ON DELETE CASCADE,
              reviewer_user_id uuid NULL REFERENCES paylink.users(user_id) ON DELETE SET NULL,
              status text NOT NULL DEFAULT 'reviewed',
              expected_intent text NULL,
              expected_entities_json jsonb NOT NULL DEFAULT '{}'::jsonb,
              parser_was_correct boolean NULL,
              resolver_was_correct boolean NULL,
              final_resolution_notes text NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_feedback_suggestions (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              annotation_id uuid NOT NULL REFERENCES ia.ai_feedback_annotations(id) ON DELETE CASCADE,
              suggestion_type text NOT NULL,
              target_key text NOT NULL,
              proposed_value jsonb NOT NULL,
              applied boolean NOT NULL DEFAULT false,
              applied_at timestamptz NULL,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ia.ai_prompt_fragments (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              intent_code text NOT NULL REFERENCES ia.ai_intents(intent_code) ON DELETE CASCADE,
              fragment_type text NOT NULL DEFAULT 'feedback_hint',
              content text NOT NULL,
              language_code text NOT NULL DEFAULT 'fr',
              enabled boolean NOT NULL DEFAULT true,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_pending_actions_user_status ON ia.ai_pending_actions (user_id, status, expires_at DESC)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_audit_logs_user_created_at ON ia.ai_audit_logs (user_id, created_at DESC)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_feedback_annotations_audit_log_id ON ia.ai_feedback_annotations (audit_log_id, created_at DESC)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_feedback_suggestions_annotation_id ON ia.ai_feedback_suggestions (annotation_id, created_at DESC)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_prompt_fragments_intent_code ON ia.ai_prompt_fragments (intent_code, created_at DESC)"))
    await db.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_synonyms_tuple
            ON ia.ai_synonyms (domain, canonical_value, synonym, language_code)
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO ia.ai_intents (intent_code, label, description, domain, requires_confirmation, enabled)
            VALUES
              ('agent_onboarding.guide', 'Guide onboarding agent', 'Guider un agent sur une procedure terrain ou d''onboarding', 'agent_onboarding', false, true),
              ('agent_onboarding.scenario', 'Scenario onboarding agent', 'Expliquer quoi faire dans un scenario agent specifique', 'agent_onboarding', false, true),
              ('cash.deposit', 'Demande cash-in', 'Preparer une demande de depot cash', 'cash', true, true),
              ('cash.withdraw', 'Demande cash-out', 'Preparer une demande de retrait cash', 'cash', true, true),
              ('wallet.balance', 'Solde wallet', 'Consulter le solde disponible du wallet', 'wallet', false, true),
              ('wallet.block_reason', 'Blocage wallet', 'Expliquer pourquoi une operation wallet semble bloquee', 'wallet', false, true),
              ('wallet.limits', 'Limites wallet', 'Consulter les limites journalieres et mensuelles du wallet', 'wallet', false, true),
              ('credit.capacity', 'Capacite credit', 'Consulter la capacite wallet et credit disponible', 'credit', false, true),
              ('credit.simulate_capacity', 'Simulation capacite', 'Simuler si un montant peut passer avec la capacite actuelle', 'credit', false, true),
              ('credit.pending_reason', 'Raison pending credit', 'Expliquer pourquoi un transfert ou une operation est encore en attente', 'credit', false, true),
              ('kyc.status', 'Statut KYC', 'Consulter le statut KYC, les limites ou les documents manquants', 'kyc', false, true),
              ('escrow.status', 'Statut escrow', 'Consulter le statut du dernier escrow ou d''un identifiant', 'escrow', false, true),
              ('p2p.trade_status', 'Statut trade P2P', 'Consulter le statut ou la prochaine etape d''un trade P2P', 'p2p', false, true),
              ('p2p.offers_summary', 'Resume offres P2P', 'Consulter le resume des offres P2P actives', 'p2p', false, true),
              ('transfer.status', 'Statut transfert', 'Consulter le statut du dernier transfert ou d''une reference', 'transfer', false, true),
              ('help.explain_block_reason', 'Explication blocage', 'Expliquer pourquoi un transfert est bloque ou en attente', 'support', false, true),
              ('transfer.create', 'Creer un transfert', 'Preparer un transfert externe', 'transfer', true, true),
              ('beneficiary.add', 'Ajouter un beneficiaire', 'Enregistrer un beneficiaire externe pour un usage futur', 'transfer', true, true),
              ('beneficiary.list', 'Lister les beneficiaires', 'Consulter les beneficiaires connus ou enregistres', 'transfer', false, true)
            ON CONFLICT (intent_code) DO UPDATE
            SET label = EXCLUDED.label,
                description = EXCLUDED.description,
                domain = EXCLUDED.domain,
                requires_confirmation = EXCLUDED.requires_confirmation,
                enabled = EXCLUDED.enabled
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO ia.ai_action_registry (action_code, intent_code, service_name, method_name, confirmation_template, success_template, failure_template, enabled)
            VALUES
              ('agent_onboarding.get_guide', 'agent_onboarding.guide', 'agent_onboarding_service', 'get_guide', NULL, '{message}', NULL, true),
              ('agent_onboarding.get_scenario', 'agent_onboarding.scenario', 'agent_onboarding_service', 'get_scenario', NULL, '{message}', NULL, true),
              ('cash.create_deposit_request', 'cash.deposit', 'cash_service', 'create_deposit_request', 'Je vais preparer cette demande cash. Confirmer ?', 'Demande cash creee avec succes.', NULL, true),
              ('cash.create_withdraw_request', 'cash.withdraw', 'cash_service', 'create_withdraw_request', 'Je vais preparer cette demande cash. Confirmer ?', 'Demande cash creee avec succes.', NULL, true),
              ('wallet.explain_block_reason', 'wallet.block_reason', 'wallet_service', 'explain_block_reason', NULL, '{explanation}', NULL, true),
              ('wallet.get_balance', 'wallet.balance', 'wallet_service', 'financial_summary', NULL, 'Votre solde disponible est {wallet_available} {wallet_currency}.', NULL, true),
              ('wallet.get_limits', 'wallet.limits', 'wallet_service', 'limits_summary', NULL, 'Limite journaliere: {used_daily} / {daily_limit} {wallet_currency}.', NULL, true),
              ('credit.get_capacity', 'credit.capacity', 'credit_service', 'get_capacity', NULL, 'Capacite actuelle: wallet {wallet_available} {wallet_currency}, credit {credit_available} {wallet_currency}.', NULL, true),
              ('credit.simulate_capacity', 'credit.simulate_capacity', 'credit_service', 'simulate_capacity', NULL, 'Simulation de capacite pour {amount} {currency}.', NULL, true),
              ('credit.get_pending_reason', 'credit.pending_reason', 'credit_service', 'get_pending_reason', NULL, '{explanation}', NULL, true),
              ('kyc.get_status', 'kyc.status', 'kyc_service', 'get_status', NULL, 'Statut KYC: {kyc_status}.', NULL, true),
              ('escrow.get_status', 'escrow.status', 'escrow_service', 'get_status', NULL, 'La commande escrow {order_id} est {status}.', NULL, true),
              ('p2p.get_trade_status', 'p2p.trade_status', 'p2p_service', 'get_trade_status', NULL, 'Le trade P2P {trade_id} est {trade_status}.', NULL, true),
              ('p2p.get_offers_summary', 'p2p.offers_summary', 'p2p_service', 'get_offers_summary', NULL, 'Vous avez {open_offers_count} offre(s) P2P active(s).', NULL, true),
              ('transfer.get_status', 'transfer.status', 'transfer_service', 'get_transfer_status', NULL, 'Le transfert {reference_code} est {transfer_status}.', NULL, true),
              ('transfer.explain_block_reason', 'help.explain_block_reason', 'transfer_service', 'explain_block_reason', NULL, '{explanation}', NULL, true),
              ('transfer_service.create_external_transfer', 'transfer.create', 'transfer_service', 'create_external_transfer', 'Je vais preparer un transfert de {amount} {origin_currency}. Confirmer ?', 'Transfert cree avec succes.', 'Le transfert a echoue.', true),
              ('beneficiary_service.save_external_beneficiary', 'beneficiary.add', 'beneficiary_service', 'save_external_beneficiary', 'Je vais enregistrer ce beneficiaire. Confirmer ?', 'Beneficiaire enregistre avec succes.', 'Le beneficiaire n''a pas pu etre enregistre.', true),
              ('beneficiary_service.list_external_beneficiaries', 'beneficiary.list', 'beneficiary_service', 'list_external_beneficiaries', NULL, '{count} beneficiaire(s) trouves.', NULL, true)
            ON CONFLICT (action_code) DO UPDATE
            SET intent_code = EXCLUDED.intent_code,
                service_name = EXCLUDED.service_name,
                method_name = EXCLUDED.method_name,
                confirmation_template = EXCLUDED.confirmation_template,
                success_template = EXCLUDED.success_template,
                failure_template = EXCLUDED.failure_template,
                enabled = EXCLUDED.enabled
            """
        )
    )
    await db.execute(text("DELETE FROM ia.ai_intent_slots WHERE intent_code IN ('agent_onboarding.guide', 'agent_onboarding.scenario', 'cash.deposit', 'cash.withdraw', 'wallet.balance', 'wallet.block_reason', 'wallet.limits', 'credit.capacity', 'credit.simulate_capacity', 'credit.pending_reason', 'transfer.create', 'beneficiary.add')"))
    await db.execute(
        text(
            """
            INSERT INTO ia.ai_intent_slots (intent_code, slot_name, slot_type, required, position_hint, validation_rule, example)
            VALUES
              ('agent_onboarding.guide', 'guide_topic', 'string', true, 1, NULL, 'cash_out'),
              ('agent_onboarding.scenario', 'scenario', 'string', true, 1, NULL, 'missing_kyc'),
              ('cash.deposit', 'amount', 'decimal', true, 1, 'positive_amount', '25000'),
              ('cash.deposit', 'currency', 'string', false, 2, 'iso_currency', 'BIF'),
              ('cash.withdraw', 'amount', 'decimal', true, 1, 'positive_amount', '25000'),
              ('cash.withdraw', 'currency', 'string', false, 2, 'iso_currency', 'BIF'),
              ('cash.withdraw', 'provider_name', 'string', true, 3, NULL, 'Lumicash'),
              ('cash.withdraw', 'mobile_number', 'string', true, 4, 'phone', '+25761234567'),
              ('credit.simulate_capacity', 'amount', 'decimal', true, 1, 'positive_amount', '100'),
              ('credit.simulate_capacity', 'currency', 'string', false, 2, 'iso_currency', 'EUR'),
              ('transfer.create', 'amount', 'decimal', true, 1, 'positive_amount', '100'),
              ('transfer.create', 'origin_currency', 'string', true, 2, 'iso_currency', 'EUR'),
              ('transfer.create', 'recipient_name', 'string', true, 3, NULL, 'Michel'),
              ('transfer.create', 'partner_name', 'string', true, 4, NULL, 'Lumicash'),
              ('transfer.create', 'recipient_phone', 'string', true, 5, 'phone', '+25761234567'),
              ('transfer.create', 'country_destination', 'string', true, 6, NULL, 'Burundi'),
              ('beneficiary.add', 'recipient_name', 'string', true, 1, NULL, 'Michel'),
              ('beneficiary.add', 'partner_name', 'string', true, 2, NULL, 'Lumicash'),
              ('beneficiary.add', 'recipient_phone', 'string', true, 3, 'phone', '+25761234567'),
              ('beneficiary.add', 'country_destination', 'string', true, 4, NULL, 'Burundi'),
              ('beneficiary.add', 'recipient_email', 'string', false, 5, 'email', 'michel@example.com')
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO ia.ai_synonyms (domain, canonical_value, synonym, language_code)
            VALUES
              ('intent', 'agent_onboarding.guide', 'cash-in agent', 'fr'),
              ('intent', 'agent_onboarding.guide', 'cash-out agent', 'fr'),
              ('intent', 'agent_onboarding.guide', 'scan client', 'fr'),
              ('intent', 'agent_onboarding.scenario', 'nouveau client', 'fr'),
              ('intent', 'agent_onboarding.scenario', 'client sans kyc', 'fr'),
              ('intent', 'agent_onboarding.scenario', 'cash-out bloque', 'fr'),
              ('intent', 'cash.deposit', 'depot', 'fr'),
              ('intent', 'cash.deposit', 'cash-in', 'fr'),
              ('intent', 'cash.deposit', 'deposit', 'en'),
              ('intent', 'cash.deposit', 'add cash', 'en'),
              ('intent', 'cash.deposit', 'depo', 'rn'),
              ('intent', 'cash.deposit', 'weka pesa', 'sw'),
              ('intent', 'cash.withdraw', 'retrait', 'fr'),
              ('intent', 'cash.withdraw', 'cash-out', 'fr'),
              ('intent', 'cash.withdraw', 'withdraw', 'en'),
              ('intent', 'cash.withdraw', 'cash out', 'en'),
              ('intent', 'cash.withdraw', 'kuramwo amafaranga', 'rn'),
              ('intent', 'cash.withdraw', 'toa pesa', 'sw'),
              ('intent', 'transfer.create', 'envoyer', 'fr'),
              ('intent', 'transfer.create', 'transferer', 'fr'),
              ('intent', 'transfer.create', 'payer', 'fr'),
              ('intent', 'transfer.create', 'send', 'en'),
              ('intent', 'transfer.create', 'pay', 'en'),
              ('intent', 'transfer.create', 'transfer', 'en'),
              ('intent', 'transfer.create', 'rungika', 'rn'),
              ('intent', 'transfer.create', 'tuma', 'rn'),
              ('intent', 'transfer.create', 'tuma', 'sw'),
              ('intent', 'transfer.create', 'tuma pesa', 'sw'),
              ('intent', 'beneficiary.add', 'ajoute beneficiaire', 'fr'),
              ('intent', 'beneficiary.add', 'enregistre beneficiaire', 'fr'),
              ('intent', 'beneficiary.add', 'sauvegarde beneficiaire', 'fr'),
              ('intent', 'beneficiary.add', 'add beneficiary', 'en'),
              ('intent', 'beneficiary.add', 'save beneficiary', 'en'),
              ('intent', 'beneficiary.add', 'ongeza beneficiary', 'sw'),
              ('intent', 'beneficiary.list', 'mes beneficiaires', 'fr'),
              ('intent', 'beneficiary.list', 'liste des beneficiaires', 'fr'),
              ('intent', 'beneficiary.list', 'my beneficiaries', 'en'),
              ('intent', 'beneficiary.list', 'saved beneficiaries', 'en'),
              ('intent', 'beneficiary.list', 'beneficiaires banje', 'rn'),
              ('intent', 'beneficiary.list', 'beneficiary zangu', 'sw'),
              ('intent', 'wallet.balance', 'solde', 'fr'),
              ('intent', 'wallet.balance', 'balance', 'fr'),
              ('intent', 'wallet.balance', 'wallet balance', 'en'),
              ('intent', 'wallet.balance', 'available balance', 'en'),
              ('intent', 'wallet.balance', 'solde yanje', 'rn'),
              ('intent', 'wallet.balance', 'amahera angahe', 'rn'),
              ('intent', 'wallet.balance', 'salio yangu', 'sw'),
              ('intent', 'wallet.balance', 'salio', 'sw'),
              ('intent', 'wallet.block_reason', 'pourquoi je ne peux plus envoyer', 'fr'),
              ('intent', 'wallet.block_reason', 'pourquoi mon retrait est bloque', 'fr'),
              ('intent', 'wallet.block_reason', 'why is my wallet blocked', 'en'),
              ('intent', 'wallet.block_reason', 'why can''t i send', 'en'),
              ('intent', 'wallet.block_reason', 'kubera iki sinshobora kurungika', 'rn'),
              ('intent', 'wallet.block_reason', 'kwa nini siwezi kutuma', 'sw'),
              ('intent', 'wallet.limits', 'limite', 'fr'),
              ('intent', 'wallet.limits', 'plafond', 'fr'),
              ('intent', 'wallet.limits', 'limit', 'en'),
              ('intent', 'wallet.limits', 'limits', 'en'),
              ('intent', 'wallet.limits', 'aho bigarukira', 'rn'),
              ('intent', 'wallet.limits', 'kikomo', 'sw'),
              ('intent', 'credit.capacity', 'capacite', 'fr'),
              ('intent', 'credit.capacity', 'credit disponible', 'fr'),
              ('intent', 'credit.capacity', 'capacity', 'en'),
              ('intent', 'credit.capacity', 'available credit', 'en'),
              ('intent', 'credit.capacity', 'ubushobozi', 'rn'),
              ('intent', 'credit.capacity', 'uwezo', 'sw'),
              ('intent', 'credit.simulate_capacity', 'est-ce que ca passe', 'fr'),
              ('intent', 'credit.simulate_capacity', 'simule', 'fr'),
              ('intent', 'credit.simulate_capacity', 'can this pass', 'en'),
              ('intent', 'credit.simulate_capacity', 'simulate', 'en'),
              ('intent', 'credit.simulate_capacity', 'birashoboka', 'rn'),
              ('intent', 'credit.simulate_capacity', 'inawezekana', 'sw'),
              ('intent', 'credit.pending_reason', 'pourquoi pending', 'fr'),
              ('intent', 'credit.pending_reason', 'pourquoi bloque', 'fr'),
              ('intent', 'credit.pending_reason', 'why pending', 'en'),
              ('intent', 'credit.pending_reason', 'why blocked', 'en'),
              ('intent', 'credit.pending_reason', 'kubera iki vyagumye aho', 'rn'),
              ('intent', 'credit.pending_reason', 'kwa nini imekwama', 'sw'),
              ('intent', 'kyc.status', 'kyc', 'fr'),
              ('intent', 'kyc.status', 'verification identite', 'fr'),
              ('intent', 'kyc.status', 'identity verification', 'en'),
              ('intent', 'kyc.status', 'kyc status', 'en'),
              ('intent', 'kyc.status', 'status ya kyc', 'rn'),
              ('intent', 'kyc.status', 'hali ya kyc', 'sw'),
              ('intent', 'p2p.trade_status', 'trade p2p', 'fr'),
              ('intent', 'p2p.trade_status', 'p2p trade', 'en'),
              ('intent', 'p2p.trade_status', 'trade p2p imeze ite', 'rn'),
              ('intent', 'p2p.trade_status', 'hali ya biashara ya p2p', 'sw'),
              ('intent', 'p2p.offers_summary', 'mes offres p2p', 'fr'),
              ('intent', 'p2p.offers_summary', 'my p2p offers', 'en'),
              ('intent', 'p2p.offers_summary', 'offers zanje za p2p', 'rn'),
              ('intent', 'p2p.offers_summary', 'ofa zangu za p2p', 'sw'),
              ('network', 'Lumicash', 'lumicash', 'fr'),
              ('network', 'Lumicash', 'lumi cash', 'fr'),
              ('network', 'Lumicash', 'lumikash', 'en'),
              ('network', 'Lumicash', 'lumikash', 'rn'),
              ('network', 'Lumicash', 'lumikash', 'sw'),
              ('network', 'Ecocash', 'ecocash', 'fr'),
              ('network', 'Ecocash', 'eco cash', 'en'),
              ('network', 'Ecocash', 'ekokash', 'rn'),
              ('network', 'Ecocash', 'ekokash', 'sw'),
              ('network', 'MTN', 'mtn', 'fr'),
              ('network', 'MTN', 'mtn', 'sw')
            ON CONFLICT DO NOTHING
            """
        )
    )
    await db.execute(text("UPDATE ia.ai_synonyms SET is_active = true WHERE is_active IS NULL"))
