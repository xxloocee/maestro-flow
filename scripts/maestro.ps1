Set-StrictMode -Version Latest

function Set-MaestroProvider {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("openai", "openrouter", "deepseek", "moonshot", "qwen", "siliconflow", "volcengine", "custom")]
        [string]$Provider,
        [Parameter(Mandatory = $true)]
        [string]$ApiKey,
        [string]$Model
    )

    $baseUrlMap = @{
        openai = ""
        openrouter = "https://openrouter.ai/api/v1"
        deepseek = "https://api.deepseek.com/v1"
        moonshot = "https://api.moonshot.cn/v1"
        qwen = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        siliconflow = "https://api.siliconflow.cn/v1"
        volcengine = "https://ark.cn-beijing.volces.com/api/v3"
        custom = ""
    }

    $env:MAESTRO_PROVIDER = $Provider
    $env:MAESTRO_API_KEY = $ApiKey

    $base = $baseUrlMap[$Provider]
    if ([string]::IsNullOrWhiteSpace($base)) {
        Remove-Item Env:MAESTRO_BASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:MAESTRO_BASE_URL = $base
    }

    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $env:MAESTRO_MODEL = $Model
    }

    Write-Host "Provider set to $Provider"
    if ($env:MAESTRO_BASE_URL) {
        Write-Host "Base URL: $($env:MAESTRO_BASE_URL)"
    }
    Write-Host "Model: $($env:MAESTRO_MODEL)"
}

function Invoke-MaestroRun {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Requirement,
        [switch]$Mock,
        [switch]$SkipGates
    )

    $args = @("-m", "maestro_flow.cli", "run", "--requirement", $Requirement)
    if ($Mock) { $args += "--mock" }
    if ($SkipGates) { $args += "--skip-gates" }
    python @args
}

function New-MaestroSpec {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    python -m maestro_flow.cli spec init --name $Name
}

function Invoke-MaestroSpecRun {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$SpecFile,
        [switch]$Mock,
        [switch]$SkipGates
    )

    $args = @("-m", "maestro_flow.cli", "spec", "run", "--file", $SpecFile)
    if ($Mock) { $args += "--mock" }
    if ($SkipGates) { $args += "--skip-gates" }
    python @args
}
