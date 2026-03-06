param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$AdminUsername,

    [Parameter(Mandatory = $true)]
    [string]$AdminPassword,

    [Parameter(Mandatory = $true)]
    [string]$SellerUsername,

    [Parameter(Mandatory = $true)]
    [string]$SellerPassword,

    [Parameter(Mandatory = $true)]
    [string]$BuyerUsername,

    [Parameter(Mandatory = $true)]
    [string]$BuyerPassword,

    [string]$SecretKey = "secret-paylink-key",
    [string]$Algorithm = "HS256",
    [decimal]$TokenAmount = 5.0,
    [decimal]$PriceBifPerUsd = 2900
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) { throw $Message }
}

function New-AuthHeaders {
    param([Parameter(Mandatory = $true)][string]$Token)
    return @{
        Authorization = "Bearer $Token"
        "Content-Type" = "application/json"
    }
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

function ConvertTo-Base64Url {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    $b64 = [Convert]::ToBase64String($Bytes)
    return $b64.TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function New-JwtHS256 {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Payload,
        [Parameter(Mandatory = $true)][string]$Secret,
        [string]$Alg = "HS256"
    )

    if ($Alg -ne "HS256") {
        throw "Only HS256 is supported in this script."
    }

    $header = @{ alg = "HS256"; typ = "JWT" }
    $headerJson = ($header | ConvertTo-Json -Compress)
    $payloadJson = ($Payload | ConvertTo-Json -Compress)

    $headerB64 = ConvertTo-Base64Url -Bytes ([Text.Encoding]::UTF8.GetBytes($headerJson))
    $payloadB64 = ConvertTo-Base64Url -Bytes ([Text.Encoding]::UTF8.GetBytes($payloadJson))
    $toSign = "$headerB64.$payloadB64"

    $hmac = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($Secret))
    try {
        $sigBytes = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($toSign))
    } finally {
        $hmac.Dispose()
    }

    $sigB64 = ConvertTo-Base64Url -Bytes $sigBytes
    return "$toSign.$sigB64"
}

function Login {
    param(
        [Parameter(Mandatory = $true)][string]$Username,
        [Parameter(Mandatory = $true)][string]$Password
    )
    $resp = Invoke-RestMethod -Method Post `
        -Uri "$BaseUrl/auth/login" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{ username = $Username; password = $Password }
    if (-not $resp.access_token) {
        throw "Login failed for $Username"
    }
    return "$($resp.access_token)"
}

Write-Host "== P2P Agent Link Regression (CRYPTO_LOCKED -> FIAT_SENT) =="

# 1) Login users
$adminToken = Login -Username $AdminUsername -Password $AdminPassword
$sellerToken = Login -Username $SellerUsername -Password $SellerPassword
$buyerToken = Login -Username $BuyerUsername -Password $BuyerPassword

$adminHeaders = New-AuthHeaders -Token $adminToken
$sellerHeaders = New-AuthHeaders -Token $sellerToken
$buyerHeaders = New-AuthHeaders -Token $buyerToken

Write-Host "Login OK (admin/seller/buyer)"

# 2) Resolve identities
$sellerMe = Invoke-ApiJson -Method Get -Uri "$BaseUrl/auth/me" -Headers @{ Authorization = "Bearer $sellerToken" }
$buyerMe = Invoke-ApiJson -Method Get -Uri "$BaseUrl/auth/me" -Headers @{ Authorization = "Bearer $buyerToken" }
$sellerId = "$($sellerMe.user_id)"
$buyerId = "$($buyerMe.user_id)"
Assert-True ($sellerId.Length -gt 0) "Seller user_id missing"
Assert-True ($buyerId.Length -gt 0) "Buyer user_id missing"

Write-Host "Seller ID: $sellerId"
Write-Host "Buyer ID : $buyerId"

# 3) Seller creates SELL offer
$offerBody = @{
    side = "SELL"
    token = "USDC"
    price_bif_per_usd = [double]$PriceBifPerUsd
    min_token_amount = [double]$TokenAmount
    max_token_amount = [double]$TokenAmount
    available_amount = [double]$TokenAmount
    payment_method = "CASH"
    payment_details = @{}
    terms = "Regression test offer"
} | ConvertTo-Json -Depth 5

$offer = Invoke-ApiJson -Method Post -Uri "$BaseUrl/api/p2p/offers" -Headers $sellerHeaders -Body $offerBody
$offerId = "$($offer.offer_id)"
Assert-True ($offerId.Length -gt 0) "Offer creation failed"
Write-Host "Offer created: $offerId"

# 4) Buyer creates trade on seller offer
$tradeBody = @{
    offer_id = $offerId
    token_amount = "$TokenAmount"
} | ConvertTo-Json

$trade = Invoke-ApiJson -Method Post -Uri "$BaseUrl/api/p2p/trades" -Headers $buyerHeaders -Body $tradeBody
$tradeId = "$($trade.trade_id)"
Assert-True ($tradeId.Length -gt 0) "Trade creation failed"
Write-Host "Trade created: $tradeId status=$($trade.status)"

# 5) Force CRYPTO_LOCKED (admin sandbox endpoint)
$forced = Invoke-ApiJson -Method Post -Uri "$BaseUrl/api/p2p/trades/$tradeId/sandbox/crypto-locked" -Headers $adminHeaders -Body (@{ escrow_tx_hash = $null } | ConvertTo-Json)
Assert-True ("$($forced.status)" -eq "CRYPTO_LOCKED") "Trade did not reach CRYPTO_LOCKED"
Write-Host "Trade forced to CRYPTO_LOCKED"

# 6) Build the same signed token used by email link
$exp = [DateTimeOffset]::UtcNow.AddHours(12).ToUnixTimeSeconds()
$payload = @{
    sub = $sellerId
    action = "p2p_fiat_sent_by_agent"
    trade_id = $tradeId
    exp = $exp
    token_type = "bearer"
}
$agentLinkToken = New-JwtHS256 -Payload $payload -Secret $SecretKey -Alg $Algorithm
$encodedToken = [System.Uri]::EscapeDataString($agentLinkToken)
$confirmUri = "$BaseUrl/api/p2p/trades/$tradeId/fiat-sent-by-agent?token=$encodedToken"

Write-Host "Generated confirm URI:"
Write-Host $confirmUri

# 7) Simulate email click
$afterLink = Invoke-ApiJson -Method Get -Uri $confirmUri -Headers $null
Assert-True ("$($afterLink.status)" -eq "FIAT_SENT") "Expected FIAT_SENT after link click, got '$($afterLink.status)'"
Write-Host "Link click OK -> status FIAT_SENT"

# 8) Sanity check trade state
$finalTrade = Invoke-ApiJson -Method Get -Uri "$BaseUrl/api/p2p/trades/$tradeId" -Headers @{ Authorization = "Bearer $buyerToken" }
Assert-True ("$($finalTrade.status)" -eq "FIAT_SENT") "Final trade status mismatch: $($finalTrade.status)"

Write-Host ""
Write-Host "All checks passed."
Write-Host "Summary:"
Write-Host " - offer_id: $offerId"
Write-Host " - trade_id: $tradeId"
Write-Host " - seller_id: $sellerId"
Write-Host " - buyer_id:  $buyerId"
Write-Host " - final_status: $($finalTrade.status)"
