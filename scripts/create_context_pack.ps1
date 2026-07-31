[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = Split-Path -Parent $PSScriptRoot
$contextDirectory = Join-Path $projectRoot "context"
$quickArchive = Join-Path $contextDirectory "HYB_QUICK_CONTEXT.zip"
$fullArchive = Join-Path $contextDirectory "HYB_FULL_CONTEXT.zip"
$manifestPath = Join-Path $contextDirectory "CONTEXT_MANIFEST.md"

$quickContextFiles = @(
    "docs/01_CONTEXT/PROJECT_STATUS.md"
    "docs/01_CONTEXT/PROJECT_CONTEXT.md"
    "docs/DOCUMENT_STATUS.md"
    "docs/07_ROADMAP/ROADMAP.md"
    "docs/04_DEVELOPMENT/CHANGELOG.md"
    "docs/04_DEVELOPMENT/AI_DEVELOPMENT_LOG.md"
)

$excludedDirectoryNames = @(
    ".git"
    ".venv"
    "__pycache__"
    ".pytest_cache"
    "htmlcov"
)

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $rootUri = [System.Uri]::new(
        $projectRoot.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar
        ) + [System.IO.Path]::DirectorySeparatorChar
    )
    $pathUri = [System.Uri]::new($Path)

    return [System.Uri]::UnescapeDataString(
        $rootUri.MakeRelativeUri($pathUri).ToString()
    )
}

function Test-ExcludedFile {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo]$File
    )

    if ($File.Extension -in @(".pyc", ".db", ".sqlite")) {
        return $true
    }

    if (
        $File.Name -eq ".env" -or
        (
            $File.Name -like ".env.*" -and
            $File.Name -ne ".env.example"
        )
    ) {
        return $true
    }

    return (
        $File.Extension -eq ".zip" -and
        $File.DirectoryName -eq $contextDirectory
    )
}

function Get-FullContextFiles {
    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    $directories = [System.Collections.Generic.Stack[string]]::new()
    $directories.Push($projectRoot)

    while ($directories.Count -gt 0) {
        $currentDirectory = $directories.Pop()

        foreach (
            $directory in Get-ChildItem `
                -LiteralPath $currentDirectory `
                -Directory `
                -Force
        ) {
            if ($directory.Name -notin $excludedDirectoryNames) {
                $directories.Push($directory.FullName)
            }
        }

        foreach (
            $file in Get-ChildItem `
                -LiteralPath $currentDirectory `
                -File `
                -Force
        ) {
            if (-not (Test-ExcludedFile -File $file)) {
                $files.Add($file)
            }
        }
    }

    return $files | Sort-Object FullName
}

function New-ZipArchive {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo[]]$Files,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $archive = [System.IO.Compression.ZipFile]::Open(
        $Destination,
        [System.IO.Compression.ZipArchiveMode]::Create
    )

    try {
        foreach ($file in $Files) {
            $entryName = (Get-RelativePath -Path $file.FullName) `
                -replace "\\", "/"

            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $file.FullName,
                $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    }
    finally {
        $archive.Dispose()
    }
}

New-Item -ItemType Directory -Path $contextDirectory -Force | Out-Null
& (Join-Path $PSScriptRoot "cleanup_context_pack.ps1")

$quickFiles = foreach ($relativePath in $quickContextFiles) {
    $fullPath = Join-Path $projectRoot $relativePath

    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Required Quick Context file not found: $relativePath"
    }

    Get-Item -LiteralPath $fullPath
}

$fullFiles = @(Get-FullContextFiles)
$generatedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
$manifestContent = @"
# HYB Context Pack Manifest

- Generated: $generatedAt
- Quick archive: `HYB_QUICK_CONTEXT.zip`
- Quick files: $($quickFiles.Count)
- Full archive: `HYB_FULL_CONTEXT.zip`
- Full files: $($fullFiles.Count + 1)

## Quick Context Files

$(
    ($quickContextFiles | ForEach-Object { "- ``$_``" }) -join "`n"
)

## Full Context Exclusions

- ``.git/``
- ``.venv/``
- ``**/__pycache__/``
- ``.pytest_cache/``
- ``htmlcov/``
- ``*.pyc``
- ``*.db``
- ``*.sqlite``
- ``.env`` and local ``.env.*`` files except ``.env.example``
- Existing ``context/*.zip`` files
"@

Set-Content `
    -LiteralPath $manifestPath `
    -Value $manifestContent `
    -Encoding utf8

New-ZipArchive -Files $quickFiles -Destination $quickArchive
$fullArchiveFiles = @($fullFiles) + (Get-Item -LiteralPath $manifestPath)
New-ZipArchive -Files $fullArchiveFiles -Destination $fullArchive

Write-Output "Created $quickArchive"
Write-Output "Created $fullArchive"
Write-Output "Created $manifestPath"
