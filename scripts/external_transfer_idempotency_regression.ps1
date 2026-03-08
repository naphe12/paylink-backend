param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$Username,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [decimal]$Amount = 10,
    [string]$CountryDestination = "Burundi",
    [string]$PartnerName = "Lumicash",
    [string]$RecipientName = "Regression User",
    [string]$RecipientPhone = "+25761000000"
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) { throw $Message }
}

function Login {
    param(
        [Parameter(Mandatory = $true)][string]$U,
        [Parameter(Mandatory = $true)][string]$P
    )
    $resp = Invoke-RestMethod -Method Post `
        -Uri "$BaseUrl/auth/login" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{ username = $U; password = $P }
    if (-not $resp.access_token) {
        throw "Login failed for $U"
    }
    return "$($resp.access_token)"
}

function Post-ExternalTransfer {
    param(
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][string]$IdemKey
    )
    $headers = @{
        Authorization    = "Bearer $Token"
        "Content-Type"   = "application/json"
        "Idempotency-Key" = $IdemKey
    }
    $body = @{
        partner_name        = $PartnerName
        country_destination = $CountryDestination
        recipient_name      = $RecipientName
        recipient_phone     = $RecipientPhone
        amount              = "$Amount"
    } | ConvertTo-Json

    return Invoke-RestMethod -Method Post -Uri "$BaseUrl/wallet/transfer/external" -Headers $headers -Body $body
}

Write-Host "== External Transfer Idempotency Regression =="

$token = Login -U $Username -P $Password
Write-Host "Login OK"

$idemKey = "ext-transfer-regression-$([guid]::NewGuid().ToString('N'))"
Write-Host "Idempotency-Key: $idemKey"

$first = Post-ExternalTransfer -Token $token -IdemKey $idemKey
Assert-True ($null -ne $first.transfer_id) "First call: transfer_id missing"
Write-Host "First call transfer_id=$($first.transfer_id) status=$($first.status)"

$second = Post-ExternalTransfer -Token $token -IdemKey $idemKey
Assert-True ($null -ne $second.transfer_id) "Second call: transfer_id missing"
Write-Host "Second call transfer_id=$($second.transfer_id) status=$($second.status)"

Assert-True ("$($first.transfer_id)" -eq "$($second.transfer_id)") `
    "Idempotency failed: second call created another transfer ($($first.transfer_id) vs $($second.transfer_id))"

Write-Host ""
Write-Host "OK: idempotency validated."
Write-Host "transfer_id: $($first.transfer_id)"
