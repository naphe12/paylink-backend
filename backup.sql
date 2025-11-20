--
-- PostgreSQL database dump
--

\restrict BaynaWTUeAPu8qGrApYSWXYSrtedZN6awszeMfxxUQCPRhiziHgM1cDTFG7xZbf

-- Dumped from database version 18.0
-- Dumped by pg_dump version 18.0

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: audit; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA audit;


ALTER SCHEMA audit OWNER TO postgres;

--
-- Name: paylink; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA paylink;


ALTER SCHEMA paylink OWNER TO postgres;

--
-- Name: telegram; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA telegram;


ALTER SCHEMA telegram OWNER TO postgres;

--
-- Name: btree_gin; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;


--
-- Name: EXTENSION btree_gin; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION btree_gin IS 'support for indexing common datatypes in GIN';


--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: contribution_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.contribution_status AS ENUM (
    'paid',
    'pending',
    'promised',
    'unpaid'
);


ALTER TYPE paylink.contribution_status OWNER TO postgres;

--
-- Name: dispute_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.dispute_status AS ENUM (
    'opened',
    'investigating',
    'won',
    'lost',
    'closed'
);


ALTER TYPE paylink.dispute_status OWNER TO postgres;

--
-- Name: document_type; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.document_type AS ENUM (
    'national_id',
    'passport',
    'residence_permit',
    'driver_license',
    'utility_bill',
    'student_card',
    'other'
);


ALTER TYPE paylink.document_type OWNER TO postgres;

--
-- Name: kyc_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.kyc_status AS ENUM (
    'unverified',
    'pending',
    'verified',
    'rejected'
);


ALTER TYPE paylink.kyc_status OWNER TO postgres;

--
-- Name: loan_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.loan_status AS ENUM (
    'draft',
    'active',
    'in_arrears',
    'repaid',
    'written_off'
);


ALTER TYPE paylink.loan_status OWNER TO postgres;

--
-- Name: provider_type; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.provider_type AS ENUM (
    'mobile_money',
    'bank',
    'aggregator',
    'card_processor',
    'fx_oracle'
);


ALTER TYPE paylink.provider_type OWNER TO postgres;

--
-- Name: risk_level; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.risk_level AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);


ALTER TYPE paylink.risk_level OWNER TO postgres;

--
-- Name: security_severity; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.security_severity AS ENUM (
    'info',
    'warning',
    'critical'
);


ALTER TYPE paylink.security_severity OWNER TO postgres;

--
-- Name: security_severity_event; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.security_severity_event AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'VERYHIGH'
);


ALTER TYPE paylink.security_severity_event OWNER TO postgres;

--
-- Name: tontine_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.tontine_status AS ENUM (
    'draft',
    'active',
    'paused',
    'completed',
    'cancelled'
);


ALTER TYPE paylink.tontine_status OWNER TO postgres;

--
-- Name: tontine_type; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.tontine_type AS ENUM (
    'rotative',
    'epargne'
);


ALTER TYPE paylink.tontine_type OWNER TO postgres;

--
-- Name: tx_channel; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.tx_channel AS ENUM (
    'mobile_money',
    'bank',
    'card',
    'cash',
    'internal',
    'bank_transfer',
    'external_transfer'
);


ALTER TYPE paylink.tx_channel OWNER TO postgres;

--
-- Name: tx_direction; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.tx_direction AS ENUM (
    'credit',
    'debit'
);


ALTER TYPE paylink.tx_direction OWNER TO postgres;

--
-- Name: tx_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.tx_status AS ENUM (
    'initiated',
    'pending',
    'succeeded',
    'failed',
    'cancelled',
    'reversed',
    'chargeback'
);


ALTER TYPE paylink.tx_status OWNER TO postgres;

--
-- Name: user_role; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.user_role AS ENUM (
    'admin',
    'agent',
    'partener',
    'client',
    'user'
);


ALTER TYPE paylink.user_role OWNER TO postgres;

--
-- Name: user_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.user_status AS ENUM (
    'pending',
    'active',
    'suspended',
    'closed'
);


ALTER TYPE paylink.user_status OWNER TO postgres;

--
-- Name: wallet_cash_request_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.wallet_cash_request_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'PENDING',
    'APPROVED',
    'REJECTED'
);


ALTER TYPE paylink.wallet_cash_request_status OWNER TO postgres;

--
-- Name: wallet_cash_request_type; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.wallet_cash_request_type AS ENUM (
    'deposit',
    'withdraw',
    'DEPOSIT',
    'WITHDRAW'
);


ALTER TYPE paylink.wallet_cash_request_type OWNER TO postgres;

--
-- Name: wallet_entry_direction; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.wallet_entry_direction AS ENUM (
    'credit',
    'debit',
    'CREDIT',
    'DEBIT'
);


ALTER TYPE paylink.wallet_entry_direction OWNER TO postgres;

--
-- Name: wallet_type; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.wallet_type AS ENUM (
    'consumer',
    'agent',
    'merchant',
    'settlement',
    'reserve',
    'admin',
    'personal'
);


ALTER TYPE paylink.wallet_type OWNER TO postgres;

--
-- Name: webhook_status; Type: TYPE; Schema: paylink; Owner: postgres
--

CREATE TYPE paylink.webhook_status AS ENUM (
    'queued',
    'delivered',
    'failed',
    'disabled'
);


ALTER TYPE paylink.webhook_status OWNER TO postgres;

--
-- Name: if_modified_func(); Type: FUNCTION; Schema: audit; Owner: postgres
--

CREATE FUNCTION audit.if_modified_func() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  v_action TEXT;
  v_changed JSONB;
BEGIN
  IF (TG_OP = 'DELETE') THEN
    v_action := 'D';
    INSERT INTO audit.logged_actions(schema_name, table_name, action, row_data, actor_user_id)
    VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, v_action, to_jsonb(OLD), current_setting('app.current_user', true)::uuid);
    RETURN OLD;
  ELSIF (TG_OP = 'UPDATE') THEN
    v_action := 'U';
    v_changed := jsonb_strip_nulls(to_jsonb(NEW)) - 'updated_at';
    INSERT INTO audit.logged_actions(schema_name, table_name, action, row_data, changed_fields, actor_user_id)
    VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, v_action, to_jsonb(OLD), v_changed, current_setting('app.current_user', true)::uuid);
    RETURN NEW;
  ELSIF (TG_OP = 'INSERT') THEN
    v_action := 'I';
    INSERT INTO audit.logged_actions(schema_name, table_name, action, row_data, actor_user_id)
    VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, v_action, to_jsonb(NEW), current_setting('app.current_user', true)::uuid);
    RETURN NEW;
  END IF;
  RETURN NULL;
END;
$$;


ALTER FUNCTION audit.if_modified_func() OWNER TO postgres;

--
-- Name: auto_fix_small_differences(); Type: FUNCTION; Schema: paylink; Owner: postgres
--

CREATE FUNCTION paylink.auto_fix_small_differences() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
  RAISE NOTICE '🧮 Correction automatique des petits écarts (≤ 100 unités)...';

  UPDATE paylink.wallets w
  SET 
    available = v.balance_ledger,
    updated_at = NOW()
  FROM paylink.v_wallet_reconciliation v
  WHERE v.wallet_id = w.wallet_id
    AND ABS(v.difference) <= 100
    AND v.difference <> 0;

  RAISE NOTICE '✅ Correction automatique terminée.';
END;
$$;


ALTER FUNCTION paylink.auto_fix_small_differences() OWNER TO postgres;

--
-- Name: record_initial_balance(uuid, numeric, character); Type: FUNCTION; Schema: paylink; Owner: postgres
--

CREATE FUNCTION paylink.record_initial_balance(p_wallet_id uuid, p_amount numeric, p_currency character) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_journal_id UUID := gen_random_uuid();
    v_wallet_acc UUID;
    v_reserve_acc UUID;
BEGIN
    -- 🔹 Vérifie que le compte wallet existe dans le ledger
    INSERT INTO paylink.ledger_accounts (code, name, currency_code)
    VALUES ('WALLET:'||p_wallet_id::text, 'Wallet initial '||p_wallet_id::text, p_currency)
    ON CONFLICT (code) DO NOTHING;

    SELECT account_id INTO v_wallet_acc
    FROM paylink.ledger_accounts
    WHERE code = 'WALLET:'||p_wallet_id::text;

    -- 🔹 Crée compte réserve si besoin
    INSERT INTO paylink.ledger_accounts (code, name, currency_code)
    VALUES ('RESERVE:'||p_currency, 'Réserve PayLink '||p_currency, p_currency)
    ON CONFLICT (code) DO NOTHING;

    SELECT account_id INTO v_reserve_acc
    FROM paylink.ledger_accounts
    WHERE code = 'RESERVE:'||p_currency;

    -- 🔹 Crée le journal
    INSERT INTO paylink.ledger_journal (journal_id, description)
    VALUES (v_journal_id, 'Initialisation du solde wallet '||p_wallet_id::text);

    -- 🔹 Écritures comptables (partie double)
    INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
    VALUES
        (v_journal_id, v_reserve_acc, 'debit',  p_amount, p_currency),   -- Réserve débite
        (v_journal_id, v_wallet_acc,  'credit', p_amount, p_currency);   -- Wallet crédite

    RAISE NOTICE '💰 Solde initial % % enregistré pour wallet %', p_amount, p_currency, p_wallet_id;
END;
$$;


ALTER FUNCTION paylink.record_initial_balance(p_wallet_id uuid, p_amount numeric, p_currency character) OWNER TO postgres;

--
-- Name: record_transaction(uuid); Type: FUNCTION; Schema: paylink; Owner: postgres
--

CREATE FUNCTION paylink.record_transaction(p_tx_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_tx                paylink.transactions%ROWTYPE;
    v_journal_id        UUID := gen_random_uuid();

    -- Comptes
    v_sender_acc_id     UUID;
    v_receiver_acc_id   UUID;
    v_bank_cash_acc_id  UUID;
    v_reserve_from_id   UUID;
    v_reserve_to_id     UUID;
    v_fees_income_id    UUID;

    -- Devises & montants
    v_from_cur          CHAR(3);
    v_to_cur            CHAR(3);
    v_from_amt          NUMERIC(20,6);
    v_to_amt            NUMERIC(20,6);
    v_fee               NUMERIC(20,6) := 0;

    -- FX éventuel
    v_fx                RECORD;
BEGIN
    -- 1️⃣ Charger la transaction
    SELECT * INTO v_tx
    FROM paylink.transactions
    WHERE tx_id = p_tx_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Transaction % introuvable', p_tx_id;
    END IF;

    v_from_cur := v_tx.currency_code;
    v_to_cur   := v_from_cur;
    v_from_amt := v_tx.amount;
    v_to_amt   := v_tx.amount;

    -- 2️⃣ Vérifier s'il existe une conversion FX liée à la transaction
    SELECT * INTO v_fx FROM paylink.fx_conversions WHERE tx_id = p_tx_id LIMIT 1;
    IF FOUND THEN
        v_from_cur := v_fx.from_currency;
        v_to_cur   := v_fx.to_currency;
        v_to_amt   := ROUND(v_from_amt * v_fx.rate_used, 2);
        RAISE NOTICE 'FX détecté : % % -> % % (taux %)',
            v_from_amt, v_from_cur, v_to_amt, v_to_cur, v_fx.rate_used;
    END IF;

    -- 3️⃣ Créer le journal
    INSERT INTO paylink.ledger_journal (journal_id, tx_id, description)
    VALUES (v_journal_id, p_tx_id, COALESCE(v_tx.description, 'Transaction ' || p_tx_id::text));

    -- 4️⃣ Créer les comptes nécessaires (réserves, cash, etc.)
    INSERT INTO paylink.ledger_accounts (code, name, currency_code)
    VALUES ('BANK:CASH:'||v_from_cur, 'Réserve Cash '||v_from_cur, v_from_cur)
    ON CONFLICT (code) DO NOTHING;

    INSERT INTO paylink.ledger_accounts (code, name, currency_code)
    VALUES ('RESERVE:'||v_from_cur, 'Réserve '||v_from_cur, v_from_cur)
    ON CONFLICT (code) DO NOTHING;

    INSERT INTO paylink.ledger_accounts (code, name, currency_code)
    VALUES ('RESERVE:'||v_to_cur, 'Réserve '||v_to_cur, v_to_cur)
    ON CONFLICT (code) DO NOTHING;

    SELECT account_id INTO v_bank_cash_acc_id FROM paylink.ledger_accounts WHERE code='BANK:CASH:'||v_from_cur;
    SELECT account_id INTO v_reserve_from_id FROM paylink.ledger_accounts WHERE code='RESERVE:'||v_from_cur;
    SELECT account_id INTO v_reserve_to_id FROM paylink.ledger_accounts WHERE code='RESERVE:'||v_to_cur;

    -- 5️⃣ Créer les comptes wallet si non NULL
    IF v_tx.sender_wallet IS NOT NULL THEN
        INSERT INTO paylink.ledger_accounts (code, name, currency_code)
        VALUES ('WALLET:'||v_tx.sender_wallet::text, 'Wallet sender '||v_tx.sender_wallet::text, v_from_cur)
        ON CONFLICT (code) DO NOTHING;

        SELECT account_id INTO v_sender_acc_id
        FROM paylink.ledger_accounts WHERE code='WALLET:'||v_tx.sender_wallet::text;
    END IF;

    IF v_tx.receiver_wallet IS NOT NULL THEN
        INSERT INTO paylink.ledger_accounts (code, name, currency_code)
        VALUES ('WALLET:'||v_tx.receiver_wallet::text, 'Wallet receiver '||v_tx.receiver_wallet::text, v_to_cur)
        ON CONFLICT (code) DO NOTHING;

        SELECT account_id INTO v_receiver_acc_id
        FROM paylink.ledger_accounts WHERE code='WALLET:'||v_tx.receiver_wallet::text;
    END IF;

    -- 6️⃣ Dispatcher selon le canal
    CASE v_tx.channel

        -- 💰 CASH-IN
        WHEN 'cash' THEN
            IF v_receiver_acc_id IS NULL THEN
                RAISE EXCEPTION 'Cash-in: receiver_wallet manquant pour tx %', p_tx_id;
            END IF;

            INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
            VALUES (v_journal_id, v_bank_cash_acc_id, 'debit', v_from_amt, v_from_cur),
                   (v_journal_id, v_receiver_acc_id, 'credit', v_from_amt, v_from_cur);

        -- 🔁 MOBILE MONEY / BANK TRANSFER (Transfert)
        WHEN 'mobile_money', 'bank_transfer' THEN
            -- Débit sender → Crédit réserve (from)
            IF v_sender_acc_id IS NOT NULL THEN
                INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
                VALUES (v_journal_id, v_sender_acc_id, 'debit', v_from_amt, v_from_cur),
                       (v_journal_id, v_reserve_from_id, 'credit', v_from_amt, v_from_cur);
            ELSE
                -- Si pas de sender, PayLink agit comme émetteur
                INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
                VALUES (v_journal_id, v_reserve_from_id, 'credit', v_from_amt, v_from_cur);
            END IF;

            -- Si conversion FX
            IF v_to_cur <> v_from_cur THEN
                IF v_receiver_acc_id IS NULL THEN
                    RAISE EXCEPTION 'FX: receiver_wallet manquant pour tx %', p_tx_id;
                END IF;

                INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
                VALUES (v_journal_id, v_reserve_to_id, 'debit', v_to_amt, v_to_cur),
                       (v_journal_id, v_receiver_acc_id, 'credit', v_to_amt, v_to_cur);
            ELSE
                -- Même devise
                IF v_receiver_acc_id IS NULL THEN
                    RAISE EXCEPTION 'Transfert: receiver_wallet manquant pour tx %', p_tx_id;
                END IF;

                INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
                VALUES (v_journal_id, v_reserve_from_id, 'debit', v_from_amt, v_from_cur),
                       (v_journal_id, v_receiver_acc_id, 'credit', v_from_amt, v_from_cur);
            END IF;

        -- 🏫 PAIEMENT MARCHAND
        WHEN 'card' THEN
            v_fee := ROUND(v_from_amt * 0.01, 2); -- 1% de commission

            INSERT INTO paylink.ledger_accounts (code, name, currency_code)
            VALUES ('FEES:INCOME:'||v_from_cur, 'Revenus PayLink '||v_from_cur, v_from_cur)
            ON CONFLICT (code) DO NOTHING;

            SELECT account_id INTO v_fees_income_id FROM paylink.ledger_accounts WHERE code='FEES:INCOME:'||v_from_cur;

            IF v_sender_acc_id IS NULL OR v_receiver_acc_id IS NULL THEN
                RAISE EXCEPTION 'Paiement marchand: wallets manquants pour tx %', p_tx_id;
            END IF;

            INSERT INTO paylink.ledger_entries (journal_id, account_id, direction, amount, currency_code)
            VALUES
                (v_journal_id, v_sender_acc_id, 'debit', v_from_amt, v_from_cur),
                (v_journal_id, v_fees_income_id, 'credit', v_fee, v_from_cur),
                (v_journal_id, v_receiver_acc_id, 'credit', v_from_amt - v_fee, v_from_cur);

        ELSE
            RAISE NOTICE 'Canal % non reconnu pour tx %, aucune écriture', v_tx.channel, p_tx_id;
    END CASE;

    RAISE NOTICE '✅ Ledger enregistré : tx=% journal=%', p_tx_id, v_journal_id;
END;
$$;


ALTER FUNCTION paylink.record_transaction(p_tx_id uuid) OWNER TO postgres;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: paylink; Owner: postgres
--

CREATE FUNCTION paylink.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION paylink.set_updated_at() OWNER TO postgres;

--
-- Name: sync_wallet_balance(); Type: FUNCTION; Schema: paylink; Owner: postgres
--

CREATE FUNCTION paylink.sync_wallet_balance() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
  RAISE NOTICE '🔄 Synchronisation des soldes wallets avec le ledger...';

  UPDATE paylink.wallets w
  SET
    available = v.ledger_balance,
    updated_at = NOW()
  FROM paylink.v_wallet_balance_ledger v
  WHERE v.wallet_id = w.wallet_id
    AND w.available IS DISTINCT FROM v.ledger_balance;

  RAISE NOTICE '✅ Synchronisation terminée.';
END;
$$;


ALTER FUNCTION paylink.sync_wallet_balance() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: logged_actions; Type: TABLE; Schema: audit; Owner: postgres
--

CREATE TABLE audit.logged_actions (
    audit_id bigint NOT NULL,
    schema_name text NOT NULL,
    table_name text NOT NULL,
    action_tstamp timestamp with time zone DEFAULT now() NOT NULL,
    action text NOT NULL,
    row_data jsonb,
    changed_fields jsonb,
    actor_user_id uuid,
    txid bigint DEFAULT txid_current()
);


ALTER TABLE audit.logged_actions OWNER TO postgres;

--
-- Name: logged_actions_audit_id_seq; Type: SEQUENCE; Schema: audit; Owner: postgres
--

CREATE SEQUENCE audit.logged_actions_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE audit.logged_actions_audit_id_seq OWNER TO postgres;

--
-- Name: logged_actions_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: audit; Owner: postgres
--

ALTER SEQUENCE audit.logged_actions_audit_id_seq OWNED BY audit.logged_actions.audit_id;


--
-- Name: agent_commission_rates; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.agent_commission_rates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    country_code character(2) NOT NULL,
    operation_type text NOT NULL,
    commission_percent numeric(5,2) DEFAULT 1.5 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_commission_rates_operation_type_check CHECK ((operation_type = ANY (ARRAY['cash_in'::text, 'cash_out'::text])))
);


ALTER TABLE paylink.agent_commission_rates OWNER TO postgres;

--
-- Name: agent_commissions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.agent_commissions (
    commission_id uuid DEFAULT gen_random_uuid() NOT NULL,
    agent_user_id uuid NOT NULL,
    operation_type text NOT NULL,
    amount numeric(12,2) NOT NULL,
    related_tx uuid,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE paylink.agent_commissions OWNER TO postgres;

--
-- Name: agent_locations; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.agent_locations (
    location_id uuid DEFAULT gen_random_uuid() NOT NULL,
    agent_id uuid NOT NULL,
    label text,
    lat numeric(10,6),
    lng numeric(10,6),
    address text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.agent_locations OWNER TO postgres;

--
-- Name: agent_transactions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.agent_transactions (
    id integer NOT NULL,
    agent_user_id uuid CONSTRAINT agent_transactions_agent_id_not_null NOT NULL,
    user_id uuid NOT NULL,
    type character varying(20) NOT NULL,
    amount numeric(18,2) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    processed_at timestamp with time zone DEFAULT now(),
    commission numeric(12,2),
    direction text,
    related_tx uuid
);


ALTER TABLE paylink.agent_transactions OWNER TO postgres;

--
-- Name: agent_transactions_id_seq; Type: SEQUENCE; Schema: paylink; Owner: postgres
--

CREATE SEQUENCE paylink.agent_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE paylink.agent_transactions_id_seq OWNER TO postgres;

--
-- Name: agent_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: paylink; Owner: postgres
--

ALTER SEQUENCE paylink.agent_transactions_id_seq OWNED BY paylink.agent_transactions.id;


--
-- Name: agents; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.agents (
    agent_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    display_name text NOT NULL,
    country_code character(2) NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    commission_rate numeric(5,2)
);


ALTER TABLE paylink.agents OWNER TO postgres;

--
-- Name: aml_events; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.aml_events (
    aml_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    tx_id uuid,
    rule_code text NOT NULL,
    risk_level paylink.risk_level NOT NULL,
    details jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.aml_events OWNER TO postgres;

--
-- Name: bill_payments; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.bill_payments (
    bill_payment_id uuid DEFAULT gen_random_uuid() NOT NULL,
    invoice_id uuid NOT NULL,
    tx_id uuid,
    paid_amount numeric(20,6) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.bill_payments OWNER TO postgres;

--
-- Name: bonus_history; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.bonus_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    amount_bif numeric(12,2) NOT NULL,
    source text,
    reference_id uuid,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE paylink.bonus_history OWNER TO postgres;

--
-- Name: countries; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.countries (
    country_code character(2) NOT NULL,
    name text NOT NULL,
    phone_prefix text,
    currency_code character(3) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.countries OWNER TO postgres;

--
-- Name: credit_line_history; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.credit_line_history (
    entry_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    transaction_id uuid,
    amount numeric(12,2) NOT NULL,
    credit_available_before numeric(12,2) NOT NULL,
    credit_available_after numeric(12,2) NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.credit_line_history OWNER TO postgres;

--
-- Name: currencies; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.currencies (
    currency_code character(3) NOT NULL,
    name text NOT NULL,
    decimals smallint DEFAULT 2 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT currencies_decimals_check CHECK (((decimals >= 0) AND (decimals <= 6)))
);


ALTER TABLE paylink.currencies OWNER TO postgres;

--
-- Name: disputes; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.disputes (
    dispute_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tx_id uuid NOT NULL,
    opened_by uuid,
    status paylink.dispute_status DEFAULT 'opened'::paylink.dispute_status NOT NULL,
    reason text,
    evidence_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.disputes OWNER TO postgres;

--
-- Name: external_transfers; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.external_transfers (
    transfer_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    partner_name text NOT NULL,
    country_destination text NOT NULL,
    recipient_name text NOT NULL,
    recipient_phone text NOT NULL,
    amount numeric(12,2) NOT NULL,
    currency text DEFAULT 'EUR'::text,
    rate numeric(10,4),
    local_amount numeric(12,2),
    credit_used boolean DEFAULT false,
    status text DEFAULT 'pending'::text,
    reference_code text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    processed_by uuid,
    processed_at timestamp with time zone DEFAULT now()
);


ALTER TABLE paylink.external_transfers OWNER TO postgres;

--
-- Name: fee_schedules; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.fee_schedules (
    fee_id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    channel paylink.tx_channel,
    provider_id uuid,
    country_code character(2),
    currency_code character(3),
    min_amount numeric(20,6) DEFAULT 0,
    max_amount numeric(20,6),
    fixed_fee numeric(20,6) DEFAULT 0,
    percent_fee numeric(7,4) DEFAULT 0,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.fee_schedules OWNER TO postgres;

--
-- Name: fx_conversions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.fx_conversions (
    conversion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tx_id uuid NOT NULL,
    from_currency character(3) NOT NULL,
    to_currency character(3) NOT NULL,
    rate_used numeric(20,8) NOT NULL,
    fee_fx_bps integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.fx_conversions OWNER TO postgres;

--
-- Name: fx_custom_rates; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.fx_custom_rates (
    rate_id integer NOT NULL,
    origin_currency character varying(3) DEFAULT 'EUR'::character varying NOT NULL,
    destination_currency character varying(3) NOT NULL,
    rate numeric(12,2) NOT NULL,
    source character varying(50) DEFAULT 'parallel_market'::character varying,
    is_active boolean DEFAULT true,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE paylink.fx_custom_rates OWNER TO postgres;

--
-- Name: fx_custom_rates_rate_id_seq; Type: SEQUENCE; Schema: paylink; Owner: postgres
--

CREATE SEQUENCE paylink.fx_custom_rates_rate_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE paylink.fx_custom_rates_rate_id_seq OWNER TO postgres;

--
-- Name: fx_custom_rates_rate_id_seq; Type: SEQUENCE OWNED BY; Schema: paylink; Owner: postgres
--

ALTER SEQUENCE paylink.fx_custom_rates_rate_id_seq OWNED BY paylink.fx_custom_rates.rate_id;


--
-- Name: fx_rates; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.fx_rates (
    fx_id bigint NOT NULL,
    provider_id uuid,
    base_currency character(3) NOT NULL,
    quote_currency character(3) NOT NULL,
    rate numeric(20,8) NOT NULL,
    obtained_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT fx_rates_rate_check CHECK ((rate > (0)::numeric))
);


ALTER TABLE paylink.fx_rates OWNER TO postgres;

--
-- Name: fx_rates_fx_id_seq; Type: SEQUENCE; Schema: paylink; Owner: postgres
--

CREATE SEQUENCE paylink.fx_rates_fx_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE paylink.fx_rates_fx_id_seq OWNER TO postgres;

--
-- Name: fx_rates_fx_id_seq; Type: SEQUENCE OWNED BY; Schema: paylink; Owner: postgres
--

ALTER SEQUENCE paylink.fx_rates_fx_id_seq OWNED BY paylink.fx_rates.fx_id;


--
-- Name: idempotency_keys; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.idempotency_keys (
    key_id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_key text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.idempotency_keys OWNER TO postgres;

--
-- Name: invoices; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.invoices (
    invoice_id uuid DEFAULT gen_random_uuid() NOT NULL,
    merchant_id uuid NOT NULL,
    customer_user uuid,
    amount numeric(20,6) NOT NULL,
    currency_code character(3) NOT NULL,
    due_date date,
    status text DEFAULT 'unpaid'::text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.invoices OWNER TO postgres;

--
-- Name: kyc_documents; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.kyc_documents (
    kyc_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    doc_type paylink.document_type NOT NULL,
    doc_number text,
    file_url text NOT NULL,
    issued_country character(2),
    expires_on date,
    verified boolean DEFAULT false NOT NULL,
    reviewer_user uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.kyc_documents OWNER TO postgres;

--
-- Name: ledger_accounts; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.ledger_accounts (
    account_id uuid DEFAULT gen_random_uuid() NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    currency_code character(3) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.ledger_accounts OWNER TO postgres;

--
-- Name: ledger_entries; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.ledger_entries (
    entry_id bigint NOT NULL,
    journal_id uuid NOT NULL,
    account_id uuid NOT NULL,
    direction paylink.tx_direction NOT NULL,
    amount numeric(20,6) NOT NULL,
    currency_code character(3) NOT NULL,
    CONSTRAINT ledger_entries_amount_check CHECK ((amount > (0)::numeric))
);


ALTER TABLE paylink.ledger_entries OWNER TO postgres;

--
-- Name: ledger_entries_entry_id_seq; Type: SEQUENCE; Schema: paylink; Owner: postgres
--

CREATE SEQUENCE paylink.ledger_entries_entry_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE paylink.ledger_entries_entry_id_seq OWNER TO postgres;

--
-- Name: ledger_entries_entry_id_seq; Type: SEQUENCE OWNED BY; Schema: paylink; Owner: postgres
--

ALTER SEQUENCE paylink.ledger_entries_entry_id_seq OWNED BY paylink.ledger_entries.entry_id;


--
-- Name: ledger_journal; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.ledger_journal (
    journal_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tx_id uuid,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE paylink.ledger_journal OWNER TO postgres;

--
-- Name: limit_usage; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.limit_usage (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    day date DEFAULT CURRENT_DATE NOT NULL,
    month date DEFAULT (date_trunc('month'::text, now()))::date NOT NULL,
    used_daily numeric(20,6) DEFAULT 0 NOT NULL,
    used_monthly numeric(20,6) DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "limit_id " uuid
);


ALTER TABLE paylink.limit_usage OWNER TO postgres;

--
-- Name: limit_usage_id_seq; Type: SEQUENCE; Schema: paylink; Owner: postgres
--

CREATE SEQUENCE paylink.limit_usage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE paylink.limit_usage_id_seq OWNER TO postgres;

--
-- Name: limit_usage_id_seq; Type: SEQUENCE OWNED BY; Schema: paylink; Owner: postgres
--

ALTER SEQUENCE paylink.limit_usage_id_seq OWNED BY paylink.limit_usage.id;


--
-- Name: limits; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.limits (
    limit_id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    kyc_level paylink.kyc_status,
    period text NOT NULL,
    currency_code character(3),
    max_tx_amount numeric(20,6),
    max_tx_count integer,
    max_total_amount numeric(20,6),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.limits OWNER TO postgres;

--
-- Name: loan_repayments; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.loan_repayments (
    repayment_id uuid DEFAULT gen_random_uuid() NOT NULL,
    loan_id uuid NOT NULL,
    tx_id uuid,
    due_date date NOT NULL,
    due_amount numeric(20,6) NOT NULL,
    paid_amount numeric(20,6) DEFAULT 0,
    paid_at timestamp with time zone
);


ALTER TABLE paylink.loan_repayments OWNER TO postgres;

--
-- Name: loans; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.loans (
    loan_id uuid DEFAULT gen_random_uuid() NOT NULL,
    borrower_user uuid NOT NULL,
    principal numeric(20,6) NOT NULL,
    currency_code character(3) NOT NULL,
    apr_percent numeric(7,4) NOT NULL,
    term_months integer NOT NULL,
    status paylink.loan_status DEFAULT 'draft'::paylink.loan_status NOT NULL,
    risk_level paylink.risk_level DEFAULT 'low'::paylink.risk_level,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.loans OWNER TO postgres;

--
-- Name: merchants; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.merchants (
    merchant_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    legal_name text NOT NULL,
    tax_id text,
    country_code character(2) NOT NULL,
    settlement_wallet uuid,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.merchants OWNER TO postgres;

--
-- Name: mobile_money_deposits; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.mobile_money_deposits (
    deposit_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    operator text NOT NULL,
    phone_number text NOT NULL,
    amount_eur numeric(12,2) NOT NULL,
    amount_local numeric(12,2),
    reference_code text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    confirmed_at timestamp with time zone
);


ALTER TABLE paylink.mobile_money_deposits OWNER TO postgres;

--
-- Name: notifications; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.notifications (
    notification_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    channel text NOT NULL,
    subject text,
    message text,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.notifications OWNER TO postgres;

--
-- Name: payment_instructions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.payment_instructions (
    pi_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tx_id uuid NOT NULL,
    provider_account_id uuid,
    direction paylink.tx_direction NOT NULL,
    amount numeric(20,6) NOT NULL,
    currency_code character(3) NOT NULL,
    country_code character(2),
    request_payload jsonb,
    response_payload jsonb,
    status paylink.tx_status DEFAULT 'pending'::paylink.tx_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT pi_status_consistency CHECK ((status = ANY (ARRAY['pending'::paylink.tx_status, 'succeeded'::paylink.tx_status, 'failed'::paylink.tx_status, 'reversed'::paylink.tx_status, 'cancelled'::paylink.tx_status])))
);


ALTER TABLE paylink.payment_instructions OWNER TO postgres;

--
-- Name: provider_accounts; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.provider_accounts (
    provider_account_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_id uuid NOT NULL,
    display_name text NOT NULL,
    currency_code character(3),
    credentials jsonb NOT NULL,
    webhook_secret text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.provider_accounts OWNER TO postgres;

--
-- Name: providers; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.providers (
    provider_id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    type paylink.provider_type NOT NULL,
    country_code character(2),
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.providers OWNER TO postgres;

--
-- Name: recon_files; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.recon_files (
    recon_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_account_id uuid NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    file_url text NOT NULL,
    parsed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.recon_files OWNER TO postgres;

--
-- Name: recon_lines; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.recon_lines (
    recon_line_id bigint NOT NULL,
    recon_id uuid NOT NULL,
    external_ref text,
    amount numeric(20,6),
    currency_code character(3),
    matched_tx uuid,
    status text DEFAULT 'unmatched'::text NOT NULL,
    details jsonb
);


ALTER TABLE paylink.recon_lines OWNER TO postgres;

--
-- Name: recon_lines_recon_line_id_seq; Type: SEQUENCE; Schema: paylink; Owner: postgres
--

CREATE SEQUENCE paylink.recon_lines_recon_line_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE paylink.recon_lines_recon_line_id_seq OWNER TO postgres;

--
-- Name: recon_lines_recon_line_id_seq; Type: SEQUENCE OWNED BY; Schema: paylink; Owner: postgres
--

ALTER SEQUENCE paylink.recon_lines_recon_line_id_seq OWNED BY paylink.recon_lines.recon_line_id;


--
-- Name: sanctions_screening; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.sanctions_screening (
    screening_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    matched boolean NOT NULL,
    provider text,
    payload jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.sanctions_screening OWNER TO postgres;

--
-- Name: security_events; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.security_events (
    event_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    severity text NOT NULL,
    event_type text NOT NULL,
    message text NOT NULL,
    context jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.security_events OWNER TO postgres;

--
-- Name: security_logs; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.security_logs (
    log_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    event_type text NOT NULL,
    severity paylink.security_severity DEFAULT 'info'::paylink.security_severity,
    message text NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE paylink.security_logs OWNER TO postgres;

--
-- Name: settlements; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.settlements (
    settlement_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_account_id uuid,
    currency_code character(3) NOT NULL,
    amount numeric(20,6) NOT NULL,
    scheduled_at timestamp with time zone,
    executed_at timestamp with time zone,
    status text DEFAULT 'pending'::text NOT NULL
);


ALTER TABLE paylink.settlements OWNER TO postgres;

--
-- Name: tontine_contributions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.tontine_contributions (
    contribution_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tontine_id uuid NOT NULL,
    user_id uuid NOT NULL,
    tx_id uuid,
    amount numeric(20,6) NOT NULL,
    paid_at timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'paid'::text NOT NULL,
    created_at time with time zone DEFAULT now()
);


ALTER TABLE paylink.tontine_contributions OWNER TO postgres;

--
-- Name: tontine_invitations; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.tontine_invitations (
    invitation_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tontine_id uuid NOT NULL,
    created_by uuid NOT NULL,
    invite_code character varying(12) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    accepted_at timestamp with time zone,
    accepted_by uuid
);


ALTER TABLE paylink.tontine_invitations OWNER TO postgres;

--
-- Name: tontine_members; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.tontine_members (
    tontine_id uuid NOT NULL,
    user_id uuid NOT NULL,
    is_online boolean DEFAULT false,
    member_id uuid DEFAULT gen_random_uuid(),
    user_name text,
    phone text,
    joined_at time with time zone,
    join_order integer DEFAULT 1
);


ALTER TABLE paylink.tontine_members OWNER TO postgres;

--
-- Name: tontine_payouts; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.tontine_payouts (
    payout_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tontine_id uuid NOT NULL,
    beneficiary_id uuid NOT NULL,
    tx_id uuid,
    amount numeric(20,6) NOT NULL,
    scheduled_at timestamp with time zone,
    paid_at timestamp with time zone
);


ALTER TABLE paylink.tontine_payouts OWNER TO postgres;

--
-- Name: tontine_rotations; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.tontine_rotations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tontine_id uuid,
    user_id uuid,
    order_index integer NOT NULL,
    has_received boolean DEFAULT false,
    received_at timestamp without time zone,
    has_paid boolean DEFAULT false,
    rotation_at time with time zone
);


ALTER TABLE paylink.tontine_rotations OWNER TO postgres;

--
-- Name: tontines; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.tontines (
    tontine_id uuid DEFAULT gen_random_uuid() NOT NULL,
    owner_user uuid NOT NULL,
    name text NOT NULL,
    currency_code character(3) NOT NULL,
    periodicity_days integer DEFAULT 30 NOT NULL,
    status paylink.tontine_status DEFAULT 'draft'::paylink.tontine_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    rotation_order uuid[],
    current_round integer DEFAULT 0,
    common_pot numeric(20,6) DEFAULT 0,
    tontine_type paylink.tontine_type DEFAULT 'rotative'::paylink.tontine_type,
    next_rotation_at timestamp with time zone DEFAULT (now() + '7 days'::interval),
    last_rotation_at time with time zone,
    amount_per_member numeric(15,2)
);


ALTER TABLE paylink.tontines OWNER TO postgres;

--
-- Name: transactions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.transactions (
    tx_id uuid DEFAULT gen_random_uuid() NOT NULL,
    initiated_by uuid,
    sender_wallet uuid,
    receiver_wallet uuid,
    amount numeric(20,6) NOT NULL,
    currency_code character(3) NOT NULL,
    channel paylink.tx_channel NOT NULL,
    status paylink.tx_status DEFAULT 'initiated'::paylink.tx_status NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    related_entity_id uuid,
    CONSTRAINT transactions_amount_check CHECK ((amount > (0)::numeric))
);


ALTER TABLE paylink.transactions OWNER TO postgres;

--
-- Name: user_auth; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.user_auth (
    user_id uuid NOT NULL,
    password_hash text,
    mfa_enabled boolean DEFAULT false NOT NULL,
    last_login_at timestamp with time zone
);


ALTER TABLE paylink.user_auth OWNER TO postgres;

--
-- Name: user_devices; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.user_devices (
    device_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    device_fingerprint text,
    push_token text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.user_devices OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.users (
    user_id uuid DEFAULT gen_random_uuid() NOT NULL,
    status paylink.user_status DEFAULT 'pending'::paylink.user_status NOT NULL,
    full_name text NOT NULL,
    email public.citext,
    phone_e164 public.citext,
    country_code character(2) DEFAULT 'BI'::bpchar NOT NULL,
    kyc_status paylink.kyc_status DEFAULT 'unverified'::paylink.kyc_status NOT NULL,
    referred_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    role paylink.user_role DEFAULT 'client'::paylink.user_role,
    credit_limit numeric(12,2) DEFAULT 0.0,
    credit_used numeric(12,2) DEFAULT 0.0,
    last_seen timestamp with time zone,
    legal_name text,
    birth_date date,
    national_id_number text,
    kyc_document_type text,
    kyc_document_front_url text,
    kyc_document_back_url text,
    selfie_url text,
    kyc_reject_reason text,
    kyc_tier smallint DEFAULT 0,
    daily_limit numeric DEFAULT 30000,
    monthly_limit numeric DEFAULT 30000,
    used_daily numeric DEFAULT 0,
    used_monthly numeric DEFAULT 0,
    last_reset date DEFAULT CURRENT_DATE,
    risk_score integer DEFAULT 0 NOT NULL,
    external_transfers_blocked boolean DEFAULT false,
    paytag public.citext,
    kyc_submitted_at timestamp with time zone DEFAULT now()
);


ALTER TABLE paylink.users OWNER TO postgres;

--
-- Name: v_journal_balanced; Type: VIEW; Schema: paylink; Owner: postgres
--

CREATE VIEW paylink.v_journal_balanced AS
 SELECT j.journal_id,
    sum(
        CASE
            WHEN (e.direction = 'debit'::paylink.tx_direction) THEN e.amount
            ELSE (0)::numeric
        END) AS total_debit,
    sum(
        CASE
            WHEN (e.direction = 'credit'::paylink.tx_direction) THEN e.amount
            ELSE (0)::numeric
        END) AS total_credit
   FROM (paylink.ledger_journal j
     JOIN paylink.ledger_entries e ON ((e.journal_id = j.journal_id)))
  GROUP BY j.journal_id;


ALTER VIEW paylink.v_journal_balanced OWNER TO postgres;

--
-- Name: wallets; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.wallets (
    wallet_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    type paylink.wallet_type DEFAULT 'consumer'::paylink.wallet_type NOT NULL,
    currency_code character(3) NOT NULL,
    available numeric(20,6) DEFAULT 0 NOT NULL,
    pending numeric(20,6) DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    bonus_balance numeric(12,2) DEFAULT 0 NOT NULL
);


ALTER TABLE paylink.wallets OWNER TO postgres;

--
-- Name: v_wallet_balance_ledger; Type: VIEW; Schema: paylink; Owner: postgres
--

CREATE VIEW paylink.v_wallet_balance_ledger AS
 SELECT a.account_id,
    a.code AS ledger_code,
    w.wallet_id,
    u.user_id,
    u.full_name AS owner_name,
    a.currency_code,
    (COALESCE(sum(
        CASE
            WHEN (e.direction = 'credit'::paylink.tx_direction) THEN e.amount
            WHEN (e.direction = 'debit'::paylink.tx_direction) THEN (- e.amount)
            ELSE (0)::numeric
        END), (0)::numeric))::numeric(20,6) AS ledger_balance,
    count(e.entry_id) AS nb_entries
   FROM (((paylink.ledger_accounts a
     LEFT JOIN paylink.ledger_entries e ON ((e.account_id = a.account_id)))
     LEFT JOIN paylink.wallets w ON ((a.code = ('WALLET:'::text || (w.wallet_id)::text))))
     LEFT JOIN paylink.users u ON ((w.user_id = u.user_id)))
  WHERE (a.code ~~ 'WALLET:%'::text)
  GROUP BY a.account_id, a.code, w.wallet_id, u.user_id, u.full_name, a.currency_code
  ORDER BY u.full_name, a.currency_code;


ALTER VIEW paylink.v_wallet_balance_ledger OWNER TO postgres;

--
-- Name: v_wallet_reconciliation; Type: VIEW; Schema: paylink; Owner: postgres
--

CREATE VIEW paylink.v_wallet_reconciliation AS
 SELECT w.wallet_id,
    u.user_id,
    u.full_name AS owner_name,
    w.currency_code,
    (COALESCE(w.available, (0)::numeric))::numeric(20,6) AS balance_stored,
    (COALESCE(v.ledger_balance, (0)::numeric))::numeric(20,6) AS balance_ledger,
    round((COALESCE(v.ledger_balance, (0)::numeric) - COALESCE(w.available, (0)::numeric)), 2) AS difference,
        CASE
            WHEN (round((COALESCE(v.ledger_balance, (0)::numeric) - COALESCE(w.available, (0)::numeric)), 2) = (0)::numeric) THEN '✅ OK'::text
            WHEN (round((COALESCE(v.ledger_balance, (0)::numeric) - COALESCE(w.available, (0)::numeric)), 2) > (0)::numeric) THEN '⬆ Ledger > Wallet'::text
            ELSE '⬇ Wallet > Ledger'::text
        END AS status
   FROM ((paylink.wallets w
     LEFT JOIN paylink.v_wallet_balance_ledger v ON ((v.wallet_id = w.wallet_id)))
     LEFT JOIN paylink.users u ON ((w.user_id = u.user_id)))
  ORDER BY (abs((COALESCE(v.ledger_balance, (0)::numeric) - COALESCE(w.available, (0)::numeric)))) DESC;


ALTER VIEW paylink.v_wallet_reconciliation OWNER TO postgres;

--
-- Name: v_system_health_dashboard; Type: VIEW; Schema: paylink; Owner: postgres
--

CREATE VIEW paylink.v_system_health_dashboard AS
 WITH ledger_totals AS (
         SELECT a.currency_code,
            sum(
                CASE
                    WHEN (e.direction = 'debit'::paylink.tx_direction) THEN e.amount
                    ELSE (0)::numeric
                END) AS total_debit,
            sum(
                CASE
                    WHEN (e.direction = 'credit'::paylink.tx_direction) THEN e.amount
                    ELSE (0)::numeric
                END) AS total_credit,
            round((sum(
                CASE
                    WHEN (e.direction = 'credit'::paylink.tx_direction) THEN e.amount
                    ELSE (0)::numeric
                END) - sum(
                CASE
                    WHEN (e.direction = 'debit'::paylink.tx_direction) THEN e.amount
                    ELSE (0)::numeric
                END)), 2) AS balance_ledger
           FROM (paylink.ledger_entries e
             JOIN paylink.ledger_accounts a ON ((e.account_id = a.account_id)))
          GROUP BY a.currency_code
        ), wallet_totals AS (
         SELECT wallets.currency_code,
            (sum(wallets.available))::numeric(20,2) AS balance_wallets,
            count(*) AS nb_wallets
           FROM paylink.wallets
          GROUP BY wallets.currency_code
        ), reconciliation AS (
         SELECT w_1.currency_code,
            (sum(v.difference))::numeric(20,2) AS total_difference,
            count(*) FILTER (WHERE (v.difference <> (0)::numeric)) AS nb_desync,
            count(*) AS nb_total
           FROM (paylink.v_wallet_reconciliation v
             JOIN paylink.wallets w_1 ON ((v.wallet_id = w_1.wallet_id)))
          GROUP BY w_1.currency_code
        ), fx_audit AS (
         SELECT count(*) AS fx_pending,
            count(*) FILTER (WHERE ((fx_conversions.rate_used IS NULL) OR (fx_conversions.rate_used = (0)::numeric))) AS fx_invalid,
            count(*) FILTER (WHERE (fx_conversions.rate_used > (0)::numeric)) AS fx_valid
           FROM paylink.fx_conversions
        ), income_summary AS (
         SELECT a.currency_code,
            (sum(e.amount))::numeric(20,2) AS total_income
           FROM (paylink.ledger_entries e
             JOIN paylink.ledger_accounts a ON ((e.account_id = a.account_id)))
          WHERE (a.code ~~ 'FEES:INCOME:%'::text)
          GROUP BY a.currency_code
        )
 SELECT w.currency_code,
    COALESCE(w.nb_wallets, (0)::bigint) AS nb_wallets,
    COALESCE(w.balance_wallets, (0)::numeric) AS balance_wallets,
    COALESCE(l.balance_ledger, (0)::numeric) AS balance_ledger,
    COALESCE(r.total_difference, (0)::numeric) AS difference_wallet_ledger,
    COALESCE(r.nb_desync, (0)::bigint) AS wallets_desync,
    COALESCE(r.nb_total, (0)::bigint) AS wallets_total,
        CASE
            WHEN (COALESCE(r.nb_total, (0)::bigint) = 0) THEN (0)::numeric
            ELSE round((((r.nb_desync)::numeric / (r.nb_total)::numeric) * (100)::numeric), 2)
        END AS desync_rate_percent,
    COALESCE(i.total_income, (0)::numeric) AS total_income_fees
   FROM (((wallet_totals w
     LEFT JOIN ledger_totals l USING (currency_code))
     LEFT JOIN reconciliation r USING (currency_code))
     LEFT JOIN income_summary i USING (currency_code))
  ORDER BY w.currency_code;


ALTER VIEW paylink.v_system_health_dashboard OWNER TO postgres;

--
-- Name: v_wallet_initialization_audit; Type: VIEW; Schema: paylink; Owner: postgres
--

CREATE VIEW paylink.v_wallet_initialization_audit AS
 SELECT w.wallet_id,
    u.user_id,
    u.full_name AS owner_name,
    w.currency_code,
    (COALESCE(w.available, (0)::numeric))::numeric(20,6) AS balance_wallet,
    (COALESCE(v.ledger_balance, (0)::numeric))::numeric(20,6) AS balance_ledger,
    round((COALESCE(w.available, (0)::numeric) - COALESCE(v.ledger_balance, (0)::numeric)), 2) AS difference,
        CASE
            WHEN ((COALESCE(v.ledger_balance, (0)::numeric) = (0)::numeric) AND (COALESCE(w.available, (0)::numeric) <> (0)::numeric)) THEN '⚠️ Manque écriture ledger'::text
            WHEN ((COALESCE(v.ledger_balance, (0)::numeric) <> (0)::numeric) AND (COALESCE(w.available, (0)::numeric) = (0)::numeric)) THEN '💸 Manque mise à jour wallet'::text
            ELSE '✅ OK'::text
        END AS audit_status
   FROM ((paylink.wallets w
     LEFT JOIN paylink.v_wallet_balance_ledger v ON ((v.wallet_id = w.wallet_id)))
     LEFT JOIN paylink.users u ON ((w.user_id = u.user_id)))
  WHERE (COALESCE(w.available, (0)::numeric) <> COALESCE(v.ledger_balance, (0)::numeric))
  ORDER BY (abs((COALESCE(w.available, (0)::numeric) - COALESCE(v.ledger_balance, (0)::numeric)))) DESC;


ALTER VIEW paylink.v_wallet_initialization_audit OWNER TO postgres;

--
-- Name: v_wallet_reconciliation_summary; Type: VIEW; Schema: paylink; Owner: postgres
--

CREATE VIEW paylink.v_wallet_reconciliation_summary AS
 SELECT w.currency_code,
    count(*) AS total_wallets,
    count(*) FILTER (WHERE (round((v.ledger_balance - w.available), 2) <> (0)::numeric)) AS nb_desync,
    round(sum((v.ledger_balance - w.available)), 2) AS total_difference
   FROM (paylink.wallets w
     LEFT JOIN paylink.v_wallet_balance_ledger v ON ((v.wallet_id = w.wallet_id)))
  GROUP BY w.currency_code
  ORDER BY (round(sum((v.ledger_balance - w.available)), 2)) DESC;


ALTER VIEW paylink.v_wallet_reconciliation_summary OWNER TO postgres;

--
-- Name: wallet_bonus_history; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.wallet_bonus_history (
    bonus_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    wallet_id uuid NOT NULL,
    amount_bif numeric(12,2) NOT NULL,
    source character varying(50) NOT NULL,
    related_transfer_id uuid,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.wallet_bonus_history OWNER TO postgres;

--
-- Name: wallet_cash_requests; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.wallet_cash_requests (
    request_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    wallet_id uuid NOT NULL,
    type paylink.wallet_cash_request_type NOT NULL,
    status paylink.wallet_cash_request_status DEFAULT 'pending'::paylink.wallet_cash_request_status NOT NULL,
    amount numeric(20,6) NOT NULL,
    fee_amount numeric(20,6) DEFAULT 0 NOT NULL,
    total_amount numeric(20,6) NOT NULL,
    currency_code character(3) NOT NULL,
    mobile_number text,
    provider_name text,
    note text,
    admin_note text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    processed_by uuid,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.wallet_cash_requests OWNER TO postgres;

--
-- Name: wallet_transactions; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.wallet_transactions (
    transaction_id uuid DEFAULT gen_random_uuid() CONSTRAINT wallet_transactions_tx_id_not_null NOT NULL,
    wallet_id uuid NOT NULL,
    user_id uuid NOT NULL,
    operation_type text CONSTRAINT wallet_transactions_tx_type_not_null NOT NULL,
    amount numeric(12,2) NOT NULL,
    currency_code text NOT NULL,
    description text,
    reference text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    direction text,
    balance_after numeric(12,2) DEFAULT 0.0,
    CONSTRAINT wallet_transactions_amount_check CHECK ((amount > (0)::numeric))
);


ALTER TABLE paylink.wallet_transactions OWNER TO postgres;

--
-- Name: webhook_events; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.webhook_events (
    event_id uuid DEFAULT gen_random_uuid() NOT NULL,
    webhook_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    status paylink.webhook_status DEFAULT 'queued'::paylink.webhook_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.webhook_events OWNER TO postgres;

--
-- Name: webhooks; Type: TABLE; Schema: paylink; Owner: postgres
--

CREATE TABLE paylink.webhooks (
    webhook_id uuid DEFAULT gen_random_uuid() NOT NULL,
    subscriber_url text NOT NULL,
    event_types text[] NOT NULL,
    secret text NOT NULL,
    status paylink.webhook_status DEFAULT 'queued'::paylink.webhook_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE paylink.webhooks OWNER TO postgres;

--
-- Name: telegram_users; Type: TABLE; Schema: telegram; Owner: postgres
--

CREATE TABLE telegram.telegram_users (
    id integer NOT NULL,
    chat_id character varying(32) NOT NULL,
    username character varying(64),
    first_name character varying(64),
    last_name character varying(64),
    language_code character varying(8),
    is_bot boolean,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE telegram.telegram_users OWNER TO postgres;

--
-- Name: telegram_users_id_seq; Type: SEQUENCE; Schema: telegram; Owner: postgres
--

CREATE SEQUENCE telegram.telegram_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE telegram.telegram_users_id_seq OWNER TO postgres;

--
-- Name: telegram_users_id_seq; Type: SEQUENCE OWNED BY; Schema: telegram; Owner: postgres
--

ALTER SEQUENCE telegram.telegram_users_id_seq OWNED BY telegram.telegram_users.id;


--
-- Name: logged_actions audit_id; Type: DEFAULT; Schema: audit; Owner: postgres
--

ALTER TABLE ONLY audit.logged_actions ALTER COLUMN audit_id SET DEFAULT nextval('audit.logged_actions_audit_id_seq'::regclass);


--
-- Name: agent_transactions id; Type: DEFAULT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_transactions ALTER COLUMN id SET DEFAULT nextval('paylink.agent_transactions_id_seq'::regclass);


--
-- Name: fx_custom_rates rate_id; Type: DEFAULT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_custom_rates ALTER COLUMN rate_id SET DEFAULT nextval('paylink.fx_custom_rates_rate_id_seq'::regclass);


--
-- Name: fx_rates fx_id; Type: DEFAULT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_rates ALTER COLUMN fx_id SET DEFAULT nextval('paylink.fx_rates_fx_id_seq'::regclass);


--
-- Name: ledger_entries entry_id; Type: DEFAULT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_entries ALTER COLUMN entry_id SET DEFAULT nextval('paylink.ledger_entries_entry_id_seq'::regclass);


--
-- Name: limit_usage id; Type: DEFAULT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.limit_usage ALTER COLUMN id SET DEFAULT nextval('paylink.limit_usage_id_seq'::regclass);


--
-- Name: recon_lines recon_line_id; Type: DEFAULT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_lines ALTER COLUMN recon_line_id SET DEFAULT nextval('paylink.recon_lines_recon_line_id_seq'::regclass);


--
-- Name: telegram_users id; Type: DEFAULT; Schema: telegram; Owner: postgres
--

ALTER TABLE ONLY telegram.telegram_users ALTER COLUMN id SET DEFAULT nextval('telegram.telegram_users_id_seq'::regclass);


--
-- Data for Name: logged_actions; Type: TABLE DATA; Schema: audit; Owner: postgres
--

COPY audit.logged_actions (audit_id, schema_name, table_name, action_tstamp, action, row_data, changed_fields, actor_user_id, txid) FROM stdin;
1	paylink	transactions	2025-11-01 13:30:31.263726+01	I	{"tx_id": "3f87f8b0-fda8-48f1-bdd5-db8f215636d1", "amount": 3000000.000000, "status": "succeeded", "channel": "cash", "created_at": "2025-11-01T13:30:31.263726+01:00", "updated_at": "2025-11-01T13:30:31.263726+01:00", "description": "Dépôt agent - Parent Burundais", "external_ref": null, "initiated_by": "ca1f45a3-5c54-4b46-9b57-e2105c226f84", "currency_code": "BIF", "sender_wallet": null, "receiver_wallet": "0b17e897-079c-4f91-a419-f0cae9e6c5e7"}	\N	\N	9224
2	paylink	transactions	2025-11-01 13:30:31.263726+01	I	{"tx_id": "eaaea6f7-3cc3-49eb-ae0b-4a8a3de73263", "amount": 3000000.000000, "status": "succeeded", "channel": "mobile_money", "created_at": "2025-11-01T13:30:31.263726+01:00", "updated_at": "2025-11-01T13:30:31.263726+01:00", "description": "Transfert Parent → Étudiant (BIF→CDF)", "external_ref": null, "initiated_by": "ca1f45a3-5c54-4b46-9b57-e2105c226f84", "currency_code": "BIF", "sender_wallet": "0b17e897-079c-4f91-a419-f0cae9e6c5e7", "receiver_wallet": "011eb6ce-82de-4802-bfc5-81821d9292f2"}	\N	\N	9224
3	paylink	transactions	2025-11-01 13:31:00.001471+01	I	{"tx_id": "e4028a62-1e40-4309-b009-b2aa46da2176", "amount": 1000.000000, "status": "succeeded", "channel": "card", "created_at": "2025-11-01T13:31:00.001471+01:00", "updated_at": "2025-11-01T13:31:00.001471+01:00", "description": "Transfert diaspora → parent (USD→BIF)", "external_ref": null, "initiated_by": "aa428532-3964-499c-a178-c26861a82551", "currency_code": "USD", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": "0b17e897-079c-4f91-a419-f0cae9e6c5e7"}	\N	\N	9225
4	paylink	transactions	2025-11-01 13:34:14.430737+01	I	{"tx_id": "447766f5-d245-42a5-8c5c-45676e92814f", "amount": 120000.000000, "status": "succeeded", "channel": "bank", "created_at": "2025-11-01T13:34:14.430737+01:00", "updated_at": "2025-11-01T13:34:14.430737+01:00", "description": "Paiement inter-pays (Rwanda → Côte d’Ivoire)", "external_ref": null, "initiated_by": "cb830e57-94fb-457a-8391-b10f2367a637", "currency_code": "KES", "sender_wallet": "3bbcd219-5601-4018-9f03-a93eb0741381", "receiver_wallet": "ca19b78e-9fcb-45ff-8514-938eab8f9273"}	\N	\N	9226
6	paylink	transactions	2025-11-01 13:45:48.922271+01	I	{"tx_id": "636c3921-81f7-40d8-960b-b9daf8dad6b1", "amount": 350000.000000, "status": "succeeded", "channel": "mobile_money", "created_at": "2025-11-01T13:45:48.922271+01:00", "updated_at": "2025-11-01T13:45:48.922271+01:00", "description": "Paiement des frais universitaires", "external_ref": null, "initiated_by": "8ec91346-e0bf-4478-84f9-0412e12cf113", "currency_code": "CDF", "sender_wallet": "011eb6ce-82de-4802-bfc5-81821d9292f2", "receiver_wallet": "c517ed5b-8025-4218-b226-1b55586faf98"}	\N	\N	9231
7	paylink	transactions	2025-11-15 10:16:34.887884+01	I	{"tx_id": "5e875a98-1d8d-4e9f-9e88-a566ce1a4c93", "amount": 25.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T10:16:34.887884+01:00", "updated_at": "2025-11-15T10:16:34.887884+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "4e9c3f42-6f90-463d-9edd-a0daec7d83a3"}	\N	\N	9542
8	paylink	transactions	2025-11-15 11:10:08.718818+01	I	{"tx_id": "34a85ee4-e314-4129-9d27-4316f4d12891", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T11:10:08.718818+01:00", "updated_at": "2025-11-15T11:10:08.718818+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "a866550e-11ac-4ed9-a2cc-75f0bdc074d7"}	\N	\N	9544
9	paylink	transactions	2025-11-15 11:11:50.696978+01	I	{"tx_id": "2ab01f45-e38e-4f0c-9bea-e4c28f78c950", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T11:11:50.696978+01:00", "updated_at": "2025-11-15T11:11:50.696978+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "45103cf9-7f6a-46ee-b006-1e1ac51628f4"}	\N	\N	9546
10	paylink	transactions	2025-11-15 11:17:30.655414+01	I	{"tx_id": "dbfaa84d-a5d8-40bb-8a43-ad1246d9569d", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T11:17:30.655414+01:00", "updated_at": "2025-11-15T11:17:30.655414+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "982b6744-76cd-4dd7-a950-d2fff146228e"}	\N	\N	9549
11	paylink	transactions	2025-11-15 11:19:37.972142+01	I	{"tx_id": "e6700255-57b2-410d-8978-89701c05524f", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T11:19:37.972142+01:00", "updated_at": "2025-11-15T11:19:37.972142+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "19c2d2cb-61a7-4387-9454-ae03cd695e37"}	\N	\N	9551
12	paylink	transactions	2025-11-15 11:23:50.977842+01	I	{"tx_id": "a3af0083-798b-4bc9-bb4d-39ae769d81b9", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T11:23:50.977842+01:00", "updated_at": "2025-11-15T11:23:50.977842+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "59918dde-8c45-49bd-a28d-54f0f6ad4861"}	\N	\N	9553
13	paylink	transactions	2025-11-15 19:22:57.640489+01	I	{"tx_id": "2587bb78-f147-4980-8f99-d0a7fb755847", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T19:22:57.640489+01:00", "updated_at": "2025-11-15T19:22:57.640489+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "b03f6ec2-4f92-4643-834d-0525ec93d0c4"}	\N	\N	9601
14	paylink	transactions	2025-11-15 21:50:42.138477+01	I	{"tx_id": "39d4d0ba-eaf6-456c-a8c8-7c5c8d10dd4f", "amount": 50.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T21:50:42.138477+01:00", "updated_at": "2025-11-15T21:50:42.138477+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "61ce0628-98a2-4bcf-aa7b-bf178b420fba"}	\N	\N	9610
15	paylink	transactions	2025-11-15 21:55:17.389381+01	I	{"tx_id": "5ba8c5d2-b5dc-4d5c-b63c-04bc916533da", "amount": 100.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-15T21:55:17.389381+01:00", "updated_at": "2025-11-15T21:55:17.389381+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "34e39e5a-4efb-434e-b698-1800c42004b9"}	\N	\N	9612
16	paylink	transactions	2025-11-16 20:04:25.424289+01	I	{"tx_id": "bb3bdeb2-c83c-4e4a-8c65-1d78e2651471", "amount": 100.000000, "status": "pending", "channel": "external_transfer", "created_at": "2025-11-16T20:04:25.424289+01:00", "updated_at": "2025-11-16T20:04:25.424289+01:00", "description": null, "initiated_by": "f3967721-8de9-453e-9f0b-1431cbf5197e", "currency_code": "EUR", "sender_wallet": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "receiver_wallet": null, "related_entity_id": "08ef915c-7624-4506-a95c-9e561e4f7ccb"}	\N	\N	9628
\.


--
-- Data for Name: agent_commission_rates; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.agent_commission_rates (id, country_code, operation_type, commission_percent, updated_at) FROM stdin;
\.


--
-- Data for Name: agent_commissions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.agent_commissions (commission_id, agent_user_id, operation_type, amount, related_tx, created_at) FROM stdin;
\.


--
-- Data for Name: agent_locations; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.agent_locations (location_id, agent_id, label, lat, lng, address, created_at) FROM stdin;
\.


--
-- Data for Name: agent_transactions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.agent_transactions (id, agent_user_id, user_id, type, amount, status, processed_at, commission, direction, related_tx) FROM stdin;
\.


--
-- Data for Name: agents; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.agents (agent_id, user_id, display_name, country_code, active, created_at, commission_rate) FROM stdin;
\.


--
-- Data for Name: aml_events; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.aml_events (aml_id, user_id, tx_id, rule_code, risk_level, details, created_at) FROM stdin;
00ed9fc1-6ed4-4c2f-bad8-d1d4e9f051eb	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-14 13:27:52.881941+01
61043aaa-b31c-44ad-aa86-761b48ef7284	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-14 13:42:07.487251+01
85c1102f-c51d-41fd-9c89-1edbc4da05ba	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 13:57:52.857001+01
629a404a-3e85-4e77-a1fa-6f91a86784a9	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:04:08.09481+01
5b764cfb-1342-477d-9f1d-fba94cbf9c4c	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:05:09.304546+01
d7d89d1e-b136-46d7-9bf4-30870e6a7c89	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:06:44.547926+01
f0fe2401-7107-497a-98b6-38c4db6f8af9	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:06:52.443063+01
f3483b64-486b-4e37-951c-9452f48b742b	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:06:53.56961+01
724e794a-669b-4f10-a050-4ab84d7f6b93	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:07:35.645684+01
61dad813-6925-4815-be12-0147423feb6e	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:14:04.322827+01
082bf8e8-9251-40ed-b634-568136e03013	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:16:03.779576+01
9112a6cf-8405-4555-9d50-3cb32fbd3bc9	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 14:18:25.918081+01
593f52e9-b699-41d9-aad6-76fc4dddd856	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-14 15:39:27.262273+01
9d4010aa-19b6-41c9-a958-f23a2ee22439	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 51.0, "score_delta": 35.0}	2025-11-14 16:28:28.686743+01
10ea1de9-cd9e-4af6-8cab-14913e2e6f15	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 51.0, "score_delta": 35.0}	2025-11-14 16:31:09.725204+01
e54e5fb4-490b-4be5-8fd6-cb98a06596c9	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 51.0, "score_delta": 35.0}	2025-11-14 16:33:02.748252+01
117e93f5-c74e-4a59-89ca-8a7ff6f1bbc2	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 51.0, "score_delta": 35.0}	2025-11-14 16:35:49.708092+01
5367ad25-6a7a-419c-880a-2472f0e77e60	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 51.0, "score_delta": 35.0}	2025-11-14 16:39:05.760082+01
bcb2251b-2182-4453-a91a-21a8d5b568a5	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 51.0, "score_delta": 35.0}	2025-11-14 16:39:40.191991+01
417cacaa-1ba1-4ef0-ab4f-185eae579e20	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:21:39.874102+01
9c3e273c-060e-4740-b1eb-aaec1d628ab7	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:28:39.662865+01
1547a9ca-2f05-42d4-97ed-16d05cce9079	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:30:58.788619+01
5475ca10-0254-4b35-8ab7-750578ff314c	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:32:56.67467+01
5bdf01c8-f615-494b-a953-f313a6a925a7	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:40:11.088826+01
e7e0d0d7-8e5a-40a7-8c7e-3b99197cf2f1	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:43:26.315933+01
442710fc-3169-4cc9-9fb8-5d2f4fac6edf	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 09:53:44.952021+01
0428d590-b9db-464f-926d-aa80f63bc862	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 10:07:41.829364+01
bc4e9c9e-10c0-4398-8ae8-8d47baa01ed4	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 10:08:27.370544+01
d04002ed-1c4d-4617-a902-5d7cbed83564	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 10:14:17.311421+01
3ee7d94f-44e5-400b-a27a-69d5cd9b220c	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 25.0, "score_delta": 35.0}	2025-11-15 10:16:34.784067+01
f140483d-054e-4df6-9ea0-550f7bb695d2	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 11:10:08.679081+01
b6f3ee22-e80c-4f7c-a34b-abb5da8dace5	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 11:11:50.680207+01
60d106f8-a328-4c00-bad3-19b1a884b1c7	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 11:17:30.608889+01
988c637c-4573-4fec-976e-9b0026706ed0	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 11:19:37.921084+01
3cb50db8-15ef-408e-9c4e-4c3612eb5115	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 11:23:50.964329+01
c0412280-fdbd-406b-b2d9-46adcfc9d52b	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 19:22:57.589973+01
30b24586-909f-41dc-a725-55727410eeeb	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 50.0, "score_delta": 35.0}	2025-11-15 21:50:42.064777+01
e48ab5ca-1cdc-45fc-afdd-665172b944aa	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 100.0, "score_delta": 35.0}	2025-11-15 21:55:17.344344+01
ffd2ebee-b707-4df2-9b58-f779c9307795	f3967721-8de9-453e-9f0b-1431cbf5197e	\N	risk_update:external	low	{"channel": "external", "new_score": 35.0, "old_score": 0.0, "tx_amount": 100.0, "score_delta": 35.0}	2025-11-16 20:04:25.305403+01
\.


--
-- Data for Name: bill_payments; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.bill_payments (bill_payment_id, invoice_id, tx_id, paid_amount, created_at) FROM stdin;
dac9f996-b2da-465b-a1bf-314fb572e9f8	352c5a38-b05d-461c-ba97-04c7eaa22536	636c3921-81f7-40d8-960b-b9daf8dad6b1	350000.000000	2025-11-01 13:45:48.922271+01
\.


--
-- Data for Name: bonus_history; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.bonus_history (id, user_id, amount_bif, source, reference_id, created_at) FROM stdin;
b5a707ff-6852-4109-bcf4-ee4f4363fd1b	f3967721-8de9-453e-9f0b-1431cbf5197e	1250.00	earned	4e9c3f42-6f90-463d-9edd-a0daec7d83a3	2025-11-15 10:16:34.887884+01
b5a2313f-1ce0-4954-a4f8-e2871175407e	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	a866550e-11ac-4ed9-a2cc-75f0bdc074d7	2025-11-15 11:10:08.718818+01
2366b82c-a714-4bf3-bfd2-95ae5578299b	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	45103cf9-7f6a-46ee-b006-1e1ac51628f4	2025-11-15 11:11:50.696978+01
787c98dd-bc4a-4999-9240-1da2eb9cf967	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	982b6744-76cd-4dd7-a950-d2fff146228e	2025-11-15 11:17:30.655414+01
e856cf56-2f65-4db3-bcd4-0a158de4bd76	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	19c2d2cb-61a7-4387-9454-ae03cd695e37	2025-11-15 11:19:37.972142+01
57fe5280-7201-4a1f-9b5a-68ba90cbe9c9	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	59918dde-8c45-49bd-a28d-54f0f6ad4861	2025-11-15 11:23:50.977842+01
21daa720-73a6-4f05-94a3-557c59bae8ee	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	b03f6ec2-4f92-4643-834d-0525ec93d0c4	2025-11-15 19:22:57.640489+01
19a0dd9f-8d21-487b-ab01-fa2389ce69bd	f3967721-8de9-453e-9f0b-1431cbf5197e	2500.00	earned	61ce0628-98a2-4bcf-aa7b-bf178b420fba	2025-11-15 21:50:42.138477+01
d7dfdc91-56de-4370-9017-da682c84452e	f3967721-8de9-453e-9f0b-1431cbf5197e	5000.00	earned	34e39e5a-4efb-434e-b698-1800c42004b9	2025-11-15 21:55:17.389381+01
e12e4b44-d997-4e58-af20-07f6f84205e7	f3967721-8de9-453e-9f0b-1431cbf5197e	5000.00	earned	08ef915c-7624-4506-a95c-9e561e4f7ccb	2025-11-16 20:04:25.424289+01
\.


--
-- Data for Name: countries; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.countries (country_code, name, phone_prefix, currency_code, created_at, updated_at) FROM stdin;
CD	RDC	+243	CDF	2025-11-01 13:24:34.152469+01	2025-11-01 13:24:34.152469+01
RW	Rwanda	+250	RWF	2025-11-01 13:24:34.152469+01	2025-11-01 13:24:34.152469+01
SN	Sénégal	+221	XOF	2025-11-01 13:24:34.152469+01	2025-11-01 13:24:34.152469+01
KE	Kenya	+254	KES	2025-11-01 13:24:34.152469+01	2025-11-01 13:24:34.152469+01
CI	Côte d'Ivoire	+225	XOF	2025-11-01 13:24:34.152469+01	2025-11-01 13:24:49.485844+01
BI	Burundi	+257	BIF	2025-11-01 13:24:34+01	2025-11-02 16:37:33.050181+01
BE	Belgique	+32	EUR	2025-11-01 13:24:34+01	2025-11-02 16:37:46.011991+01
\.


--
-- Data for Name: credit_line_history; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.credit_line_history (entry_id, user_id, transaction_id, amount, credit_available_before, credit_available_after, description, created_at) FROM stdin;
\.


--
-- Data for Name: currencies; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.currencies (currency_code, name, decimals, created_at, updated_at) FROM stdin;
BIF	Burundian Franc	0	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
CDF	Congolese Franc	2	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
RWF	Rwandan Franc	0	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
XOF	Franc CFA BCEAO	0	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
KES	Kenyan Shilling	2	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
USD	US Dollar	2	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
EUR	Euro	2	2025-11-01 13:25:34.750372+01	2025-11-01 13:25:34.750372+01
\.


--
-- Data for Name: disputes; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.disputes (dispute_id, tx_id, opened_by, status, reason, evidence_url, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: external_transfers; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.external_transfers (transfer_id, user_id, partner_name, country_destination, recipient_name, recipient_phone, amount, currency, rate, local_amount, credit_used, status, reference_code, metadata, created_at, processed_by, processed_at) FROM stdin;
4e9c3f42-6f90-463d-9edd-a0daec7d83a3	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	+32470765843	25.00	EUR	7000.0000	175000.00	f	pending	EXT-A1CB19D4	{}	2025-11-15 10:16:34.883611+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 10:16:34.873512+01
a866550e-11ac-4ed9-a2cc-75f0bdc074d7	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	+32470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-F4EA8F56	{}	2025-11-15 11:10:08.717647+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 11:10:08.713931+01
45103cf9-7f6a-46ee-b006-1e1ac51628f4	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	+32470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-9C025A4A	{}	2025-11-15 11:11:50.695213+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 11:11:50.693742+01
982b6744-76cd-4dd7-a950-d2fff146228e	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	+32470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-69B709BA	{}	2025-11-15 11:17:30.653967+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 11:17:30.650361+01
19c2d2cb-61a7-4387-9454-ae03cd695e37	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	+32470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-845E8A90	{}	2025-11-15 11:19:37.969464+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 11:19:37.967618+01
59918dde-8c45-49bd-a28d-54f0f6ad4861	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	+32470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-1B8B9571	{}	2025-11-15 11:23:50.97682+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 11:23:50.975575+01
b03f6ec2-4f92-4643-834d-0525ec93d0c4	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-9CCE7333	{}	2025-11-15 19:22:57.659763+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 19:22:57.657695+01
61ce0628-98a2-4bcf-aa7b-bf178b420fba	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Nahayo	470765843	50.00	EUR	7000.0000	350000.00	f	pending	EXT-894FE7BE	{}	2025-11-15 21:50:42.168956+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 21:50:42.16646+01
34e39e5a-4efb-434e-b698-1800c42004b9	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Bukuru	470765843	100.00	EUR	7000.0000	700000.00	f	pending	EXT-05B2DD0D	{}	2025-11-15 21:55:17.40923+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-15 21:55:17.407401+01
08ef915c-7624-4506-a95c-9e561e4f7ccb	f3967721-8de9-453e-9f0b-1431cbf5197e	Lumicash	Burundi	Bukomezwa	45656444555	100.00	EUR	7000.0000	700000.00	f	pending	EXT-A20982D7	{}	2025-11-16 20:04:25.49415+01	f3967721-8de9-453e-9f0b-1431cbf5197e	2025-11-16 20:04:25.486259+01
\.


--
-- Data for Name: fee_schedules; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.fee_schedules (fee_id, name, channel, provider_id, country_code, currency_code, min_amount, max_amount, fixed_fee, percent_fee, active, created_at) FROM stdin;
\.


--
-- Data for Name: fx_conversions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.fx_conversions (conversion_id, tx_id, from_currency, to_currency, rate_used, fee_fx_bps, created_at) FROM stdin;
0b5ad257-3f8d-4bc7-90ce-a76df1109fff	eaaea6f7-3cc3-49eb-ae0b-4a8a3de73263	BIF	CDF	1.02000000	50	2025-11-01 13:30:31.263726+01
30e946f9-8ffc-4168-9bbc-7ac5f03b4ec4	e4028a62-1e40-4309-b009-b2aa46da2176	USD	BIF	2900.00000000	75	2025-11-01 13:31:00.001471+01
791aa154-fac4-4bae-b323-25c4c5bee71c	447766f5-d245-42a5-8c5c-45676e92814f	KES	XOF	4.20000000	80	2025-11-01 13:34:14.430737+01
\.


--
-- Data for Name: fx_custom_rates; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.fx_custom_rates (rate_id, origin_currency, destination_currency, rate, source, is_active, updated_at) FROM stdin;
1	EUR	BIF	8500.00	parallel_market	t	2025-11-17 17:35:01.503038
\.


--
-- Data for Name: fx_rates; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.fx_rates (fx_id, provider_id, base_currency, quote_currency, rate, obtained_at) FROM stdin;
1	964c90eb-6534-4ffb-8dc0-00d43e4a3695	USD	BIF	2900.00000000	2025-11-01 13:29:35.587986+01
2	964c90eb-6534-4ffb-8dc0-00d43e4a3695	USD	CDF	2800.00000000	2025-11-01 13:29:35.587986+01
3	964c90eb-6534-4ffb-8dc0-00d43e4a3695	USD	XOF	610.00000000	2025-11-01 13:29:35.587986+01
4	964c90eb-6534-4ffb-8dc0-00d43e4a3695	USD	KES	150.00000000	2025-11-01 13:29:35.587986+01
\.


--
-- Data for Name: idempotency_keys; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.idempotency_keys (key_id, client_key, created_at) FROM stdin;
\.


--
-- Data for Name: invoices; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.invoices (invoice_id, merchant_id, customer_user, amount, currency_code, due_date, status, metadata, created_at, updated_at) FROM stdin;
2a922d00-dd52-416a-98e1-6343b9f9a06a	fe9700a5-c6cc-49cc-a7f0-0f1fab79f893	8ec91346-e0bf-4478-84f9-0412e12cf113	200000.000000	XOF	2025-11-16	unpaid	{"type": "school_fees", "semester": "2025-S1"}	2025-11-01 13:43:49.201907+01	2025-11-01 13:43:49.201907+01
c3479c96-0460-472e-a28f-c1402d8583d6	1b47321d-0b7e-4678-ba06-725cc95552a9	ca1f45a3-5c54-4b46-9b57-e2105c226f84	80000.000000	KES	2025-11-08	unpaid	{"type": "medical_consultation"}	2025-11-01 13:43:49.201907+01	2025-11-01 13:43:49.201907+01
352c5a38-b05d-461c-ba97-04c7eaa22536	80eca020-b6ac-468e-8185-ab6cdb592e4e	8ec91346-e0bf-4478-84f9-0412e12cf113	350000.000000	CDF	2025-12-01	paid	{"type": "tuition_fee", "year": "2025"}	2025-11-01 13:43:49.201907+01	2025-11-01 13:45:48.922271+01
\.


--
-- Data for Name: kyc_documents; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.kyc_documents (kyc_id, user_id, doc_type, doc_number, file_url, issued_country, expires_on, verified, reviewer_user, notes, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ledger_accounts; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.ledger_accounts (account_id, code, name, currency_code, metadata, created_at) FROM stdin;
e4a38193-572f-4a57-89e1-5529639e0874	WALLET_CASH_IN	Encaissements dépôt cash	EUR	{}	2025-11-15 18:59:09.746941+01
ab3420d2-bf3a-4da5-b7e5-2520dddd282d	WALLET_CASH_OUT	Décaissements retrait cash	EUR	{}	2025-11-15 18:59:09.746941+01
cda01d9b-7473-4caa-8c56-41fd660c8636	LEDGER_CASH_IN	Flux cash entrants	EUR	{}	2025-11-15 19:05:07.593376+01
38c1fe1d-6fa0-4297-9a4f-e788afacd797	LEDGER_CASH_OUT	Flux cash sortants	EUR	{}	2025-11-15 19:05:07.593376+01
67ae4f3c-a9d9-48fd-b6d4-f19c961f0e1f	LEDGER_CREDIT	Ligne de crédit clients	EUR	{}	2025-11-15 19:05:07.593376+01
65221aac-4c5c-45f3-81e7-9e0995b8b390	WALLET::48e4fb8b-58c2-445a-9278-0e6258b60b38	Wallet 48e4fb8b-58c2-445a-9278-0e6258b60b38	EUR	{"user_id": "f3967721-8de9-453e-9f0b-1431cbf5197e", "wallet_id": "48e4fb8b-58c2-445a-9278-0e6258b60b38"}	2025-11-15 19:05:35.96858+01
\.


--
-- Data for Name: ledger_entries; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.ledger_entries (entry_id, journal_id, account_id, direction, amount, currency_code) FROM stdin;
55	3670945b-c2f1-4685-89f5-16df50c7bb90	e4a38193-572f-4a57-89e1-5529639e0874	debit	100.000000	EUR
56	3670945b-c2f1-4685-89f5-16df50c7bb90	65221aac-4c5c-45f3-81e7-9e0995b8b390	credit	100.000000	EUR
57	e2a56b94-87a4-467b-be21-032116d0755b	65221aac-4c5c-45f3-81e7-9e0995b8b390	debit	106.250000	EUR
58	e2a56b94-87a4-467b-be21-032116d0755b	ab3420d2-bf3a-4da5-b7e5-2520dddd282d	credit	106.250000	EUR
59	adf2d2d4-6edf-4a62-b36b-b2d339b5ab84	65221aac-4c5c-45f3-81e7-9e0995b8b390	debit	50.000000	EUR
60	adf2d2d4-6edf-4a62-b36b-b2d339b5ab84	ab3420d2-bf3a-4da5-b7e5-2520dddd282d	credit	50.000000	EUR
61	c307d505-5e10-479d-9eeb-d307c2ad6f15	65221aac-4c5c-45f3-81e7-9e0995b8b390	debit	50.000000	EUR
62	c307d505-5e10-479d-9eeb-d307c2ad6f15	ab3420d2-bf3a-4da5-b7e5-2520dddd282d	credit	50.000000	EUR
63	32916b55-e4a3-43aa-b07b-d541363877b1	65221aac-4c5c-45f3-81e7-9e0995b8b390	debit	100.000000	EUR
64	32916b55-e4a3-43aa-b07b-d541363877b1	ab3420d2-bf3a-4da5-b7e5-2520dddd282d	credit	100.000000	EUR
65	f80d2ee8-c4ae-404f-9b7a-85d373b74a0a	65221aac-4c5c-45f3-81e7-9e0995b8b390	debit	100.000000	EUR
66	f80d2ee8-c4ae-404f-9b7a-85d373b74a0a	ab3420d2-bf3a-4da5-b7e5-2520dddd282d	credit	100.000000	EUR
\.


--
-- Data for Name: ledger_journal; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.ledger_journal (journal_id, tx_id, occurred_at, description, metadata) FROM stdin;
3670945b-c2f1-4685-89f5-16df50c7bb90	\N	2025-11-15 19:05:35.96858+01	Validation dépôt cash	{"type": "deposit", "movement_id": "89bb6026-a43f-4b6d-a83a-a8dca56cd2bf", "processed_by": "cd4d7154-9d5e-4c3a-bb38-aad84014e92b", "cash_request_id": "e2463283-dfcb-41a3-af68-57beca75619c"}
e2a56b94-87a4-467b-be21-032116d0755b	\N	2025-11-15 19:06:10.329575+01	Validation retrait cash	{"type": "withdraw", "movement_id": "c5fa80bf-0de7-4fbe-9e60-9819ee5347c7", "processed_by": "cd4d7154-9d5e-4c3a-bb38-aad84014e92b", "cash_request_id": "a8a28b70-acb1-4567-8e81-400c4efff174"}
adf2d2d4-6edf-4a62-b36b-b2d339b5ab84	2587bb78-f147-4980-8f99-d0a7fb755847	2025-11-15 19:22:57.640489+01	Transfert externe vers Nahayo	{"user_id": "f3967721-8de9-453e-9f0b-1431cbf5197e", "operation": "external_transfer", "wallet_id": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "movement_id": "c5cbca94-51bb-46e4-8294-7aebcb6f29ac", "transfer_id": "b03f6ec2-4f92-4643-834d-0525ec93d0c4", "debited_amount": "50", "transaction_id": "2587bb78-f147-4980-8f99-d0a7fb755847", "credit_used_amount": "0"}
c307d505-5e10-479d-9eeb-d307c2ad6f15	39d4d0ba-eaf6-456c-a8c8-7c5c8d10dd4f	2025-11-15 21:50:42.138477+01	Transfert externe vers Nahayo	{"user_id": "f3967721-8de9-453e-9f0b-1431cbf5197e", "operation": "external_transfer", "wallet_id": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "movement_id": "13c57269-cf7e-4695-9ed0-f536b0f11542", "transfer_id": "61ce0628-98a2-4bcf-aa7b-bf178b420fba", "debited_amount": "50", "transaction_id": "39d4d0ba-eaf6-456c-a8c8-7c5c8d10dd4f", "credit_used_amount": "0"}
32916b55-e4a3-43aa-b07b-d541363877b1	5ba8c5d2-b5dc-4d5c-b63c-04bc916533da	2025-11-15 21:55:17.389381+01	Transfert externe vers Bukuru	{"user_id": "f3967721-8de9-453e-9f0b-1431cbf5197e", "operation": "external_transfer", "wallet_id": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "movement_id": "71cbeddb-0bd3-4638-865f-959f11e6ee67", "transfer_id": "34e39e5a-4efb-434e-b698-1800c42004b9", "debited_amount": "100", "transaction_id": "5ba8c5d2-b5dc-4d5c-b63c-04bc916533da", "credit_used_amount": "0"}
f80d2ee8-c4ae-404f-9b7a-85d373b74a0a	bb3bdeb2-c83c-4e4a-8c65-1d78e2651471	2025-11-16 20:04:25.424289+01	Transfert externe vers Bukomezwa	{"user_id": "f3967721-8de9-453e-9f0b-1431cbf5197e", "operation": "external_transfer", "wallet_id": "48e4fb8b-58c2-445a-9278-0e6258b60b38", "movement_id": "723d43f9-5563-4b43-b963-d056ef011513", "transfer_id": "08ef915c-7624-4506-a95c-9e561e4f7ccb", "debited_amount": "100.0", "transaction_id": "bb3bdeb2-c83c-4e4a-8c65-1d78e2651471", "credit_used_amount": "0"}
\.


--
-- Data for Name: limit_usage; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.limit_usage (id, user_id, day, month, used_daily, used_monthly, updated_at, "limit_id ") FROM stdin;
\.


--
-- Data for Name: limits; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.limits (limit_id, name, kyc_level, period, currency_code, max_tx_amount, max_tx_count, max_total_amount, created_at) FROM stdin;
\.


--
-- Data for Name: loan_repayments; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.loan_repayments (repayment_id, loan_id, tx_id, due_date, due_amount, paid_amount, paid_at) FROM stdin;
\.


--
-- Data for Name: loans; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.loans (loan_id, borrower_user, principal, currency_code, apr_percent, term_months, status, risk_level, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: merchants; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.merchants (merchant_id, user_id, legal_name, tax_id, country_code, settlement_wallet, active, created_at) FROM stdin;
fe9700a5-c6cc-49cc-a7f0-0f1fab79f893	50cc3f16-d8eb-4582-8a3c-62102e39a3a2	École Sainte-Marie	CI-TX-2024-01	SN	ca19b78e-9fcb-45ff-8514-938eab8f9273	t	2025-11-01 13:43:25.272671+01
1b47321d-0b7e-4678-ba06-725cc95552a9	cb830e57-94fb-457a-8391-b10f2367a637	Kigali General Hospital	RW-HO-2024-07	RW	3bbcd219-5601-4018-9f03-a93eb0741381	t	2025-11-01 13:43:25.272671+01
80eca020-b6ac-468e-8185-ab6cdb592e4e	ceac05ae-872c-4eff-aa69-de251deb50c7	Université de Kinshasa	CD-EDU-2024-02	CD	c517ed5b-8025-4218-b226-1b55586faf98	t	2025-11-01 13:43:25.272671+01
\.


--
-- Data for Name: mobile_money_deposits; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.mobile_money_deposits (deposit_id, user_id, operator, phone_number, amount_eur, amount_local, reference_code, status, created_at, confirmed_at) FROM stdin;
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.notifications (notification_id, user_id, channel, subject, message, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: payment_instructions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.payment_instructions (pi_id, tx_id, provider_account_id, direction, amount, currency_code, country_code, request_payload, response_payload, status, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: provider_accounts; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.provider_accounts (provider_account_id, provider_id, display_name, currency_code, credentials, webhook_secret, active, created_at, updated_at) FROM stdin;
5c771bff-45f3-409a-9b4c-081d245e1292	ba504734-2303-4814-8ffe-11748582f13e	M-Pesa Settlement Account	KES	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
46c95f61-95f0-474b-99ce-87b01e4f1de5	5e088311-c55f-4290-adc1-dddf5bad5722	MTN MoMo Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
29cd7b4d-2141-49c0-9adc-ae68826a32cb	7e64ed8f-c823-4d41-8d80-50d5a00e877f	Orange Money Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
e8e31de6-fb26-4518-a367-66f21a974458	ed6ba64e-330f-4485-9d65-42d1dea868fe	Wave Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
4f43cfeb-f7cd-4311-8d59-e75a5cb6ec7a	735b219a-b5fc-4807-84c5-66ad6d8513f9	Ecobank Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
6de8dcb4-a79a-473f-ac92-07bf56782df0	964c90eb-6534-4ffb-8dc0-00d43e4a3695	MFS Africa Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
f0a39f49-85fb-4289-b859-9eca927f095f	89410bf3-7c1b-4cd1-9687-c3e7a86a4ad4	M-Pesa Settlement Account	KES	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
08e5ca54-9cad-4bec-b780-f8fec1b62580	760bddbc-08e5-4041-8f81-d5b9cd28910d	MTN MoMo Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
c808444a-c9fc-413d-8139-5c53f7cfe379	684477fc-e858-4bc5-9885-533a44ee7b63	Orange Money Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
1904f136-95a0-4ce9-9dfa-832a1b0905cb	93733f18-5ebd-4cc8-b68b-5f0804148b88	Wave Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
241b6b61-680c-4175-b2a6-74a6ac0ca073	db197fc8-ee49-489f-8c04-b720cd3a8821	Ecobank Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
291ee6d5-e251-4050-972d-6df0ed012550	e8e286a9-9acf-4a1b-b876-2e5fe8f100a1	MFS Africa Settlement Account	XOF	{}	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
\.


--
-- Data for Name: providers; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.providers (provider_id, name, type, country_code, active, created_at, updated_at) FROM stdin;
ba504734-2303-4814-8ffe-11748582f13e	M-Pesa	mobile_money	KE	t	2025-11-01 13:26:15.821423+01	2025-11-01 13:26:15.821423+01
5e088311-c55f-4290-adc1-dddf5bad5722	MTN MoMo	mobile_money	CI	t	2025-11-01 13:26:15.821423+01	2025-11-01 13:26:15.821423+01
7e64ed8f-c823-4d41-8d80-50d5a00e877f	Orange Money	mobile_money	SN	t	2025-11-01 13:26:15.821423+01	2025-11-01 13:26:15.821423+01
ed6ba64e-330f-4485-9d65-42d1dea868fe	Wave	mobile_money	SN	t	2025-11-01 13:26:15.821423+01	2025-11-01 13:26:15.821423+01
735b219a-b5fc-4807-84c5-66ad6d8513f9	Ecobank	bank	CI	t	2025-11-01 13:26:15.821423+01	2025-11-01 13:26:15.821423+01
964c90eb-6534-4ffb-8dc0-00d43e4a3695	MFS Africa	aggregator	\N	t	2025-11-01 13:26:15.821423+01	2025-11-01 13:26:15.821423+01
89410bf3-7c1b-4cd1-9687-c3e7a86a4ad4	M-Pesa	mobile_money	KE	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
760bddbc-08e5-4041-8f81-d5b9cd28910d	MTN MoMo	mobile_money	CI	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
684477fc-e858-4bc5-9885-533a44ee7b63	Orange Money	mobile_money	SN	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
93733f18-5ebd-4cc8-b68b-5f0804148b88	Wave	mobile_money	SN	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
db197fc8-ee49-489f-8c04-b720cd3a8821	Ecobank	bank	CI	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
e8e286a9-9acf-4a1b-b876-2e5fe8f100a1	MFS Africa	aggregator	\N	t	2025-11-01 13:28:10.840141+01	2025-11-01 13:28:10.840141+01
\.


--
-- Data for Name: recon_files; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.recon_files (recon_id, provider_account_id, period_start, period_end, file_url, parsed_at, created_at) FROM stdin;
\.


--
-- Data for Name: recon_lines; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.recon_lines (recon_line_id, recon_id, external_ref, amount, currency_code, matched_tx, status, details) FROM stdin;
\.


--
-- Data for Name: sanctions_screening; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.sanctions_screening (screening_id, user_id, matched, provider, payload, created_at) FROM stdin;
\.


--
-- Data for Name: security_events; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.security_events (event_id, user_id, severity, event_type, message, context, created_at) FROM stdin;
a71b35aa-e720-431c-ae3d-6e72be6db4dd	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 13:27:52.881941+01
e541c7da-fb22-4ad9-a52a-d40cffa84b1a	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 13:42:07.487251+01
c859ce83-c7c7-4217-ad61-85a10278118e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 13:57:52.857001+01
f766fd5d-505f-4b9d-8c99-ac8a4654e638	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:04:08.09481+01
2fc86854-5c8b-4843-830a-9628c02f7d7e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:05:09.304546+01
2229b2bc-f6c6-4634-b30c-bfd130753ffe	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:06:44.547926+01
fd8866ce-ab71-4682-8f0d-66d0fb805472	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:06:52.443063+01
c6d49e75-db55-4391-924f-3d6dd8705d00	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:06:53.56961+01
69cb073d-c90a-4937-86ad-e178e4d9ac5e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:07:35.645684+01
c7e65e41-3cc1-4262-a72e-78da56bcdcbb	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:14:04.322827+01
7477aebd-e3c7-4fb9-960b-3b4b1a5c194f	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:16:03.779576+01
37289d08-20b2-4cdb-92ce-488b52df0aa2	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 14:18:25.918081+01
7105d1b6-c461-4126-8f26-859d4ab5f164	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 15:39:27.262273+01
eb3585e0-216e-4fc3-9a0b-a57a1191d53e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 16:28:28.686743+01
aa799ad3-41a1-43c0-abaa-0aa338582ec7	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 16:31:09.725204+01
155886b6-1dca-456a-a0b3-74109a61e645	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 16:33:02.748252+01
0c5c3de5-7a51-4929-87c9-64749d38ae63	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 16:35:49.708092+01
c4a033af-bdd7-4211-ba1d-b7ce379910b4	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 16:39:05.760082+01
792e4d0a-df3d-4586-91bb-b4850660da9f	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-14 16:39:40.191991+01
9f820df1-93b7-438c-ad45-adc2766ac25e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:21:39.874102+01
88f94c1d-b412-4641-9c29-1192f81768c6	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:28:39.662865+01
0a180655-eb9f-4bec-b18a-c53591bb52b1	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:30:58.788619+01
883fb01a-4200-4f5c-8e5e-5afe08e0b1a0	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:32:56.67467+01
2f6f953e-eb56-4400-b8df-1982d61b448d	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:40:11.088826+01
136ef5a5-6bba-49b9-b531-360c41fd94ae	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:43:26.315933+01
ea19b39b-8302-47ef-b92a-65f508fc08f4	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 09:53:44.952021+01
218c15be-1de8-47d1-ac21-422368a95563	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 10:07:41.829364+01
cb00a8ca-0037-4d9c-85c5-611700f85084	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 10:08:27.370544+01
bb7ff326-57d4-4cb5-bcfd-5198b91a7221	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 10:14:17.311421+01
94adeffa-c2f7-49e1-a9b3-7ff48a1ac958	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 10:16:34.784067+01
01e34659-63c3-4894-983f-bcf5bb7478c2	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 11:10:08.679081+01
c8b1a86d-c130-4197-b95a-7cee14f1e43b	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 11:11:50.680207+01
8b3fa945-c56a-421c-90f4-25f922a42b4f	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 11:17:30.608889+01
3d4c9846-16d9-4f37-b9ac-21995bf85a9a	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 11:19:37.921084+01
d1037c05-9d50-402e-b471-ad252fb8c52e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 11:23:50.964329+01
2598fa1a-6720-4988-adb6-c5616f05530e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 19:22:57.589973+01
1d521f6b-f106-48e4-ae32-7bca3be621f3	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 21:50:42.064777+01
4556b59f-74e7-48cc-8e59-964d1b99b4b1	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-15 21:55:17.344344+01
86d39d66-9424-4c44-af0a-1c761ec0c37e	f3967721-8de9-453e-9f0b-1431cbf5197e	LOW	risk_update	Risk score 0 → 35 (Δ=35)	"{\\"message\\": \\"Risk score 0 \\\\u2192 35 (\\\\u0394=35)\\", \\"old_score\\": 0.0, \\"new_score\\": 35.0}"	2025-11-16 20:04:25.305403+01
\.


--
-- Data for Name: security_logs; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.security_logs (log_id, user_id, event_type, severity, message, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: settlements; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.settlements (settlement_id, provider_account_id, currency_code, amount, scheduled_at, executed_at, status) FROM stdin;
\.


--
-- Data for Name: tontine_contributions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.tontine_contributions (contribution_id, tontine_id, user_id, tx_id, amount, paid_at, status, created_at) FROM stdin;
ac047331-0c09-4ee5-a8e2-f19cfbba4ac5	ab394ed0-4277-448a-94ea-8cc3dfc1d548	a13f6f47-6f61-444e-8c68-389cb3df46db	\N	50.000000	2025-10-24 22:32:23.565319+02	paid	15:27:23.216073+01
cb4191c2-c10f-4ddc-8258-4fb65f4816c4	ab394ed0-4277-448a-94ea-8cc3dfc1d548	0454c830-0c4e-4484-a763-8941b2a52bbc	\N	50.000000	2025-10-25 22:32:23.565319+02	paid	15:27:23.216073+01
de6e310c-4919-4012-9f9a-c18385e1b57b	ab394ed0-4277-448a-94ea-8cc3dfc1d548	10ae9170-f6cc-4035-91c2-cb9e4e40d151	\N	50.000000	2025-10-26 22:32:23.565319+01	pending	15:27:23.216073+01
03882ad4-723c-42af-acbb-20ff2d142182	ab394ed0-4277-448a-94ea-8cc3dfc1d548	c2695741-9701-4c4b-9f46-ee43635ce13a	\N	0.000000	2025-10-27 22:32:23.565319+01	promised	15:27:23.216073+01
292e5262-e4ca-4e2d-bd05-8fe7085be1b5	d923d341-ff49-40d4-8b50-1767b1320593	0454c830-0c4e-4484-a763-8941b2a52bbc	\N	25.000000	2025-10-28 22:34:41.223067+01	paid	15:27:23.216073+01
59216bc5-6d73-4ab3-8e6d-0d0bea22f791	d923d341-ff49-40d4-8b50-1767b1320593	bad3ac22-69da-454d-874b-09b4307fcfd2	\N	50.000000	2025-10-29 22:34:41.223067+01	paid	15:27:23.216073+01
8825c86b-2842-465c-bc52-b5628264c9f8	d923d341-ff49-40d4-8b50-1767b1320593	ef6b63db-ebb9-45a9-814d-61b186567bb6	\N	45.000000	2025-10-30 22:34:41.223067+01	paid	15:27:23.216073+01
\.


--
-- Data for Name: tontine_invitations; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.tontine_invitations (invitation_id, tontine_id, created_by, invite_code, created_at, accepted_at, accepted_by) FROM stdin;
\.


--
-- Data for Name: tontine_members; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.tontine_members (tontine_id, user_id, is_online, member_id, user_name, phone, joined_at, join_order) FROM stdin;
ab394ed0-4277-448a-94ea-8cc3dfc1d548	a13f6f47-6f61-444e-8c68-389cb3df46db	f	b1b0dd95-d8d5-4d5b-8d8c-23281d14214f	Alice Bisimwa	+25771234567	22:30:37.493734+02	1
ab394ed0-4277-448a-94ea-8cc3dfc1d548	0454c830-0c4e-4484-a763-8941b2a52bbc	f	4a21c413-2ecc-4b43-af39-28b9c32bcd06	Bob Kamanzi	+25771234568	22:30:37.493734+02	1
ab394ed0-4277-448a-94ea-8cc3dfc1d548	10ae9170-f6cc-4035-91c2-cb9e4e40d151	f	47fcd8fa-835f-4819-b7d4-3b2c1f028258	Carla Uwimana	+25771234569	22:30:37.493734+02	1
ab394ed0-4277-448a-94ea-8cc3dfc1d548	c2695741-9701-4c4b-9f46-ee43635ce13a	f	7d572590-5374-4a36-a023-bebb33cb6bad	Dan Ndayishimiye	+25771234570	22:30:37.493734+02	1
d923d341-ff49-40d4-8b50-1767b1320593	0454c830-0c4e-4484-a763-8941b2a52bbc	f	f267bf2f-1398-44a5-92cc-31cd52dbf445	Bob Kamanzi	+25771234568	22:31:26.649938+02	1
d923d341-ff49-40d4-8b50-1767b1320593	bad3ac22-69da-454d-874b-09b4307fcfd2	f	c827420f-6729-4082-a21a-90f5f310ffd2	Emma Hakizimana	+25771234571	22:31:26.649938+02	1
d923d341-ff49-40d4-8b50-1767b1320593	ef6b63db-ebb9-45a9-814d-61b186567bb6	f	36780816-30c3-432d-9098-0cb9e7ba17f7	Frank Ndizeye	+25771234572	22:31:26.649938+02	1
\.


--
-- Data for Name: tontine_payouts; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.tontine_payouts (payout_id, tontine_id, beneficiary_id, tx_id, amount, scheduled_at, paid_at) FROM stdin;
c2ab6d7b-6636-4823-9957-715805a0fe99	ab394ed0-4277-448a-94ea-8cc3dfc1d548	a13f6f47-6f61-444e-8c68-389cb3df46db	\N	150.000000	\N	2025-10-18 22:36:13.879862+02
\.


--
-- Data for Name: tontine_rotations; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.tontine_rotations (id, tontine_id, user_id, order_index, has_received, received_at, has_paid, rotation_at) FROM stdin;
d8fc6175-b485-4ece-9f46-f4103fd9fbc7	ab394ed0-4277-448a-94ea-8cc3dfc1d548	a13f6f47-6f61-444e-8c68-389cb3df46db	0	t	\N	t	22:42:36.95411+02
26af05cd-c648-412f-a801-5253b3c70d06	ab394ed0-4277-448a-94ea-8cc3dfc1d548	0454c830-0c4e-4484-a763-8941b2a52bbc	1	f	\N	t	22:42:36.95411+02
f955c1da-8626-474f-b6ef-36bb3b0a86a5	ab394ed0-4277-448a-94ea-8cc3dfc1d548	10ae9170-f6cc-4035-91c2-cb9e4e40d151	2	f	\N	f	22:42:36.95411+01
392d37e6-5149-4980-b3a9-1d8fdac33687	ab394ed0-4277-448a-94ea-8cc3dfc1d548	c2695741-9701-4c4b-9f46-ee43635ce13a	3	f	\N	f	22:42:36.95411+01
\.


--
-- Data for Name: tontines; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.tontines (tontine_id, owner_user, name, currency_code, periodicity_days, status, created_at, updated_at, rotation_order, current_round, common_pot, tontine_type, next_rotation_at, last_rotation_at, amount_per_member) FROM stdin;
ab394ed0-4277-448a-94ea-8cc3dfc1d548	f3967721-8de9-453e-9f0b-1431cbf5197e	Tontine Umoja (rotative)	BIF	7	draft	2025-10-08 22:19:21.291889+02	2025-11-07 23:36:50.8329+01	\N	0	0.000000	rotative	2025-11-09 22:19:21.291889+01	22:19:21.291889+02	50.00
d923d341-ff49-40d4-8b50-1767b1320593	f3967721-8de9-453e-9f0b-1431cbf5197e	Tontine Epargne Amahoro	BIF	30	draft	2025-10-20 22:19:21.291889+02	2025-11-07 23:36:50.8329+01	\N	0	120.000000	epargne	\N	22:19:21.291889+02	25.00
\.


--
-- Data for Name: transactions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.transactions (tx_id, initiated_by, sender_wallet, receiver_wallet, amount, currency_code, channel, status, description, created_at, updated_at, related_entity_id) FROM stdin;
3f87f8b0-fda8-48f1-bdd5-db8f215636d1	ca1f45a3-5c54-4b46-9b57-e2105c226f84	\N	0b17e897-079c-4f91-a419-f0cae9e6c5e7	3000000.000000	BIF	cash	succeeded	Dépôt agent - Parent Burundais	2025-11-01 13:30:31.263726+01	2025-11-01 13:30:31.263726+01	\N
eaaea6f7-3cc3-49eb-ae0b-4a8a3de73263	ca1f45a3-5c54-4b46-9b57-e2105c226f84	0b17e897-079c-4f91-a419-f0cae9e6c5e7	011eb6ce-82de-4802-bfc5-81821d9292f2	3000000.000000	BIF	mobile_money	succeeded	Transfert Parent → Étudiant (BIF→CDF)	2025-11-01 13:30:31.263726+01	2025-11-01 13:30:31.263726+01	\N
e4028a62-1e40-4309-b009-b2aa46da2176	aa428532-3964-499c-a178-c26861a82551	48e4fb8b-58c2-445a-9278-0e6258b60b38	0b17e897-079c-4f91-a419-f0cae9e6c5e7	1000.000000	USD	card	succeeded	Transfert diaspora → parent (USD→BIF)	2025-11-01 13:31:00.001471+01	2025-11-01 13:31:00.001471+01	\N
447766f5-d245-42a5-8c5c-45676e92814f	cb830e57-94fb-457a-8391-b10f2367a637	3bbcd219-5601-4018-9f03-a93eb0741381	ca19b78e-9fcb-45ff-8514-938eab8f9273	120000.000000	KES	bank	succeeded	Paiement inter-pays (Rwanda → Côte d’Ivoire)	2025-11-01 13:34:14.430737+01	2025-11-01 13:34:14.430737+01	\N
636c3921-81f7-40d8-960b-b9daf8dad6b1	8ec91346-e0bf-4478-84f9-0412e12cf113	011eb6ce-82de-4802-bfc5-81821d9292f2	c517ed5b-8025-4218-b226-1b55586faf98	350000.000000	CDF	mobile_money	succeeded	Paiement des frais universitaires	2025-11-01 13:45:48.922271+01	2025-11-01 13:45:48.922271+01	\N
5e875a98-1d8d-4e9f-9e88-a566ce1a4c93	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	25.000000	EUR	external_transfer	pending	\N	2025-11-15 10:16:34.887884+01	2025-11-15 10:16:34.887884+01	4e9c3f42-6f90-463d-9edd-a0daec7d83a3
34a85ee4-e314-4129-9d27-4316f4d12891	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 11:10:08.718818+01	2025-11-15 11:10:08.718818+01	a866550e-11ac-4ed9-a2cc-75f0bdc074d7
2ab01f45-e38e-4f0c-9bea-e4c28f78c950	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 11:11:50.696978+01	2025-11-15 11:11:50.696978+01	45103cf9-7f6a-46ee-b006-1e1ac51628f4
dbfaa84d-a5d8-40bb-8a43-ad1246d9569d	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 11:17:30.655414+01	2025-11-15 11:17:30.655414+01	982b6744-76cd-4dd7-a950-d2fff146228e
e6700255-57b2-410d-8978-89701c05524f	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 11:19:37.972142+01	2025-11-15 11:19:37.972142+01	19c2d2cb-61a7-4387-9454-ae03cd695e37
a3af0083-798b-4bc9-bb4d-39ae769d81b9	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 11:23:50.977842+01	2025-11-15 11:23:50.977842+01	59918dde-8c45-49bd-a28d-54f0f6ad4861
2587bb78-f147-4980-8f99-d0a7fb755847	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 19:22:57.640489+01	2025-11-15 19:22:57.640489+01	b03f6ec2-4f92-4643-834d-0525ec93d0c4
39d4d0ba-eaf6-456c-a8c8-7c5c8d10dd4f	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	50.000000	EUR	external_transfer	pending	\N	2025-11-15 21:50:42.138477+01	2025-11-15 21:50:42.138477+01	61ce0628-98a2-4bcf-aa7b-bf178b420fba
5ba8c5d2-b5dc-4d5c-b63c-04bc916533da	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	100.000000	EUR	external_transfer	pending	\N	2025-11-15 21:55:17.389381+01	2025-11-15 21:55:17.389381+01	34e39e5a-4efb-434e-b698-1800c42004b9
bb3bdeb2-c83c-4e4a-8c65-1d78e2651471	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	\N	100.000000	EUR	external_transfer	pending	\N	2025-11-16 20:04:25.424289+01	2025-11-16 20:04:25.424289+01	08ef915c-7624-4506-a95c-9e561e4f7ccb
\.


--
-- Data for Name: user_auth; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.user_auth (user_id, password_hash, mfa_enabled, last_login_at) FROM stdin;
a13f6f47-6f61-444e-8c68-389cb3df46db	$2a$06$Ge2aQMJXmEfSVF1eiApZKO1v9wfpD7rNrja69y/RwkzHJ..wSr/Ru	f	\N
0454c830-0c4e-4484-a763-8941b2a52bbc	$2a$06$A9B41T4v2ebXZsDuVtX/nuAIqy3TWt6yX1/NPOvYizlNida7EWs1i	f	\N
10ae9170-f6cc-4035-91c2-cb9e4e40d151	$2a$06$hDFCztdPkjJM52RsvOLL8uEsusejXVWi0vgnwWIBEzPZuuPyy.0ym	f	\N
c2695741-9701-4c4b-9f46-ee43635ce13a	$2a$06$pDs79yQSxW/Cten1GNLGN.b6jas6Td0ceybAnaee9FGJeCnIfspzC	f	\N
f3967721-8de9-453e-9f0b-1431cbf5197e	$2b$12$Nvr7LRX73Ts/gI276noBxePq/KKuEmupSGQA97aRwoLpr0UaKODrC	f	2025-11-17 18:10:40.021174+01
0d7da96c-1760-4e8c-8947-cadf39910938	$2b$12$Nvr7LRX73Ts/gI276noBxePq/KKuEmupSGQA97aRwoLpr0UaKODrC	f	2025-11-17 18:12:23.641124+01
cd4d7154-9d5e-4c3a-bb38-aad84014e92b	$2b$12$Nvr7LRX73Ts/gI276noBxePq/KKuEmupSGQA97aRwoLpr0UaKODrC	f	2025-11-17 18:14:27.607305+01
41b2dfa7-eb3c-4633-bffc-6c90229f8182	$2b$12$zJRCeyPF8JZNVNeIMc8WIOFFZLA1hg1XXNu97XL874d13E0CAwXKa	f	\N
\.


--
-- Data for Name: user_devices; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.user_devices (device_id, user_id, device_fingerprint, push_token, created_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.users (user_id, status, full_name, email, phone_e164, country_code, kyc_status, referred_by, created_at, updated_at, role, credit_limit, credit_used, last_seen, legal_name, birth_date, national_id_number, kyc_document_type, kyc_document_front_url, kyc_document_back_url, selfie_url, kyc_reject_reason, kyc_tier, daily_limit, monthly_limit, used_daily, used_monthly, last_reset, risk_score, external_transfers_blocked, paytag, kyc_submitted_at) FROM stdin;
a0633588-72b9-4ca1-921f-b79d91b4fb53	active	Jean Nduwimana	jean.ndu@paylink.bi	+25779900123	BI	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
ceac05ae-872c-4eff-aa69-de251deb50c7	active	Marie Mbayo	marie.mbayo@paylink.cd	+24381002233	CD	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
50cc3f16-d8eb-4582-8a3c-62102e39a3a2	active	Awa Diop	awa.diop@paylink.sn	+22177001122	SN	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
cb830e57-94fb-457a-8391-b10f2367a637	active	Kevin Mwangi	kevin.mwangi@paylink.ke	+254710054321	KE	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
ca1f45a3-5c54-4b46-9b57-e2105c226f84	active	Parent Burundais	parent@paylink.bi	+25778800111	BI	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
8ec91346-e0bf-4478-84f9-0412e12cf113	active	Étudiant à Kinshasa	etudiant@paylink.cd	+24381222222	CD	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
aa428532-3964-499c-a178-c26861a82551	active	Diaspora USA	diaspora@paylink.us	+13479998888	BI	verified	\N	2025-11-01 13:28:41.304359+01	2025-11-01 13:28:41.304359+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
a13f6f47-6f61-444e-8c68-389cb3df46db	pending	Alice Bisimwa	alice@example.com	+25771234567	BI	unverified	\N	2025-09-28 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	user	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
0454c830-0c4e-4484-a763-8941b2a52bbc	pending	Bob Kamanzi	bob@example.com	+25771234568	BI	unverified	\N	2025-09-30 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	user	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
10ae9170-f6cc-4035-91c2-cb9e4e40d151	pending	Carla Uwimana	carla@example.com	+25771234569	BI	unverified	\N	2025-10-02 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	user	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
c2695741-9701-4c4b-9f46-ee43635ce13a	pending	Dan Ndayishimiye	dan@example.com	+25771234570	BI	unverified	\N	2025-10-04 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	user	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
bad3ac22-69da-454d-874b-09b4307fcfd2	pending	Emma Hakizimana	emma@example.com	+25771234571	BI	unverified	\N	2025-10-10 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	user	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
ef6b63db-ebb9-45a9-814d-61b186567bb6	pending	Frank Ndizeye	frank@example.com	+25771234572	BI	unverified	\N	2025-10-18 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	user	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
cd4d7154-9d5e-4c3a-bb38-aad84014e92b	pending	Admin PayLink	admin@example.com	+25770000000	BI	unverified	\N	2025-07-30 22:17:01.12648+02	2025-11-07 22:17:01.12648+01	admin	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
41b2dfa7-eb3c-4633-bffc-6c90229f8182	active	NAHIMANA ADO	naphe155@yahoo.fr	+32470066843	BE	unverified	\N	2025-11-12 18:38:50.214146+01	2025-11-12 18:38:50.214146+01	client	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-12	0	f	\N	2025-11-15 11:59:50.060874+01
f3967721-8de9-453e-9f0b-1431cbf5197e	active	Adolphe Nahimana	naphe12@yahoo.fr	+32412345678	BE	verified	\N	2025-11-02 17:11:00.244292+01	2025-11-15 11:55:36.916169+01	client	0.00	0.00	\N	Nahimana 	1970-09-20	4567834BE	national_id	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	20	f	\N	2025-11-15 11:59:50.060874+01
0d7da96c-1760-4e8c-8947-cadf39910938	active	Agent Stone	adolphe.nahimana@yahoo.fr	+25771111111	BI	verified	\N	2025-10-28 22:17:01.12648+01	2025-11-15 19:28:11.868+01	agent	0.00	0.00	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	30000	30000	0	0	2025-11-08	0	f	\N	2025-11-15 11:59:50.060874+01
\.


--
-- Data for Name: wallet_bonus_history; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.wallet_bonus_history (bonus_id, user_id, wallet_id, amount_bif, source, related_transfer_id, created_at) FROM stdin;
\.


--
-- Data for Name: wallet_cash_requests; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.wallet_cash_requests (request_id, user_id, wallet_id, type, status, amount, fee_amount, total_amount, currency_code, mobile_number, provider_name, note, admin_note, metadata, processed_by, processed_at, created_at) FROM stdin;
e2463283-dfcb-41a3-af68-57beca75619c	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	DEPOSIT	APPROVED	100.000000	0.000000	100.000000	EUR	\N	\N	\N	\N	{}	cd4d7154-9d5e-4c3a-bb38-aad84014e92b	2025-11-15 19:05:36.008185+01	2025-11-15 18:51:24.731265+01
a8a28b70-acb1-4567-8e81-400c4efff174	f3967721-8de9-453e-9f0b-1431cbf5197e	48e4fb8b-58c2-445a-9278-0e6258b60b38	WITHDRAW	APPROVED	100.000000	6.250000	106.250000	EUR	67225225	Lumicash	retrait	\N	{}	cd4d7154-9d5e-4c3a-bb38-aad84014e92b	2025-11-15 19:06:10.372706+01	2025-11-15 18:52:27.841592+01
\.


--
-- Data for Name: wallet_transactions; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.wallet_transactions (transaction_id, wallet_id, user_id, operation_type, amount, currency_code, description, reference, created_at, direction, balance_after) FROM stdin;
506fecb4-c589-416a-9aba-87cdaa0f359b	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	25.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 10:16:34.887884+01	DEBIT	975.00
c8883fed-d3c7-4dbe-a02e-397369246901	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 11:10:08.718818+01	DEBIT	925.00
3e697015-8652-4750-ba35-f3b2bb8de897	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 11:11:50.696978+01	DEBIT	875.00
c456d379-ea0f-4dbb-b994-8ce93c6aca58	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 11:17:30.655414+01	DEBIT	825.00
32cfdd21-4eba-4a89-8753-2edc9dfc8bc1	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 11:19:37.972142+01	DEBIT	775.00
57e2c102-3401-456e-b0bb-5c5407a848d8	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 11:23:50.977842+01	DEBIT	725.00
89bb6026-a43f-4b6d-a83a-a8dca56cd2bf	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	cash_deposit_admin	100.00	EUR	Validation dépôt cash	cash_deposit	2025-11-15 19:05:35.96858+01	credit	825.00
c5fa80bf-0de7-4fbe-9e60-9819ee5347c7	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	cash_withdraw_admin	106.25	EUR	Validation retrait cash	Lumicash	2025-11-15 19:06:10.329575+01	debit	718.75
c5cbca94-51bb-46e4-8294-7aebcb6f29ac	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 19:22:57.640489+01	DEBIT	668.75
13c57269-cf7e-4695-9ed0-f536b0f11542	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	50.00	EUR	Transfert externe vers Nahayo	Lumicash	2025-11-15 21:50:42.138477+01	DEBIT	618.75
71cbeddb-0bd3-4638-865f-959f11e6ee67	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	100.00	EUR	Transfert externe vers Bukuru	Lumicash	2025-11-15 21:55:17.389381+01	DEBIT	518.75
723d43f9-5563-4b43-b963-d056ef011513	48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	external_transfer	100.00	EUR	Transfert externe vers Bukomezwa	Lumicash	2025-11-16 20:04:25.424289+01	DEBIT	418.75
\.


--
-- Data for Name: wallets; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.wallets (wallet_id, user_id, type, currency_code, available, pending, created_at, updated_at, bonus_balance) FROM stdin;
e7fa4789-5bcd-4a0f-903b-6f3115272325	a0633588-72b9-4ca1-921f-b79d91b4fb53	consumer	BIF	2500000.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 13:29:16.089182+01	0.00
c517ed5b-8025-4218-b226-1b55586faf98	ceac05ae-872c-4eff-aa69-de251deb50c7	consumer	CDF	2000000.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 13:29:16.089182+01	0.00
ca19b78e-9fcb-45ff-8514-938eab8f9273	50cc3f16-d8eb-4582-8a3c-62102e39a3a2	consumer	XOF	1000000.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 13:29:16.089182+01	0.00
3bbcd219-5601-4018-9f03-a93eb0741381	cb830e57-94fb-457a-8391-b10f2367a637	consumer	KES	150000.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 13:29:16.089182+01	0.00
61ccddd3-b6cf-4868-9b14-9c6f60229d6a	aa428532-3964-499c-a178-c26861a82551	consumer	BIF	2500000.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 13:29:16.089182+01	0.00
0b17e897-079c-4f91-a419-f0cae9e6c5e7	ca1f45a3-5c54-4b46-9b57-e2105c226f84	consumer	BIF	6001980.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 23:44:33.952256+01	0.00
011eb6ce-82de-4802-bfc5-81821d9292f2	8ec91346-e0bf-4478-84f9-0412e12cf113	consumer	CDF	9180000.000000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-01 23:44:33.952256+01	0.00
663e3a6c-39cf-4f2c-bef2-34cbb3c8fe4d	bad3ac22-69da-454d-874b-09b4307fcfd2	consumer	EUR	0.000000	0.000000	2025-11-12 18:35:54.318227+01	2025-11-15 23:15:03.298628+01	0.00
0044ead2-23a8-4e37-aa86-a067a3ddcbea	c2695741-9701-4c4b-9f46-ee43635ce13a	consumer	EUR	0.000000	0.000000	2025-11-12 17:48:13.855452+01	2025-11-15 23:15:46.11548+01	0.00
9dfe2f2c-d690-43b2-8399-58e5a67233cf	41b2dfa7-eb3c-4633-bffc-6c90229f8182	consumer	EUR	0.000000	0.000000	2025-11-12 18:38:50.214146+01	2025-11-12 18:38:50.214146+01	0.00
48e4fb8b-58c2-445a-9278-0e6258b60b38	f3967721-8de9-453e-9f0b-1431cbf5197e	consumer	EUR	418.750000	0.000000	2025-11-01 13:29:16.089182+01	2025-11-16 20:04:25.424289+01	28750.00
cd60f6cc-b517-498b-8d84-22f96c25b3ff	0d7da96c-1760-4e8c-8947-cadf39910938	agent	BIF	25000000.000000	0.000000	2025-11-16 20:36:10.50864+01	2025-11-16 20:36:10.50864+01	0.00
0e9b3673-411f-4258-99e1-f4f154492a42	cd4d7154-9d5e-4c3a-bb38-aad84014e92b	admin	EUR	0.000000	0.000000	2025-11-16 21:26:54.996657+01	2025-11-16 21:26:54.996657+01	0.00
\.


--
-- Data for Name: webhook_events; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.webhook_events (event_id, webhook_id, event_type, payload, attempt_count, last_attempt_at, status, created_at) FROM stdin;
\.


--
-- Data for Name: webhooks; Type: TABLE DATA; Schema: paylink; Owner: postgres
--

COPY paylink.webhooks (webhook_id, subscriber_url, event_types, secret, status, created_at) FROM stdin;
\.


--
-- Data for Name: telegram_users; Type: TABLE DATA; Schema: telegram; Owner: postgres
--

COPY telegram.telegram_users (id, chat_id, username, first_name, last_name, language_code, is_bot, created_at, updated_at) FROM stdin;
1	7600938538	adolphe	Adolphe	Nahimana	fr	t	2025-11-15 21:45:12.148948	2025-11-15 21:45:12.148948
\.


--
-- Name: logged_actions_audit_id_seq; Type: SEQUENCE SET; Schema: audit; Owner: postgres
--

SELECT pg_catalog.setval('audit.logged_actions_audit_id_seq', 16, true);


--
-- Name: agent_transactions_id_seq; Type: SEQUENCE SET; Schema: paylink; Owner: postgres
--

SELECT pg_catalog.setval('paylink.agent_transactions_id_seq', 1, false);


--
-- Name: fx_custom_rates_rate_id_seq; Type: SEQUENCE SET; Schema: paylink; Owner: postgres
--

SELECT pg_catalog.setval('paylink.fx_custom_rates_rate_id_seq', 1, true);


--
-- Name: fx_rates_fx_id_seq; Type: SEQUENCE SET; Schema: paylink; Owner: postgres
--

SELECT pg_catalog.setval('paylink.fx_rates_fx_id_seq', 4, true);


--
-- Name: ledger_entries_entry_id_seq; Type: SEQUENCE SET; Schema: paylink; Owner: postgres
--

SELECT pg_catalog.setval('paylink.ledger_entries_entry_id_seq', 66, true);


--
-- Name: limit_usage_id_seq; Type: SEQUENCE SET; Schema: paylink; Owner: postgres
--

SELECT pg_catalog.setval('paylink.limit_usage_id_seq', 1, false);


--
-- Name: recon_lines_recon_line_id_seq; Type: SEQUENCE SET; Schema: paylink; Owner: postgres
--

SELECT pg_catalog.setval('paylink.recon_lines_recon_line_id_seq', 1, false);


--
-- Name: telegram_users_id_seq; Type: SEQUENCE SET; Schema: telegram; Owner: postgres
--

SELECT pg_catalog.setval('telegram.telegram_users_id_seq', 1, true);


--
-- Name: logged_actions logged_actions_pkey; Type: CONSTRAINT; Schema: audit; Owner: postgres
--

ALTER TABLE ONLY audit.logged_actions
    ADD CONSTRAINT logged_actions_pkey PRIMARY KEY (audit_id);


--
-- Name: agent_commission_rates agent_commission_rates_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_commission_rates
    ADD CONSTRAINT agent_commission_rates_pkey PRIMARY KEY (id);


--
-- Name: agent_commissions agent_commissions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_commissions
    ADD CONSTRAINT agent_commissions_pkey PRIMARY KEY (commission_id);


--
-- Name: agent_locations agent_locations_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_locations
    ADD CONSTRAINT agent_locations_pkey PRIMARY KEY (location_id);


--
-- Name: agent_transactions agent_transactions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_transactions
    ADD CONSTRAINT agent_transactions_pkey PRIMARY KEY (id);


--
-- Name: agents agents_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agents
    ADD CONSTRAINT agents_pkey PRIMARY KEY (agent_id);


--
-- Name: agents agents_user_id_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agents
    ADD CONSTRAINT agents_user_id_key UNIQUE (user_id);


--
-- Name: aml_events aml_events_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.aml_events
    ADD CONSTRAINT aml_events_pkey PRIMARY KEY (aml_id);


--
-- Name: bill_payments bill_payments_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.bill_payments
    ADD CONSTRAINT bill_payments_pkey PRIMARY KEY (bill_payment_id);


--
-- Name: bonus_history bonus_history_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.bonus_history
    ADD CONSTRAINT bonus_history_pkey PRIMARY KEY (id);


--
-- Name: countries countries_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.countries
    ADD CONSTRAINT countries_pkey PRIMARY KEY (country_code);


--
-- Name: credit_line_history credit_line_history_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.credit_line_history
    ADD CONSTRAINT credit_line_history_pkey PRIMARY KEY (entry_id);


--
-- Name: currencies currencies_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.currencies
    ADD CONSTRAINT currencies_pkey PRIMARY KEY (currency_code);


--
-- Name: disputes disputes_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.disputes
    ADD CONSTRAINT disputes_pkey PRIMARY KEY (dispute_id);


--
-- Name: external_transfers external_transfers_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.external_transfers
    ADD CONSTRAINT external_transfers_pkey PRIMARY KEY (transfer_id);


--
-- Name: fee_schedules fee_schedules_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fee_schedules
    ADD CONSTRAINT fee_schedules_pkey PRIMARY KEY (fee_id);


--
-- Name: fx_conversions fx_conversions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_conversions
    ADD CONSTRAINT fx_conversions_pkey PRIMARY KEY (conversion_id);


--
-- Name: fx_custom_rates fx_custom_rates_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_custom_rates
    ADD CONSTRAINT fx_custom_rates_pkey PRIMARY KEY (rate_id);


--
-- Name: fx_rates fx_rates_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_rates
    ADD CONSTRAINT fx_rates_pkey PRIMARY KEY (fx_id);


--
-- Name: idempotency_keys idempotency_keys_client_key_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.idempotency_keys
    ADD CONSTRAINT idempotency_keys_client_key_key UNIQUE (client_key);


--
-- Name: idempotency_keys idempotency_keys_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.idempotency_keys
    ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (key_id);


--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (invoice_id);


--
-- Name: kyc_documents kyc_documents_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.kyc_documents
    ADD CONSTRAINT kyc_documents_pkey PRIMARY KEY (kyc_id);


--
-- Name: ledger_accounts ledger_accounts_code_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_accounts
    ADD CONSTRAINT ledger_accounts_code_key UNIQUE (code);


--
-- Name: ledger_accounts ledger_accounts_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_accounts
    ADD CONSTRAINT ledger_accounts_pkey PRIMARY KEY (account_id);


--
-- Name: ledger_entries ledger_entries_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_entries
    ADD CONSTRAINT ledger_entries_pkey PRIMARY KEY (entry_id);


--
-- Name: ledger_journal ledger_journal_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_journal
    ADD CONSTRAINT ledger_journal_pkey PRIMARY KEY (journal_id);


--
-- Name: limit_usage limit_usage_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.limit_usage
    ADD CONSTRAINT limit_usage_pkey PRIMARY KEY (id);


--
-- Name: limits limits_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.limits
    ADD CONSTRAINT limits_pkey PRIMARY KEY (limit_id);


--
-- Name: loan_repayments loan_repayments_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.loan_repayments
    ADD CONSTRAINT loan_repayments_pkey PRIMARY KEY (repayment_id);


--
-- Name: loans loans_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.loans
    ADD CONSTRAINT loans_pkey PRIMARY KEY (loan_id);


--
-- Name: merchants merchants_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.merchants
    ADD CONSTRAINT merchants_pkey PRIMARY KEY (merchant_id);


--
-- Name: merchants merchants_user_id_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.merchants
    ADD CONSTRAINT merchants_user_id_key UNIQUE (user_id);


--
-- Name: mobile_money_deposits mobile_money_deposits_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.mobile_money_deposits
    ADD CONSTRAINT mobile_money_deposits_pkey PRIMARY KEY (deposit_id);


--
-- Name: mobile_money_deposits mobile_money_deposits_reference_code_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.mobile_money_deposits
    ADD CONSTRAINT mobile_money_deposits_reference_code_key UNIQUE (reference_code);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (notification_id);


--
-- Name: payment_instructions payment_instructions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.payment_instructions
    ADD CONSTRAINT payment_instructions_pkey PRIMARY KEY (pi_id);


--
-- Name: provider_accounts provider_accounts_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.provider_accounts
    ADD CONSTRAINT provider_accounts_pkey PRIMARY KEY (provider_account_id);


--
-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (provider_id);


--
-- Name: recon_files recon_files_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_files
    ADD CONSTRAINT recon_files_pkey PRIMARY KEY (recon_id);


--
-- Name: recon_lines recon_lines_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_lines
    ADD CONSTRAINT recon_lines_pkey PRIMARY KEY (recon_line_id);


--
-- Name: sanctions_screening sanctions_screening_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.sanctions_screening
    ADD CONSTRAINT sanctions_screening_pkey PRIMARY KEY (screening_id);


--
-- Name: security_events security_events_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.security_events
    ADD CONSTRAINT security_events_pkey PRIMARY KEY (event_id);


--
-- Name: security_events security_events_severity_check_2; Type: CHECK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE paylink.security_events
    ADD CONSTRAINT security_events_severity_check_2 CHECK ((severity = ANY (ARRAY['info'::text, 'warning'::text, 'critical'::text, 'LOW'::text, 'HIGH'::text, 'MEDIUM'::text, 'low'::text, 'medium'::text, 'high'::text]))) NOT VALID;


--
-- Name: security_logs security_logs_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.security_logs
    ADD CONSTRAINT security_logs_pkey PRIMARY KEY (log_id);


--
-- Name: settlements settlements_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.settlements
    ADD CONSTRAINT settlements_pkey PRIMARY KEY (settlement_id);


--
-- Name: tontine_contributions tontine_contributions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_contributions
    ADD CONSTRAINT tontine_contributions_pkey PRIMARY KEY (contribution_id);


--
-- Name: tontine_invitations tontine_invitations_invite_code_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_invitations
    ADD CONSTRAINT tontine_invitations_invite_code_key UNIQUE (invite_code);


--
-- Name: tontine_invitations tontine_invitations_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_invitations
    ADD CONSTRAINT tontine_invitations_pkey PRIMARY KEY (invitation_id);


--
-- Name: tontine_members tontine_members_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_members
    ADD CONSTRAINT tontine_members_pkey PRIMARY KEY (tontine_id, user_id);


--
-- Name: tontine_payouts tontine_payouts_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_payouts
    ADD CONSTRAINT tontine_payouts_pkey PRIMARY KEY (payout_id);


--
-- Name: tontine_rotations tontine_rotations_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_rotations
    ADD CONSTRAINT tontine_rotations_pkey PRIMARY KEY (id);


--
-- Name: tontines tontines_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontines
    ADD CONSTRAINT tontines_pkey PRIMARY KEY (tontine_id);


--
-- Name: transactions transactions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (tx_id);


--
-- Name: user_auth user_auth_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.user_auth
    ADD CONSTRAINT user_auth_pkey PRIMARY KEY (user_id);


--
-- Name: user_devices user_devices_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.user_devices
    ADD CONSTRAINT user_devices_pkey PRIMARY KEY (device_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_paytag_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.users
    ADD CONSTRAINT users_paytag_key UNIQUE (paytag);


--
-- Name: users users_phone_e164_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.users
    ADD CONSTRAINT users_phone_e164_key UNIQUE (phone_e164);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: wallet_bonus_history wallet_bonus_history_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_bonus_history
    ADD CONSTRAINT wallet_bonus_history_pkey PRIMARY KEY (bonus_id);


--
-- Name: wallet_cash_requests wallet_cash_requests_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_cash_requests
    ADD CONSTRAINT wallet_cash_requests_pkey PRIMARY KEY (request_id);


--
-- Name: wallet_transactions wallet_transactions_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_transactions
    ADD CONSTRAINT wallet_transactions_pkey PRIMARY KEY (transaction_id);


--
-- Name: wallets wallets_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallets
    ADD CONSTRAINT wallets_pkey PRIMARY KEY (wallet_id);


--
-- Name: wallets wallets_user_id_currency_code_type_key; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallets
    ADD CONSTRAINT wallets_user_id_currency_code_type_key UNIQUE (user_id, currency_code, type);


--
-- Name: webhook_events webhook_events_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.webhook_events
    ADD CONSTRAINT webhook_events_pkey PRIMARY KEY (event_id);


--
-- Name: webhooks webhooks_pkey; Type: CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.webhooks
    ADD CONSTRAINT webhooks_pkey PRIMARY KEY (webhook_id);


--
-- Name: telegram_users telegram_users_chat_id_key; Type: CONSTRAINT; Schema: telegram; Owner: postgres
--

ALTER TABLE ONLY telegram.telegram_users
    ADD CONSTRAINT telegram_users_chat_id_key UNIQUE (chat_id);


--
-- Name: telegram_users telegram_users_pkey; Type: CONSTRAINT; Schema: telegram; Owner: postgres
--

ALTER TABLE ONLY telegram.telegram_users
    ADD CONSTRAINT telegram_users_pkey PRIMARY KEY (id);


--
-- Name: idx_entries_account; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_entries_account ON paylink.ledger_entries USING btree (account_id);


--
-- Name: idx_entries_journal; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_entries_journal ON paylink.ledger_entries USING btree (journal_id);


--
-- Name: idx_fee_filters; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_fee_filters ON paylink.fee_schedules USING btree (channel, provider_id, country_code, currency_code);


--
-- Name: idx_fx_pair_time; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_fx_pair_time ON paylink.fx_rates USING btree (base_currency, quote_currency, obtained_at DESC);


--
-- Name: idx_invoices_merchant; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_invoices_merchant ON paylink.invoices USING btree (merchant_id, status);


--
-- Name: idx_kyc_user; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_kyc_user ON paylink.kyc_documents USING btree (user_id);


--
-- Name: idx_limit_usage_user_day; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_limit_usage_user_day ON paylink.limit_usage USING btree (user_id, day);


--
-- Name: idx_limit_usage_user_month; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_limit_usage_user_month ON paylink.limit_usage USING btree (user_id, month);


--
-- Name: idx_pi_status; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_pi_status ON paylink.payment_instructions USING btree (status);


--
-- Name: idx_pi_tx; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_pi_tx ON paylink.payment_instructions USING btree (tx_id);


--
-- Name: idx_provider_accounts_provider; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_provider_accounts_provider ON paylink.provider_accounts USING btree (provider_id);


--
-- Name: idx_providers_type; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_providers_type ON paylink.providers USING btree (type);


--
-- Name: idx_recon_lines_ref; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_recon_lines_ref ON paylink.recon_lines USING btree (external_ref);


--
-- Name: idx_security_events_severity; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_security_events_severity ON paylink.security_events USING btree (severity);


--
-- Name: idx_security_events_type; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_security_events_type ON paylink.security_events USING btree (event_type);


--
-- Name: idx_security_events_user; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_security_events_user ON paylink.security_events USING btree (user_id);


--
-- Name: idx_tx_receiver; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_tx_receiver ON paylink.transactions USING btree (receiver_wallet);


--
-- Name: idx_tx_sender; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_tx_sender ON paylink.transactions USING btree (sender_wallet);


--
-- Name: idx_tx_status; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_tx_status ON paylink.transactions USING btree (status);


--
-- Name: idx_users_country; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_users_country ON paylink.users USING btree (country_code);


--
-- Name: idx_users_phone; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_users_phone ON paylink.users USING btree (phone_e164);


--
-- Name: idx_wallet_tx_user; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_wallet_tx_user ON paylink.wallet_transactions USING btree (user_id);


--
-- Name: idx_wallet_tx_wallet; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_wallet_tx_wallet ON paylink.wallet_transactions USING btree (wallet_id);


--
-- Name: idx_wallets_currency; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_wallets_currency ON paylink.wallets USING btree (currency_code);


--
-- Name: idx_wallets_user; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX idx_wallets_user ON paylink.wallets USING btree (user_id);


--
-- Name: wallet_bonus_history_user_id_idx; Type: INDEX; Schema: paylink; Owner: postgres
--

CREATE INDEX wallet_bonus_history_user_id_idx ON paylink.wallet_bonus_history USING btree (user_id);


--
-- Name: transactions audit_transactions; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER audit_transactions AFTER INSERT OR DELETE OR UPDATE ON paylink.transactions FOR EACH ROW EXECUTE FUNCTION audit.if_modified_func();


--
-- Name: countries trg_countries_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_countries_updated BEFORE UPDATE ON paylink.countries FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: currencies trg_currencies_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_currencies_updated BEFORE UPDATE ON paylink.currencies FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: disputes trg_disputes_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_disputes_updated BEFORE UPDATE ON paylink.disputes FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: invoices trg_invoices_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_invoices_updated BEFORE UPDATE ON paylink.invoices FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: kyc_documents trg_kyc_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_kyc_updated BEFORE UPDATE ON paylink.kyc_documents FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: limit_usage trg_limit_usage_update; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_limit_usage_update BEFORE UPDATE ON paylink.limit_usage FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: loans trg_loans_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_loans_updated BEFORE UPDATE ON paylink.loans FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: payment_instructions trg_pi_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_pi_updated BEFORE UPDATE ON paylink.payment_instructions FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: provider_accounts trg_provider_accounts_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_provider_accounts_updated BEFORE UPDATE ON paylink.provider_accounts FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: providers trg_providers_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_providers_updated BEFORE UPDATE ON paylink.providers FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: tontines trg_tontines_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_tontines_updated BEFORE UPDATE ON paylink.tontines FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: transactions trg_tx_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_tx_updated BEFORE UPDATE ON paylink.transactions FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: users trg_users_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON paylink.users FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: wallets trg_wallets_updated; Type: TRIGGER; Schema: paylink; Owner: postgres
--

CREATE TRIGGER trg_wallets_updated BEFORE UPDATE ON paylink.wallets FOR EACH ROW EXECUTE FUNCTION paylink.set_updated_at();


--
-- Name: agent_commission_rates agent_commission_rates_country_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_commission_rates
    ADD CONSTRAINT agent_commission_rates_country_code_fkey FOREIGN KEY (country_code) REFERENCES paylink.countries(country_code);


--
-- Name: agent_commissions agent_commissions_agent_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_commissions
    ADD CONSTRAINT agent_commissions_agent_user_id_fkey FOREIGN KEY (agent_user_id) REFERENCES paylink.users(user_id);


--
-- Name: agent_commissions agent_commissions_related_tx_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_commissions
    ADD CONSTRAINT agent_commissions_related_tx_fkey FOREIGN KEY (related_tx) REFERENCES paylink.transactions(tx_id);


--
-- Name: agent_locations agent_locations_agent_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_locations
    ADD CONSTRAINT agent_locations_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES paylink.agents(agent_id) ON DELETE CASCADE;


--
-- Name: agent_transactions agent_transactions_agent_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_transactions
    ADD CONSTRAINT agent_transactions_agent_id_fkey FOREIGN KEY (agent_user_id) REFERENCES paylink.agents(agent_id) ON DELETE CASCADE;


--
-- Name: agent_transactions agent_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agent_transactions
    ADD CONSTRAINT agent_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: agents agents_country_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agents
    ADD CONSTRAINT agents_country_code_fkey FOREIGN KEY (country_code) REFERENCES paylink.countries(country_code);


--
-- Name: agents agents_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.agents
    ADD CONSTRAINT agents_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: aml_events aml_events_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.aml_events
    ADD CONSTRAINT aml_events_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id);


--
-- Name: aml_events aml_events_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.aml_events
    ADD CONSTRAINT aml_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id);


--
-- Name: bill_payments bill_payments_invoice_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.bill_payments
    ADD CONSTRAINT bill_payments_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES paylink.invoices(invoice_id) ON DELETE CASCADE;


--
-- Name: bill_payments bill_payments_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.bill_payments
    ADD CONSTRAINT bill_payments_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id);


--
-- Name: credit_line_history credit_line_history_transaction_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.credit_line_history
    ADD CONSTRAINT credit_line_history_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES paylink.transactions(tx_id) ON DELETE SET NULL;


--
-- Name: credit_line_history credit_line_history_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.credit_line_history
    ADD CONSTRAINT credit_line_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: disputes disputes_opened_by_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.disputes
    ADD CONSTRAINT disputes_opened_by_fkey FOREIGN KEY (opened_by) REFERENCES paylink.users(user_id);


--
-- Name: disputes disputes_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.disputes
    ADD CONSTRAINT disputes_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id) ON DELETE CASCADE;


--
-- Name: external_transfers external_transfers_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.external_transfers
    ADD CONSTRAINT external_transfers_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id);


--
-- Name: fee_schedules fee_schedules_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fee_schedules
    ADD CONSTRAINT fee_schedules_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: fee_schedules fee_schedules_provider_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fee_schedules
    ADD CONSTRAINT fee_schedules_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES paylink.providers(provider_id);


--
-- Name: bonus_history fk_user; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.bonus_history
    ADD CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID;


--
-- Name: fx_conversions fx_conversions_from_currency_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_conversions
    ADD CONSTRAINT fx_conversions_from_currency_fkey FOREIGN KEY (from_currency) REFERENCES paylink.currencies(currency_code);


--
-- Name: fx_conversions fx_conversions_to_currency_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_conversions
    ADD CONSTRAINT fx_conversions_to_currency_fkey FOREIGN KEY (to_currency) REFERENCES paylink.currencies(currency_code);


--
-- Name: fx_conversions fx_conversions_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_conversions
    ADD CONSTRAINT fx_conversions_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id) ON DELETE CASCADE;


--
-- Name: fx_rates fx_rates_base_currency_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_rates
    ADD CONSTRAINT fx_rates_base_currency_fkey FOREIGN KEY (base_currency) REFERENCES paylink.currencies(currency_code);


--
-- Name: fx_rates fx_rates_provider_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_rates
    ADD CONSTRAINT fx_rates_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES paylink.providers(provider_id);


--
-- Name: fx_rates fx_rates_quote_currency_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.fx_rates
    ADD CONSTRAINT fx_rates_quote_currency_fkey FOREIGN KEY (quote_currency) REFERENCES paylink.currencies(currency_code);


--
-- Name: invoices invoices_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.invoices
    ADD CONSTRAINT invoices_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: invoices invoices_customer_user_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.invoices
    ADD CONSTRAINT invoices_customer_user_fkey FOREIGN KEY (customer_user) REFERENCES paylink.users(user_id);


--
-- Name: invoices invoices_merchant_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.invoices
    ADD CONSTRAINT invoices_merchant_id_fkey FOREIGN KEY (merchant_id) REFERENCES paylink.merchants(merchant_id) ON DELETE CASCADE;


--
-- Name: kyc_documents kyc_documents_reviewer_user_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.kyc_documents
    ADD CONSTRAINT kyc_documents_reviewer_user_fkey FOREIGN KEY (reviewer_user) REFERENCES paylink.users(user_id);


--
-- Name: kyc_documents kyc_documents_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.kyc_documents
    ADD CONSTRAINT kyc_documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: ledger_accounts ledger_accounts_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_accounts
    ADD CONSTRAINT ledger_accounts_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: ledger_entries ledger_entries_account_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_entries
    ADD CONSTRAINT ledger_entries_account_id_fkey FOREIGN KEY (account_id) REFERENCES paylink.ledger_accounts(account_id);


--
-- Name: ledger_entries ledger_entries_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_entries
    ADD CONSTRAINT ledger_entries_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: ledger_entries ledger_entries_journal_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.ledger_entries
    ADD CONSTRAINT ledger_entries_journal_id_fkey FOREIGN KEY (journal_id) REFERENCES paylink.ledger_journal(journal_id) ON DELETE CASCADE;


--
-- Name: limit_usage limit_usage_limit_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.limit_usage
    ADD CONSTRAINT limit_usage_limit_id_fkey FOREIGN KEY ("limit_id ") REFERENCES paylink.limits(limit_id) NOT VALID;


--
-- Name: limit_usage limit_usage_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.limit_usage
    ADD CONSTRAINT limit_usage_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: limits limits_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.limits
    ADD CONSTRAINT limits_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: loan_repayments loan_repayments_loan_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.loan_repayments
    ADD CONSTRAINT loan_repayments_loan_id_fkey FOREIGN KEY (loan_id) REFERENCES paylink.loans(loan_id) ON DELETE CASCADE;


--
-- Name: loan_repayments loan_repayments_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.loan_repayments
    ADD CONSTRAINT loan_repayments_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id);


--
-- Name: loans loans_borrower_user_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.loans
    ADD CONSTRAINT loans_borrower_user_fkey FOREIGN KEY (borrower_user) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: loans loans_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.loans
    ADD CONSTRAINT loans_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: merchants merchants_settlement_wallet_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.merchants
    ADD CONSTRAINT merchants_settlement_wallet_fkey FOREIGN KEY (settlement_wallet) REFERENCES paylink.wallets(wallet_id);


--
-- Name: merchants merchants_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.merchants
    ADD CONSTRAINT merchants_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: mobile_money_deposits mobile_money_deposits_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.mobile_money_deposits
    ADD CONSTRAINT mobile_money_deposits_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id);


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: payment_instructions payment_instructions_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.payment_instructions
    ADD CONSTRAINT payment_instructions_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: payment_instructions payment_instructions_provider_account_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.payment_instructions
    ADD CONSTRAINT payment_instructions_provider_account_id_fkey FOREIGN KEY (provider_account_id) REFERENCES paylink.provider_accounts(provider_account_id);


--
-- Name: payment_instructions payment_instructions_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.payment_instructions
    ADD CONSTRAINT payment_instructions_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id) ON DELETE CASCADE;


--
-- Name: provider_accounts provider_accounts_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.provider_accounts
    ADD CONSTRAINT provider_accounts_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: provider_accounts provider_accounts_provider_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.provider_accounts
    ADD CONSTRAINT provider_accounts_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES paylink.providers(provider_id) ON DELETE CASCADE;


--
-- Name: recon_files recon_files_provider_account_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_files
    ADD CONSTRAINT recon_files_provider_account_id_fkey FOREIGN KEY (provider_account_id) REFERENCES paylink.provider_accounts(provider_account_id);


--
-- Name: recon_lines recon_lines_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_lines
    ADD CONSTRAINT recon_lines_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: recon_lines recon_lines_matched_tx_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_lines
    ADD CONSTRAINT recon_lines_matched_tx_fkey FOREIGN KEY (matched_tx) REFERENCES paylink.transactions(tx_id);


--
-- Name: recon_lines recon_lines_recon_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.recon_lines
    ADD CONSTRAINT recon_lines_recon_id_fkey FOREIGN KEY (recon_id) REFERENCES paylink.recon_files(recon_id) ON DELETE CASCADE;


--
-- Name: sanctions_screening sanctions_screening_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.sanctions_screening
    ADD CONSTRAINT sanctions_screening_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: security_events security_events_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.security_events
    ADD CONSTRAINT security_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id);


--
-- Name: settlements settlements_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.settlements
    ADD CONSTRAINT settlements_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: settlements settlements_provider_account_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.settlements
    ADD CONSTRAINT settlements_provider_account_id_fkey FOREIGN KEY (provider_account_id) REFERENCES paylink.provider_accounts(provider_account_id);


--
-- Name: tontine_contributions tontine_contributions_tontine_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_contributions
    ADD CONSTRAINT tontine_contributions_tontine_id_fkey FOREIGN KEY (tontine_id) REFERENCES paylink.tontines(tontine_id) ON DELETE CASCADE;


--
-- Name: tontine_contributions tontine_contributions_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_contributions
    ADD CONSTRAINT tontine_contributions_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id);


--
-- Name: tontine_contributions tontine_contributions_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_contributions
    ADD CONSTRAINT tontine_contributions_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: tontine_invitations tontine_invitations_accepted_by_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_invitations
    ADD CONSTRAINT tontine_invitations_accepted_by_fkey FOREIGN KEY (accepted_by) REFERENCES paylink.users(user_id);


--
-- Name: tontine_invitations tontine_invitations_created_by_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_invitations
    ADD CONSTRAINT tontine_invitations_created_by_fkey FOREIGN KEY (created_by) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: tontine_invitations tontine_invitations_tontine_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_invitations
    ADD CONSTRAINT tontine_invitations_tontine_id_fkey FOREIGN KEY (tontine_id) REFERENCES paylink.tontines(tontine_id) ON DELETE CASCADE;


--
-- Name: tontine_members tontine_members_tontine_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_members
    ADD CONSTRAINT tontine_members_tontine_id_fkey FOREIGN KEY (tontine_id) REFERENCES paylink.tontines(tontine_id) ON DELETE CASCADE;


--
-- Name: tontine_members tontine_members_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_members
    ADD CONSTRAINT tontine_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: tontine_payouts tontine_payouts_beneficiary_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_payouts
    ADD CONSTRAINT tontine_payouts_beneficiary_id_fkey FOREIGN KEY (beneficiary_id) REFERENCES paylink.users(user_id);


--
-- Name: tontine_payouts tontine_payouts_tontine_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_payouts
    ADD CONSTRAINT tontine_payouts_tontine_id_fkey FOREIGN KEY (tontine_id) REFERENCES paylink.tontines(tontine_id) ON DELETE CASCADE;


--
-- Name: tontine_payouts tontine_payouts_tx_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_payouts
    ADD CONSTRAINT tontine_payouts_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES paylink.transactions(tx_id);


--
-- Name: tontine_rotations tontine_rotations_tontine_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_rotations
    ADD CONSTRAINT tontine_rotations_tontine_id_fkey FOREIGN KEY (tontine_id) REFERENCES paylink.tontines(tontine_id) ON DELETE CASCADE;


--
-- Name: tontine_rotations tontine_rotations_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontine_rotations
    ADD CONSTRAINT tontine_rotations_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id);


--
-- Name: tontines tontines_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontines
    ADD CONSTRAINT tontines_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: tontines tontines_owner_user_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.tontines
    ADD CONSTRAINT tontines_owner_user_fkey FOREIGN KEY (owner_user) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: transactions transactions_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.transactions
    ADD CONSTRAINT transactions_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: transactions transactions_initiated_by_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.transactions
    ADD CONSTRAINT transactions_initiated_by_fkey FOREIGN KEY (initiated_by) REFERENCES paylink.users(user_id);


--
-- Name: transactions transactions_receiver_wallet_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.transactions
    ADD CONSTRAINT transactions_receiver_wallet_fkey FOREIGN KEY (receiver_wallet) REFERENCES paylink.wallets(wallet_id);


--
-- Name: transactions transactions_sender_wallet_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.transactions
    ADD CONSTRAINT transactions_sender_wallet_fkey FOREIGN KEY (sender_wallet) REFERENCES paylink.wallets(wallet_id);


--
-- Name: user_auth user_auth_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.user_auth
    ADD CONSTRAINT user_auth_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: user_devices user_devices_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.user_devices
    ADD CONSTRAINT user_devices_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: users users_country_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.users
    ADD CONSTRAINT users_country_code_fkey FOREIGN KEY (country_code) REFERENCES paylink.countries(country_code);


--
-- Name: users users_referred_by_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.users
    ADD CONSTRAINT users_referred_by_fkey FOREIGN KEY (referred_by) REFERENCES paylink.users(user_id);


--
-- Name: wallet_bonus_history wallet_bonus_history_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_bonus_history
    ADD CONSTRAINT wallet_bonus_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: wallet_bonus_history wallet_bonus_history_wallet_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_bonus_history
    ADD CONSTRAINT wallet_bonus_history_wallet_id_fkey FOREIGN KEY (wallet_id) REFERENCES paylink.wallets(wallet_id) ON DELETE CASCADE;


--
-- Name: wallet_cash_requests wallet_cash_requests_processed_by_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_cash_requests
    ADD CONSTRAINT wallet_cash_requests_processed_by_fkey FOREIGN KEY (processed_by) REFERENCES paylink.users(user_id) ON DELETE SET NULL;


--
-- Name: wallet_cash_requests wallet_cash_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_cash_requests
    ADD CONSTRAINT wallet_cash_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE CASCADE;


--
-- Name: wallet_cash_requests wallet_cash_requests_wallet_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_cash_requests
    ADD CONSTRAINT wallet_cash_requests_wallet_id_fkey FOREIGN KEY (wallet_id) REFERENCES paylink.wallets(wallet_id) ON DELETE CASCADE;


--
-- Name: wallet_transactions wallet_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_transactions
    ADD CONSTRAINT wallet_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE SET NULL;


--
-- Name: wallet_transactions wallet_transactions_wallet_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallet_transactions
    ADD CONSTRAINT wallet_transactions_wallet_id_fkey FOREIGN KEY (wallet_id) REFERENCES paylink.wallets(wallet_id) ON DELETE CASCADE;


--
-- Name: wallets wallets_currency_code_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallets
    ADD CONSTRAINT wallets_currency_code_fkey FOREIGN KEY (currency_code) REFERENCES paylink.currencies(currency_code);


--
-- Name: wallets wallets_user_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.wallets
    ADD CONSTRAINT wallets_user_id_fkey FOREIGN KEY (user_id) REFERENCES paylink.users(user_id) ON DELETE SET NULL;


--
-- Name: webhook_events webhook_events_webhook_id_fkey; Type: FK CONSTRAINT; Schema: paylink; Owner: postgres
--

ALTER TABLE ONLY paylink.webhook_events
    ADD CONSTRAINT webhook_events_webhook_id_fkey FOREIGN KEY (webhook_id) REFERENCES paylink.webhooks(webhook_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict BaynaWTUeAPu8qGrApYSWXYSrtedZN6awszeMfxxUQCPRhiziHgM1cDTFG7xZbf

