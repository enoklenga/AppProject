param(
    [string]$EnvFile = ".env.production",
    [string]$ComposeFile = "docker-compose.prod.yml"
)

$ErrorActionPreference = "Stop"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\production\preflight_production.ps1" -EnvFile $EnvFile -ComposeFile $ComposeFile
if ($LASTEXITCODE -ne 0) {
    throw "Preflight production non superato."
}

& docker compose --env-file $EnvFile -f $ComposeFile up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Avvio production non riuscito."
}

& docker compose --env-file $EnvFile -f $ComposeFile ps
if ($LASTEXITCODE -ne 0) {
    throw "Impossibile leggere lo stato production."
}

Write-Host "Production avviata. Controllare i log e gli endpoint health."
