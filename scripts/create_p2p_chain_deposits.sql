CREATE SCHEMA IF NOT EXISTS p2p;

CREATE TABLE IF NOT EXISTS p2p.chain_deposits (
  deposit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_id uuid REFERENCES p2p.trades(trade_id) ON DELETE SET NULL,
  tx_hash text NOT NULL,
  log_index bigint NOT NULL DEFAULT 0,
  network text NOT NULL,
  token text NOT NULL,
  to_address text NOT NULL,
  amount numeric(24, 8) NOT NULL,
  block_number bigint,
  block_timestamp timestamptz,
  status text NOT NULL,
  resolution text,
  matched_at timestamptz,
  matched_by uuid REFERENCES paylink.users(user_id) ON DELETE SET NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_p2p_chain_deposits_tx UNIQUE (network, token, tx_hash, log_index)
);

CREATE INDEX IF NOT EXISTS idx_p2p_chain_deposits_status_created
ON p2p.chain_deposits (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_p2p_chain_deposits_trade_id
ON p2p.chain_deposits (trade_id);

CREATE INDEX IF NOT EXISTS idx_p2p_chain_deposits_to_address
ON p2p.chain_deposits (lower(to_address));

CREATE INDEX IF NOT EXISTS idx_p2p_trades_escrow_match
ON p2p.trades (status, token, created_at);

CREATE INDEX IF NOT EXISTS idx_p2p_trades_escrow_addr
ON p2p.trades (lower(escrow_deposit_addr));
