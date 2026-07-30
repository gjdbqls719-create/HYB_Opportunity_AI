[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$contextDirectory = Join-Path $projectRoot "context"
$artifactNames = @(
    "HYB_QUICK_CONTEXT.zip"
    "HYB_FULL_CONTEXT.zip"
    "CONTEXT_MANIFEST.md"
)

foreach ($artifactName in $artifactNames) {
    $artifactPath = Join-Path $contextDirectory $artifactName

    if (Test-Path -LiteralPath $artifactPath -PathType Leaf) {
        Remove-Item -LiteralPath $artifactPath -Force
        Write-Output "Removed $artifactPath"
    }
}
