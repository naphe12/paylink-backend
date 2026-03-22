CREATE TABLE IF NOT EXISTS paylink.app_errors (
  error_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  request_id text NULL,
  status_code int NOT NULL,
  error_type text NOT NULL,
  message text NOT NULL,
  request_path text NOT NULL,
  request_method text NOT NULL,
  user_id uuid NULL,
  client_ip text NULL,
  handled boolean NOT NULL DEFAULT true,
  stack_trace text NULL,
  headers jsonb NOT NULL DEFAULT '{}'::jsonb,
  query_params jsonb NOT NULL DEFAULT '{}'::jsonb,
  request_body text NULL
);

CREATE INDEX IF NOT EXISTS idx_app_errors_created_at
ON paylink.app_errors (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_app_errors_status_code
ON paylink.app_errors (status_code);

CREATE INDEX IF NOT EXISTS idx_app_errors_request_path
ON paylink.app_errors (request_path);

CREATE INDEX IF NOT EXISTS idx_app_errors_request_id
ON paylink.app_errors (request_id);
