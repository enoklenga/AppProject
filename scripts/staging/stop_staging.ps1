param(
    [string]$EnvFile = ".env.staging",
    [string]$ComposeFile = "docker-compose.staging.yml",
    [string]$ProjectName = "lef-timesheet-staging",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"

$composeArgs = @(
    "compose",
    "-p", $ProjectName,
    "--env-file", $EnvFile,
    "-f", $ComposeFile,
    "down"
)

if ($RemoveData) {
    $composeArgs += "-v"
}

& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Arresto dell'ambiente staging non riuscito."
}

if ($RemoveData) {
    Write-Host "Ambiente staging arrestato e volumi di prova eliminati. Il database operativo non è stato toccato."
}
else {
    Write-Host "Ambiente staging arrestato. Il volume del database di prova è stato conservato."
}
