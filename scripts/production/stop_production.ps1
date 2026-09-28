param(
    [string]$EnvFile = ".env.production",
    [string]$ComposeFile = "docker-compose.prod.yml"
)

$ErrorActionPreference = "Stop"

& docker compose --env-file $EnvFile -f $ComposeFile stop nginx reminder web
if ($LASTEXITCODE -ne 0) {
    throw "Arresto dei servizi applicativi production non riuscito."
}

Write-Host "Servizi applicativi production arrestati. Il database e i volumi sono conservati."
