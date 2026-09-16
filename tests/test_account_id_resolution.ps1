$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\sh\lib\SovereignShield.Orchestration.psm1") -Force

function global:az {
    $global:LASTEXITCODE = 0
    if ($args -contains "show") { return "configured-id" }
    return '["old-id","configured-id"]'
}

try {
    $resolved = Resolve-SovereignShieldApplicationId -Name "same-display-name" -ClientId "configured-id"
    if ($resolved -ne "configured-id") { throw "Explicit application identity was not preserved." }
    $refused = $false
    try { Resolve-SovereignShieldApplicationId -Name "same-display-name" | Out-Null }
    catch { $refused = $_.Exception.Message -match "found 2" }
    if (-not $refused) { throw "Ambiguous display names must fail closed." }
    $refused = $false
    try { Resolve-SovereignShieldApplicationId -Name "same-display-name" -ClientId "unverified-id" | Out-Null }
    catch { $refused = $_.Exception.Message -match "could not be verified" }
    if (-not $refused) { throw "An unverified explicit ID was accepted." }
    Write-Output "Explicit application identity and ambiguous-name rejection checks passed."
} finally {
    Remove-Item Function:\az
}