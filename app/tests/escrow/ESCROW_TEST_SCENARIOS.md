# Escrow Test Scenarios (Given/When/Then)

## Variables de base
- `base_url`: URL API (ex: `http://localhost:8000`)
- `token`: JWT utilisateur
- `admin_token`: JWT admin/operator (pour `mark-paid` si necessaire)
- `order_id`: ID d'ordre escrow
- `deposit_address`: adresse de depot USDC de l'ordre

## 1) Creation ordre escrow sandbox (etat CREATED)
- Given un utilisateur authentifie avec KYC `verified`
- When il appelle `POST /escrow/orders` avec `X-SANDBOX: true` et `X-SANDBOX-SCENARIO: CONFIRMATION_DELAY`
- Then la reponse est `200`, contient `id`, `is_sandbox=true`, et le status initial est exploitable en mode sandbox

## 2) Lecture detail ordre
- Given un `order_id` valide appartenant a l'utilisateur
- When il appelle `GET /escrow/orders/{order_id}`
- Then la reponse est `200` avec `deposit_address`, `status`, `required_confirmations`, `estimated_minutes_remaining`

## 3) Transition sandbox FUND
- Given un ordre sandbox en `CREATED`
- When il appelle `POST /escrow/orders/{order_id}/sandbox/FUND`
- Then la reponse est `200`, `status=OK`, `escrow_status=FUNDED`

## 4) Transition sandbox SWAP
- Given un ordre sandbox en `FUNDED`
- When il appelle `POST /escrow/orders/{order_id}/sandbox/SWAP`
- Then la reponse est `200`, `escrow_status=SWAPPED`

## 5) Transition sandbox PAYOUT_PENDING
- Given un ordre sandbox en `SWAPPED`
- When il appelle `POST /escrow/orders/{order_id}/sandbox/PAYOUT_PENDING`
- Then la reponse est `200`, `escrow_status=PAYOUT_PENDING`

## 6) Transition sandbox PAYOUT
- Given un ordre sandbox en `PAYOUT_PENDING`
- When il appelle `POST /escrow/orders/{order_id}/sandbox/PAYOUT`
- Then la reponse est `200`, `escrow_status=PAID_OUT`

## 7) Retry autorise
- Given un ordre en `CREATED` ou `FUNDED`
- When il appelle `POST /escrow/orders/{order_id}/retry`
- Then la reponse est `200`, `status=OK`, et `expires_at` est mis a jour

## 8) Retry interdit
- Given un ordre en `PAID_OUT` ou `FAILED`
- When il appelle `POST /escrow/orders/{order_id}/retry`
- Then la reponse est `400` avec `Retry not allowed`

## 9) Webhook USDC signature invalide
- Given un payload webhook syntactiquement valide
- When il appelle `POST /escrow/webhooks/usdc` avec un `X-Paylink-Signature` incorrect
- Then la reponse est `401 Invalid webhook signature`

## 10) Webhook USDC signature valide
- Given un payload webhook valide et une signature HMAC SHA-256 correcte
- When il appelle `POST /escrow/webhooks/usdc`
- Then la reponse est `200` avec `status` dans `{OK, DUPLICATE, QUEUED_RETRY}` selon donnees et idempotence

## 11) Idempotence webhook (tx_hash + log_index)
- Given un webhook deja traite avec meme `tx_hash` et `log_index`
- When le meme webhook est rejoue
- Then la reponse retourne `DUPLICATE` sans double effet metier

## 12) Acces non proprietaire
- Given un autre utilisateur non admin/operator
- When il appelle `GET /escrow/orders/{order_id}` d'un ordre tiers
- Then la reponse est `403 Acces refuse`

## 13) Limite creation quotidienne
- Given l'utilisateur atteint `DAILY_USDC_LIMIT` ou `DAILY_TX_LIMIT`
- When il appelle `POST /escrow/orders`
- Then la reponse est `429`

## 14) Validation input creation
- Given un payload sans `recipient_name` ou sans `recipient_phone` ou `amount_usdc<=0`
- When il appelle `POST /escrow/orders`
- Then la reponse est `400` avec message de validation

## 15) Mark paid (role-based)
- Given un ordre eligibile et un utilisateur role `admin` ou `operator`
- When il appelle `POST /escrow/orders/{order_id}/mark-paid`
- Then la reponse est `200` avec `status=PAID_OUT`
- And avec un role non autorise, la reponse est `403`

