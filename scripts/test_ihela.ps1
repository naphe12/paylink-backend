# test_ihela_bridge.ps1
# Usage:
# .\test_ihela_bridge.ps1 `
#   -BackendBaseUrl "https://<TON_BACKEND_RAILWAY>" `
#   -JwtToken "<JWT_ADMIN_OU_AGENT>" `
#   -DebitAccount "76001002" `
#   -DebitAccountHolder "John Doe" `
#   -Amount 3000 `
#   -PinCode "1234"

param(
  [Parameter(Mandatory=$true)][string]$BackendBaseUrl,
  [Parameter(Mandatory=$true)][string]$JwtToken,
  [Parameter(Mandatory=$true)][string]$DebitAccount,
  [Parameter(Mandatory=$true)][string]$DebitAccountHolder,
  [Parameter(Mandatory=$true)][decimal]$Amount,
  [Parameter(Mandatory=$true)][string]$PinCode,
  [string]$Description = "Test transfert externe Paylink",
  [string]$ExternalReference = ""
)

$ErrorActionPreference = "Stop"

function Clean-HeaderValue([string]$Value) {
  return (($Value -replace "[`r`n]", "")).Trim()
}

$base = (Clean-HeaderValue $BackendBaseUrl).TrimEnd("/")
$JwtToken = Clean-HeaderValue $JwtToken
$DebitAccount = Clean-HeaderValue $DebitAccount
$DebitAccountHolder = Clean-HeaderValue $DebitAccountHolder
$PinCode = Clean-HeaderValue $PinCode
$Description = (($Description -replace "[`r`n]", " ")).Trim()
$ExternalReference = Clean-HeaderValue $ExternalReference

if ([string]::IsNullOrWhiteSpace($ExternalReference)) {
  $ExternalReference = "PAYLINK-TEST-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}

if ($JwtToken -match "\s") {
  throw "JwtToken invalide: il contient des espaces ou retours ligne. Recupere uniquement access_token."
}

$headers = @{
  "Authorization" = "Bearer $JwtToken"
  "Content-Type"  = "application/json"
}

$withdrawBody = @{
  debit_account        = $DebitAccount
  debit_account_holder = $DebitAccountHolder
  amount               = [double]$Amount
  description          = $Description
  external_reference   = $ExternalReference
  pin_code             = $PinCode
} | ConvertTo-Json -Depth 10

Write-Host "===> 1) Withdrawal test..."
$withdrawUrl = "$base/providers/ihela/test/withdrawal"
$withdrawResp = Invoke-RestMethod -Method Post -Uri $withdrawUrl -Headers $headers -Body $withdrawBody

$withdrawResp | ConvertTo-Json -Depth 20
Write-Host ""

if ($withdrawResp.transport -ne "bridge") {
  Write-Warning "transport != bridge (actuel: $($withdrawResp.transport))"
}

$reference = $null
if ($withdrawResp.response -and $withdrawResp.response.response_data) {
  $reference = $withdrawResp.response.response_data.reference
}
if (-not $reference -and $withdrawResp.response) {
  $reference = $withdrawResp.response.reference
}

if (-not $reference) {
  throw "Reference introuvable dans la reponse withdrawal. Verifie la structure JSON retournee."
}

Write-Host "Reference detectee: $reference"
Write-Host "===> 2) Transaction status test..."

$statusBody = @{
  reference = "$reference"
} | ConvertTo-Json -Depth 10

$statusUrl = "$base/providers/ihela/test/transaction-status"
$statusResp = Invoke-RestMethod -Method Post -Uri $statusUrl -Headers $headers -Body $statusBody

$statusResp | ConvertTo-Json -Depth 20
Write-Host ""
Write-Host "Test termine."
