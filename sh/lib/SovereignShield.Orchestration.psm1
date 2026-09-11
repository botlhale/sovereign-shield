Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SovereignShieldRepoRoot {
    return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Get-SovereignShieldTerraform {
    $command = Get-Command terraform.exe -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command terraform -ErrorAction SilentlyContinue }
    if ($command) { return $command.Source }

    $candidate = Get-ChildItem `
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Hashicorp.Terraform_*\terraform.exe" `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { return $candidate.FullName }

    throw "Terraform was not found. Install Terraform 1.9+ or add it to PATH."
}

function Assert-SovereignShieldCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Invoke-SovereignShieldNative {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    Write-Host "    > $FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
    $previousErrorActionPreference = $ErrorActionPreference
    if ($AllowFailure) { $ErrorActionPreference = "Continue" }
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    }
    catch {
        if (-not $AllowFailure) { throw }
        Write-Warning $_.Exception.Message
        $exitCode = 1
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "Command failed with exit code ${exitCode}: $FilePath $($Arguments -join ' ')"
    }
    return $exitCode
}

function Invoke-SovereignShieldTerraform {
    param(
        [Parameter(Mandatory = $true)][string]$Terraform,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    $terraformDirectory = Join-Path $RepoRoot "terraform"
    return Invoke-SovereignShieldNative `
        -FilePath $Terraform `
        -Arguments (@("-chdir=$terraformDirectory") + $Arguments) `
        -AllowFailure:$AllowFailure
}

function Invoke-SovereignShieldTerraformApply {
    param(
        [Parameter(Mandatory = $true)][string]$Terraform,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$VarFile,
        [string[]]$Variables = @()
    )

    $planName = ".sovereignshield-orchestration.tfplan"
    $planArguments = @("plan", "-input=false", "-var-file=$VarFile", "-out=$planName")
    foreach ($variable in $Variables) { $planArguments += "-var=$variable" }

    try {
        Invoke-SovereignShieldTerraform -Terraform $Terraform -RepoRoot $RepoRoot -Arguments $planArguments | Out-Null
        Invoke-SovereignShieldTerraform -Terraform $Terraform -RepoRoot $RepoRoot `
            -Arguments @("apply", "-input=false", $planName) | Out-Null
    }
    finally {
        Remove-Item (Join-Path $RepoRoot "terraform\$planName") -ErrorAction SilentlyContinue
    }
}

function Get-SovereignShieldTerraformOutput {
    param(
        [Parameter(Mandatory = $true)][string]$Terraform,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $terraformDirectory = Join-Path $RepoRoot "terraform"
    $value = & $Terraform "-chdir=$terraformDirectory" output -raw $Name
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
        throw "Terraform output '$Name' is unavailable."
    }
    return ($value | Out-String).Trim()
}

function Set-SovereignShieldWorkspaceAuth {
    param([Parameter(Mandatory = $true)][string]$WorkspaceUrl)

    $env:DATABRICKS_HOST = if ($WorkspaceUrl.StartsWith("http")) {
        $WorkspaceUrl.TrimEnd("/")
    } else {
        "https://$($WorkspaceUrl.TrimEnd('/'))"
    }
    $env:DATABRICKS_AUTH_TYPE = "azure-cli"
    Remove-Item Env:ARM_CLIENT_ID, Env:ARM_CLIENT_SECRET -ErrorAction SilentlyContinue
}

function Test-SovereignShieldEntraUsers {
    param(
        [Parameter(Mandatory = $true)][string]$TenantDomain,
        [string[]]$Prefixes = @("admin_lead", "boc_analyst", "fed_analyst", "econ_researcher")
    )

    $missing = @()
    foreach ($prefix in $Prefixes) {
        $upn = "$prefix@$TenantDomain"
        & az ad user show --id $upn --query id -o tsv 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { $missing += $upn }
    }
    if ($missing.Count -gt 0) {
        throw "Required Entra users do not exist:`n  $($missing -join "`n  ")"
    }
}

Export-ModuleMember -Function @(
    "Get-SovereignShieldRepoRoot",
    "Get-SovereignShieldTerraform",
    "Assert-SovereignShieldCommand",
    "Invoke-SovereignShieldNative",
    "Invoke-SovereignShieldTerraform",
    "Invoke-SovereignShieldTerraformApply",
    "Get-SovereignShieldTerraformOutput",
    "Set-SovereignShieldWorkspaceAuth",
    "Test-SovereignShieldEntraUsers"
)
