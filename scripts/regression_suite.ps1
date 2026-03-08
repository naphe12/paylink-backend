param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [string]$UserUsername,
    [string]$UserPassword,

    [string]$AdminUsername,
    [string]$AdminPassword,
    [string]$SellerUsername,
    [string]$SellerPassword,
    [string]$BuyerUsername,
    [string]$BuyerPassword,

    [string]$WebhookSecret,
    [string]$JwtSecret = "secret-paylink-key",
    [string]$JwtAlgorithm = "HS256",

    [switch]$StopOnError
)

$ErrorActionPreference = "Stop"

function Run-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host ""
    Write-Host "=== $Name ==="
    try {
        & $Action
        return @{
            name = $Name
            status = "PASS"
            error = $null
        }
    } catch {
        $msg = $_.Exception.Message
        Write-Host "FAILED: $msg"
        if ($StopOnError) { throw }
        return @{
            name = $Name
            status = "FAIL"
            error = $msg
        }
    }
}

function Can-RunExternalTransferRegression {
    return (-not [string]::IsNullOrWhiteSpace($UserUsername)) -and (-not [string]::IsNullOrWhiteSpace($UserPassword))
}

function Can-RunEscrowRegression {
    return (Can-RunExternalTransferRegression) -and (-not [string]::IsNullOrWhiteSpace($WebhookSecret))
}

function Can-RunP2PAgentLinkRegression {
    $required = @(
        $AdminUsername,
        $AdminPassword,
        $SellerUsername,
        $SellerPassword,
        $BuyerUsername,
        $BuyerPassword
    )
    foreach ($value in $required) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            return $false
        }
    }
    return $true
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$results = @()

Write-Host "== PayLink Regression Suite =="
Write-Host "BaseUrl: $BaseUrl"

if (Can-RunExternalTransferRegression) {
    $results += Run-Step -Name "External Transfer Idempotency" -Action {
        & (Join-Path $scriptRoot "external_transfer_idempotency_regression.ps1") `
            -BaseUrl $BaseUrl `
            -Username $UserUsername `
            -Password $UserPassword
    }
} else {
    Write-Host ""
    Write-Host "SKIP External Transfer Idempotency (UserUsername/UserPassword manquants)"
    $results += @{ name = "External Transfer Idempotency"; status = "SKIP"; error = "Missing user credentials" }
}

if (Can-RunEscrowRegression) {
    $results += Run-Step -Name "Escrow Regression" -Action {
        & (Join-Path $scriptRoot "escrow_regression.ps1") `
            -BaseUrl $BaseUrl `
            -Username $UserUsername `
            -Password $UserPassword `
            -WebhookSecret $WebhookSecret
    }
} else {
    Write-Host ""
    Write-Host "SKIP Escrow Regression (UserUsername/UserPassword/WebhookSecret manquants)"
    $results += @{ name = "Escrow Regression"; status = "SKIP"; error = "Missing user credentials or webhook secret" }
}

if (Can-RunP2PAgentLinkRegression) {
    $results += Run-Step -Name "P2P Agent Link Regression" -Action {
        & (Join-Path $scriptRoot "p2p_agent_fiat_link_regression.ps1") `
            -BaseUrl $BaseUrl `
            -AdminUsername $AdminUsername `
            -AdminPassword $AdminPassword `
            -SellerUsername $SellerUsername `
            -SellerPassword $SellerPassword `
            -BuyerUsername $BuyerUsername `
            -BuyerPassword $BuyerPassword `
            -SecretKey $JwtSecret `
            -Algorithm $JwtAlgorithm
    }
} else {
    Write-Host ""
    Write-Host "SKIP P2P Agent Link Regression (credentials admin/seller/buyer manquants)"
    $results += @{ name = "P2P Agent Link Regression"; status = "SKIP"; error = "Missing admin/seller/buyer credentials" }
}

Write-Host ""
Write-Host "=== Regression Summary ==="
$pass = 0
$fail = 0
$skip = 0
foreach ($r in $results) {
    Write-Host (" - {0}: {1}" -f $r.name, $r.status)
    if ($r.status -eq "PASS") { $pass++ }
    elseif ($r.status -eq "FAIL") {
        $fail++
        if ($r.error) { Write-Host ("   error: {0}" -f $r.error) }
    } else {
        $skip++
    }
}
Write-Host ("PASS={0} FAIL={1} SKIP={2}" -f $pass, $fail, $skip)

if ($fail -gt 0) {
    throw "Regression suite failed with $fail failing step(s)."
}
