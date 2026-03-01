param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$Username,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [Parameter(Mandatory = $true)]
    [string]$WebhookSecret,

    [string]$RecipientPhone = "+25770000001",
    [decimal]$AmountUsdc = 10
)

$ErrorActionPreference = "Stop"

function New-RandomHex([int]$length) {
    $chars = "0123456789abcdef"
    $sb = New-Object System.Text.StringBuilder
    for ($i = 0; $i -lt $length; $i++) {
        [void]$sb.Append($chars[(Get-Random -Minimum 0 -Maximum 16)])
    }
    return $sb.ToString()
}

function Get-HmacSha256Hex([string]$secret, [string]$payload) {
    $hmac = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($secret))
    $hashBytes = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($payload))
    return -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
}

function Invoke-ApiJson {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [hashtable]$Headers,
        [object]$Body
    )

    $args = @{
        Method = $Method
        Uri = $Uri
    }
    if ($Headers) { $args["Headers"] = $Headers }
    if ($Body -ne $null) { $args["Body"] = $Body }
    return Invoke-RestMethod @args
}

function Create-EscrowOrder {
    param(
        [string]$BaseUrl,
        [string]$Token,
        [string]$Scenario,
        [decimal]$AmountUsdc,
        [string]$RecipientPhone
    )

    $headers = @{
        Authorization = "Bearer $Token"
        "Content-Type" = "application/json"
        "X-SANDBOX" = "true"
        "X-SANDBOX-SCENARIO" = $Scenario
    }
    $body = @{
        amount_usdc = $AmountUsdc
        recipient_name = "Regression Test"
        recipient_phone = $RecipientPhone
        deposit_network = "POLYGON"
        deposit_required_confirmations = 1
    } | ConvertTo-Json

    return Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders" -Headers $headers -Body $body
}

Write-Host "== Escrow Regression =="

# 1) Login
$loginResp = Invoke-RestMethod -Method Post `
    -Uri "$BaseUrl/auth/login" `
    -ContentType "application/x-www-form-urlencoded" `
    -Body @{ username = $Username; password = $Password }

if (-not $loginResp.access_token) { throw "Login failed: access_token absent" }
$token = $loginResp.access_token
Write-Host "TOKEN OK"

# 2) Sandbox full flow
Write-Host "`n[Flow A] Sandbox full flow"
$orderA = Create-EscrowOrder -BaseUrl $BaseUrl -Token $token -Scenario "CONFIRMATION_DELAY" -AmountUsdc $AmountUsdc -RecipientPhone $RecipientPhone
$orderAId = $orderA.id
if (-not $orderAId) { throw "Flow A: order id absent" }
Write-Host "ORDER_A: $orderAId"

$authHeaders = @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
}

$rFund = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders/$orderAId/sandbox/FUND" -Headers $authHeaders
if ($rFund.escrow_status -ne "FUNDED") { throw "Flow A: expected FUNDED, got $($rFund.escrow_status)" }

$rSwap = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders/$orderAId/sandbox/SWAP" -Headers $authHeaders
if ($rSwap.escrow_status -ne "SWAPPED") { throw "Flow A: expected SWAPPED, got $($rSwap.escrow_status)" }

$rPending = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders/$orderAId/sandbox/PAYOUT_PENDING" -Headers $authHeaders
if ($rPending.escrow_status -ne "PAYOUT_PENDING") { throw "Flow A: expected PAYOUT_PENDING, got $($rPending.escrow_status)" }

$rPayout = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders/$orderAId/sandbox/PAYOUT" -Headers $authHeaders
if ($rPayout.escrow_status -ne "PAID_OUT") { throw "Flow A: expected PAID_OUT, got $($rPayout.escrow_status)" }
Write-Host "Flow A OK"

# 3) Webhook-only flow
Write-Host "`n[Flow B] Webhook only"
$orderB = Create-EscrowOrder -BaseUrl $BaseUrl -Token $token -Scenario "CONFIRMATION_DELAY" -AmountUsdc $AmountUsdc -RecipientPhone $RecipientPhone
$orderBId = $orderB.id
if (-not $orderBId) { throw "Flow B: order id absent" }
Write-Host "ORDER_B: $orderBId"

$orderBState = Invoke-ApiJson -Method Get -Uri "$BaseUrl/escrow/orders/$orderBId" -Headers @{ Authorization = "Bearer $token" }
$depositAddress = $orderBState.deposit_address
if (-not $depositAddress) { throw "Flow B: deposit_address absent" }
Write-Host "DEPOSIT_ADDRESS: $depositAddress"

$txHash = "0x$(New-RandomHex -length 64)"
$payloadObj = @{
    network = "POLYGON"
    tx_hash = $txHash
    log_index = 0
    from_address = "0x1111111111111111111111111111111111111111"
    to_address = $depositAddress
    amount = "$AmountUsdc"
    confirmations = 3
}
$payload = $payloadObj | ConvertTo-Json -Compress

# Invalid signature should return 401
try {
    Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/webhooks/usdc" -Headers @{
        "X-Paylink-Signature" = "invalid-signature"
        "Content-Type" = "application/json"
    } -Body $payload | Out-Null
    throw "Flow B: invalid signature unexpectedly accepted"
} catch {
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -eq 401) {
        Write-Host "Invalid signature check OK (401)"
    } else {
        throw
    }
}

# Valid signature should process webhook
$signature = Get-HmacSha256Hex -secret $WebhookSecret -payload $payload
$validResp = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/webhooks/usdc" -Headers @{
    "X-Paylink-Signature" = $signature
    "Content-Type" = "application/json"
} -Body $payload

$allowedWebhookStatus = @("FUNDED", "MANUAL_REVIEW", "BLOCKED", "QUEUED_RETRY")
if ($allowedWebhookStatus -notcontains "$($validResp.status)") {
    throw "Flow B: unexpected webhook status '$($validResp.status)'"
}
Write-Host "Webhook response: $($validResp | ConvertTo-Json -Compress)"

$orderBAfter = Invoke-ApiJson -Method Get -Uri "$BaseUrl/escrow/orders/$orderBId" -Headers @{ Authorization = "Bearer $token" }
Write-Host "Order after webhook: $($orderBAfter.status)"

Write-Host "`nAll escrow regression checks passed."
