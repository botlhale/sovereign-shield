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

function Get-SovereignShieldPython {
    param([string]$RepoRoot)
    foreach ($relative in @(".venv\Scripts\python.exe", ".venv/bin/python")) {
        $candidate = Join-Path $RepoRoot $relative
        if (Test-Path $candidate) { return $candidate }
    }
    foreach ($name in @("python", "python3")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) { return $candidate.Source }
    }
    throw "Python is required for lifecycle state and plan verification."
}

function Enter-SovereignShieldLifecycleLock {
    param([string]$RepoRoot)
    $directory = Join-Path $RepoRoot ".pytest_cache"
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    try {
        return [System.IO.File]::Open((Join-Path $directory "sovereignshield.lifecycle.lock"),
            [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        throw "Another lifecycle operation holds this checkout's lock."
    }
}

function Get-SovereignShieldDeploymentSettings {
    param([string]$Terraform, [string]$RepoRoot)
    $stateJson = & $Terraform "-chdir=$(Join-Path $RepoRoot 'terraform')" show -json
    if ($LASTEXITCODE -ne 0) { throw "Terraform state inspection failed; readiness was not assumed." }
    $python = Get-SovereignShieldPython -RepoRoot $RepoRoot
    $settings = $stateJson | & $python (Join-Path $RepoRoot "sh/deployment_state.py") inspect
    if ($LASTEXITCODE -ne 0) { throw "Could not determine deployment readiness." }
    return ($settings | ConvertFrom-Json)
}

function Get-SovereignShieldReadinessVariables {
    param([object]$Settings)
    foreach ($name in @("account_groups_ready", "grant_tables", "deploy_dissemination_gateway")) {
        "${name}=$($Settings.$name.ToString().ToLowerInvariant())"
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
        [string[]]$Variables = @(),
        [switch]$ApproveComputeScale
    )

    $planName = ".sovereignshield-$([guid]::NewGuid().ToString('N')).tfplan"
    $planArguments = @("plan", "-input=false", "-var-file=$VarFile", "-out=$planName")
    foreach ($variable in $Variables) { $planArguments += "-var=$variable" }

    try {
        Invoke-SovereignShieldTerraform -Terraform $Terraform -RepoRoot $RepoRoot -Arguments $planArguments | Out-Null
        $planJson = & $Terraform "-chdir=$(Join-Path $RepoRoot 'terraform')" show -json $planName
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect the plan; apply was refused." }
        $python = Get-SovereignShieldPython -RepoRoot $RepoRoot
        $guardArguments = @((Join-Path $RepoRoot "sh/deployment_state.py"), "check-plan")
        if ($ApproveComputeScale) { $guardArguments += "--approve-compute-scale" }
        $planJson | & $python @guardArguments
        if ($LASTEXITCODE -ne 0) { throw "Lifecycle plan guard refused apply." }
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
    Remove-Item Env:DATABRICKS_ACCOUNT_ID, Env:DATABRICKS_AZURE_RESOURCE_ID, `
        Env:DATABRICKS_AZURE_TENANT_ID, Env:DATABRICKS_CONFIG_PROFILE -ErrorAction SilentlyContinue
}

function Test-SovereignShieldEntraUsers {
    param(
        [Parameter(Mandatory = $true)][string]$TenantDomain,
        [string[]]$Prefixes = @("admin_lead", "submitter_ca", "submitter_us", "econ_researcher")
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
    "Get-SovereignShieldPython",
    "Enter-SovereignShieldLifecycleLock",
    "Get-SovereignShieldDeploymentSettings",
    "Get-SovereignShieldReadinessVariables",
    "Assert-SovereignShieldCommand",
    "Invoke-SovereignShieldNative",
    "Invoke-SovereignShieldTerraform",
    "Invoke-SovereignShieldTerraformApply",
    "Get-SovereignShieldTerraformOutput",
    "Set-SovereignShieldWorkspaceAuth",
    "Test-SovereignShieldEntraUsers"
)
