$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\sh\lib\SovereignShield.Orchestration.psm1") -Force

function global:Invoke-SovereignShieldProgressProbe {
    param([string]$ExitStatus)
    Write-Output "NATIVE_PROGRESS_VISIBLE"
    $global:LASTEXITCODE = [int]$ExitStatus
}

try {
    $progress = @()
    Invoke-SovereignShieldNative -FilePath "Invoke-SovereignShieldProgressProbe" `
        -Arguments @("0") -InformationVariable progress | Out-Null
    if (($progress | Out-String) -notmatch "NATIVE_PROGRESS_VISIBLE") {
        throw "Native progress was hidden by the caller's Out-Null."
    }
    $failed = $false
    try {
        Invoke-SovereignShieldNative -FilePath "Invoke-SovereignShieldProgressProbe" -Arguments @("17") | Out-Null
    } catch {
        $failed = $_.Exception.Message -match "exit code 17"
    }
    if (-not $failed) { throw "The progress change lost native failure propagation." }
    Write-Output "Orchestration progress and failure propagation checks passed."
} finally {
    Remove-Item Function:\Invoke-SovereignShieldProgressProbe
}