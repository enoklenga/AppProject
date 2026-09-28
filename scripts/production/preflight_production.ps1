param(
    [string]$EnvFile = ".env.production",
    [string]$ComposeFile = "docker-compose.prod.yml"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "File $EnvFile non trovato. Copiare .env.production.example come .env.production."
}

if (-not (Test-Path $ComposeFile)) {
    throw "File $ComposeFile non trovato."
}

& docker version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker non è disponibile o Docker Desktop non è avviato."
}

& docker compose --env-file $EnvFile -f $ComposeFile config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "La configurazione Docker Compose production non è valida."
}

$requiredNames = @(
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "SITE_URL",
    "EMAIL_BACKEND",
    "WEB_REQUIRE_PASSWORD_CHANGED",
    "API_REQUIRE_PASSWORD_CHANGED",
    "DOCUMENTS_MAX_UPLOAD_SIZE_MB",
    "IMPORT_MAX_UPLOAD_SIZE_MB",
    "WEB_LOGIN_RATE_LIMIT",
    "WEB_LOGIN_IP_RATE_LIMIT",
    "WEB_LOGIN_RATE_WINDOW_SECONDS",
    "API_NUM_PROXIES",
    "API_TRUST_X_FORWARDED_FOR"
)

$content = Get-Content $EnvFile
foreach ($name in $requiredNames) {
    $line = $content | Where-Object { $_ -match "^$name=" } | Select-Object -Last 1
    if (-not $line) {
        throw "Variabile obbligatoria mancante: $name"
    }
    $value = ($line -split "=", 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match "CAMBIARE|example") {
        throw "Variabile non configurata correttamente: $name"
    }
}

foreach ($name in @("WEB_REQUIRE_PASSWORD_CHANGED", "API_REQUIRE_PASSWORD_CHANGED", "API_TRUST_X_FORWARDED_FOR")) {
    $line = $content | Where-Object { $_ -match "^$name=" } | Select-Object -Last 1
    $value = (($line -split "=", 2)[1]).Trim().ToLowerInvariant()
    if ($value -notin @("true", "1", "yes", "on")) {
        throw "$name deve essere abilitata in production."
    }
}

$numericPositive = @(
    "DOCUMENTS_MAX_UPLOAD_SIZE_MB",
    "IMPORT_MAX_UPLOAD_SIZE_MB",
    "WEB_LOGIN_RATE_LIMIT",
    "WEB_LOGIN_IP_RATE_LIMIT",
    "WEB_LOGIN_RATE_WINDOW_SECONDS",
    "API_NUM_PROXIES"
)
foreach ($name in $numericPositive) {
    $line = $content | Where-Object { $_ -match "^$name=" } | Select-Object -Last 1
    $raw = (($line -split "=", 2)[1]).Trim()
    $number = 0
    if (-not [int]::TryParse($raw, [ref]$number) -or $number -lt 1) {
        throw "$name deve essere un intero maggiore di zero."
    }
}

Write-Host "[OK] Docker disponibile"
Write-Host "[OK] Docker Compose production valido"
Write-Host "[OK] Variabili obbligatorie presenti"
Write-Host "Preflight production completato."
