$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root 'libs/Doxygen'
$runtime = Join-Path $root '.runtime/doxygen/bin'
$metadata = [IO.File]::ReadAllText((Join-Path $vendor 'UE5-UPSTREAM.json')) | ConvertFrom-Json
$archive = $env:CODESTYLE_DOXYGEN_ARCHIVE
if (-not $archive) {
    $archive = Join-Path $vendor $metadata.runtime.archive
}
$executable = Join-Path $runtime 'doxygen.exe'

if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $metadata.runtime.archive_sha256) {
    throw 'Doxygen archive checksum mismatch'
}
if (!(Test-Path -LiteralPath $executable -PathType Leaf) -or
    (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash -ne $metadata.runtime.executable_sha256) {
    Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
    if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash -ne $metadata.runtime.executable_sha256) {
        throw 'Doxygen executable checksum mismatch'
    }
}
& $executable --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
