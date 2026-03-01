param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$Username,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [string]$RecipientPhone = "+25770000001",
    [decimal]$AmountUsdc = 10,
    [string]$LumicashRef = "TEST-LUMICASH-REF-001"
)

$ErrorActionPreference = "Stop"

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

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) { throw $Message }
}

function New-AuthHeaders {
    param(
        [Parameter(Mandatory = $true)][string]$Token
    )
    return @{
        Authorization = "Bearer $Token"
        "Content-Type" = "application/json"
    }
}

Write-Host "== Payout + Agent Email Regression (USDC test) =="

# 1) Login (admin/operator recommended when SANDBOX_ADMIN_ONLY=true)
$loginResp = Invoke-RestMethod -Method Post `
    -Uri "$BaseUrl/auth/login" `
    -ContentType "application/x-www-form-urlencoded" `
    -Body @{ username = $Username; password = $Password }

if (-not $loginResp.access_token) { throw "Login failed: access_token absent" }
$token = "$($loginResp.access_token)"
$authHeaders = New-AuthHeaders -Token $token
Write-Host "Login OK"

# 2) Create escrow order in sandbox with USDC test amount
$createHeaders = @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
    "X-SANDBOX" = "true"
    "X-SANDBOX-SCENARIO" = "CONFIRMATION_DELAY"
}
$createBody = @{
    amount_usdc = $AmountUsdc
    recipient_name = "Payout Regression"
    recipient_phone = $RecipientPhone
    deposit_network = "POLYGON"
    deposit_required_confirmations = 1
} | ConvertTo-Json

$order = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders" -Headers $createHeaders -Body $createBody
$orderId = "$($order.id)"
Assert-True ($orderId.Length -gt 0) "Order creation failed: id absent"
Write-Host "Order created: $orderId"

# 3) Sandbox transition CREATED -> FUNDED -> SWAPPED
$fundResp = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders/$orderId/sandbox/FUND" -Headers $authHeaders
if ("$($fundResp.escrow_status)" -ne "FUNDED") {
    throw "Expected FUNDED after sandbox/FUND, got '$($fundResp.escrow_status)'"
}
Write-Host "FUND OK"

$swapResp = Invoke-ApiJson -Method Post -Uri "$BaseUrl/escrow/orders/$orderId/sandbox/SWAP" -Headers $authHeaders
$swapStatus = "$($swapResp.escrow_status)"
if (@("SWAPPED", "PAYOUT_PENDING") -notcontains $swapStatus) {
    throw "Expected SWAPPED or PAYOUT_PENDING after sandbox/SWAP, got '$swapStatus'"
}
Write-Host "SWAP OK (status=$swapStatus)"

# 4) Read order state to get BIF amount
$orderState = Invoke-ApiJson -Method Get -Uri "$BaseUrl/escrow/orders/$orderId" -Headers @{ Authorization = "Bearer $token" }
$bifTarget = [decimal]$orderState.bif_target
Assert-True ($bifTarget -gt 0) "Invalid bif_target from order state"
Write-Host "Order bif_target: $bifTarget"

# 5) Ensure assignment exists (this call triggers assign_agent_and_notify if not already done)
$initBody = @{
    order_id = $orderId
    amount_bif = [double]$bifTarget
} | ConvertTo-Json
$initResp = Invoke-ApiJson -Method Post -Uri "$BaseUrl/ops/payouts/initiate" -Headers $authHeaders -Body $initBody

Assert-True ($initResp.ok -eq $true) "ops/payouts/initiate failed"
$assignmentId = "$($initResp.assignment_id)"
$agentId = "$($initResp.agent_id)"
Assert-True ($assignmentId.Length -gt 0) "assignment_id absent"
Assert-True ($agentId.Length -gt 0) "agent_id absent"
Write-Host "Assignment ready: assignment_id=$assignmentId agent_id=$agentId"

# NOTE: assign_agent_and_notify triggers best-effort email to agent here.
Write-Host "Agent email notification trigger executed via assign_agent_and_notify."

# 6) Verify assignment is listed for the agent
$agentAssignments = Invoke-ApiJson -Method Get -Uri "$BaseUrl/agent/assignments?agent_id=$agentId"
$item = $null
foreach ($a in $agentAssignments.items) {
    if ("$($a.id)" -eq $assignmentId) { $item = $a; break }
}
Assert-True ($null -ne $item) "Assignment not found in /agent/assignments for agent_id=$agentId"
if ("$($item.status)" -ne "ASSIGNED" -and "$($item.status)" -ne "CONFIRMED") {
    throw "Unexpected assignment status: $($item.status)"
}
Write-Host "Assignment listing OK (status=$($item.status))"

# 7) Confirm payout as agent (simulated)
if ("$($item.status)" -eq "ASSIGNED") {
    $confirmBody = @{
        agent_id = $agentId
        lumicash_ref = $LumicashRef
        note = "Regression payout confirmation"
    } | ConvertTo-Json

    $confirmResp = Invoke-ApiJson -Method Post -Uri "$BaseUrl/agent/assignments/$assignmentId/confirm" -Headers $authHeaders -Body $confirmBody
    Assert-True ($confirmResp.ok -eq $true) "Assignment confirm failed"
    Write-Host "Assignment confirm OK"
}

# 8) Final order status check
$finalOrder = Invoke-ApiJson -Method Get -Uri "$BaseUrl/escrow/orders/$orderId" -Headers @{ Authorization = "Bearer $token" }
$finalStatus = "$($finalOrder.status)"
if (@("PAYOUT_PENDING", "PAID_OUT") -notcontains $finalStatus) {
    throw "Unexpected final order status: $finalStatus"
}
Write-Host "Final order status: $finalStatus"

Write-Host "`nAll checks passed."
Write-Host "Summary:"
Write-Host " - order_id: $orderId"
Write-Host " - assignment_id: $assignmentId"
Write-Host " - agent_id: $agentId"
Write-Host " - final_status: $finalStatus"
