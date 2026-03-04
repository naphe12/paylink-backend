CREATE SCHEMA IF NOT EXISTS escrow;

CREATE TABLE IF NOT EXISTS escrow.webhook_logs (
  id bigserial PRIMARY KEY,
  event_type text NOT NULL,
  tx_hash text,
  status text NOT NULL,
  attempts integer NOT NULL DEFAULT 1,
  payload jsonb NOT NULL,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  order_id uuid,
  network text
);

CREATE INDEX IF NOT EXISTS idx_escrow_webhook_logs_created_at
ON escrow.webhook_logs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_escrow_webhook_logs_event_type
ON escrow.webhook_logs (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_escrow_webhook_logs_tx_hash
ON escrow.webhook_logs (tx_hash);

CREATE INDEX IF NOT EXISTS idx_escrow_webhook_logs_status
ON escrow.webhook_logs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_escrow_webhook_logs_provider
ON escrow.webhook_logs ((payload->>'provider'));

CREATE INDEX IF NOT EXISTS idx_escrow_webhook_logs_provider_event_id
ON escrow.webhook_logs ((payload->>'provider_event_id'));
