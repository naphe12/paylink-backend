-- Replace :order_id and :tx_hash before executing.
-- Example:
--   \set order_id 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
--   \set tx_hash '0xabc...'

-- 1) Etat de l'ordre escrow
SELECT
    o.id,
    o.status,
    o.usdc_expected,
    o.usdc_received,
    o.bif_target,
    o.deposit_tx_hash,
    o.deposit_confirmations,
    o.funded_at,
    o.swapped_at,
    o.payout_initiated_at,
    o.updated_at
FROM escrow.orders o
WHERE o.id = CAST(:order_id AS uuid);

-- 2) Depot on-chain enregistre
SELECT
    d.order_id,
    d.network,
    d.tx_hash,
    d.from_address,
    d.to_address,
    d.amount,
    d.confirmations,
    d.detected_at
FROM escrow.chain_deposits d
WHERE d.order_id = CAST(:order_id AS uuid)
ORDER BY d.detected_at DESC;

-- 3) Assignment agent cree des le FUNDED
SELECT
    a.id AS assignment_id,
    a.order_id,
    a.agent_id,
    a.amount_bif,
    a.status,
    a.assigned_at,
    ag.display_name,
    ag.email AS agent_email,
    ag.user_id AS agent_user_id,
    ag.daily_used_bif,
    ag.last_assigned_at
FROM paylink.assignments a
JOIN paylink.agents ag ON ag.agent_id = a.agent_id
WHERE a.order_id = CAST(:order_id AS uuid)
ORDER BY a.assigned_at DESC NULLS LAST, a.id DESC;

-- 4) Notification persistee pour l'agent
SELECT
    n.notification_id,
    n.user_id,
    n.channel,
    n.subject,
    n.message,
    n.metadata,
    n.created_at
FROM paylink.notifications n
WHERE n.channel = 'PAYOUT_ASSIGNMENT'
  AND n.metadata->>'order_id' = :order_id
ORDER BY n.created_at DESC;

-- 5) Log webhook
SELECT
    wl.id,
    wl.event_type,
    wl.tx_hash,
    wl.status,
    wl.attempts,
    wl.payload->>'log_index' AS log_index,
    wl.created_at,
    wl.error
FROM escrow.webhook_logs wl
WHERE wl.tx_hash = :tx_hash
ORDER BY wl.created_at DESC;

-- 6) Vue de synthese utile pour validation rapide
SELECT
    o.id AS order_id,
    o.status AS order_status,
    a.id AS assignment_id,
    a.status AS assignment_status,
    a.agent_id,
    n.notification_id,
    n.created_at AS notification_created_at,
    wl.status AS webhook_status
FROM escrow.orders o
LEFT JOIN paylink.assignments a
    ON a.order_id = o.id
LEFT JOIN paylink.notifications n
    ON n.channel = 'PAYOUT_ASSIGNMENT'
   AND n.metadata->>'order_id' = CAST(o.id AS text)
LEFT JOIN LATERAL (
    SELECT status
    FROM escrow.webhook_logs
    WHERE tx_hash = :tx_hash
    ORDER BY created_at DESC
    LIMIT 1
) wl ON TRUE
WHERE o.id = CAST(:order_id AS uuid);
