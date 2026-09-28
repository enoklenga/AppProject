param(
    [string]$BaseUrl = "http://localhost",
    [string]$EnvFile = ".env.production",
    [string]$ComposeFile = "docker-compose.prod.yml"
)

$ErrorActionPreference = "Stop"

& docker compose --env-file $EnvFile -f $ComposeFile ps
if ($LASTEXITCODE -ne 0) {
    throw "Impossibile leggere lo stato dei container production."
}

$urls = @(
    "$BaseUrl/health/",
    "$BaseUrl/health/ready/",
    "$BaseUrl/login/"
)

foreach ($url in $urls) {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) {
        throw "Endpoint non valido: $url"
    }
    Write-Host "[OK] $url"
}

& docker compose --env-file $EnvFile -f $ComposeFile exec -T web python manage.py verifica_go_live
if ($LASTEXITCODE -ne 0) {
    throw "Verifica go-live Django non superata."
}

Write-Host "Controllo production completato."
