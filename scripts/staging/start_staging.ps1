param(
    [string]$EnvFile = ".env.staging",
    [string]$ComposeFile = "docker-compose.staging.yml",
    [string]$ProjectName = "lef-timesheet-staging"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "File $EnvFile non trovato. Copia .env.staging.example in .env.staging e completa i valori prima di avviare lo staging."
}

$values = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
        return
    }
    $parts = $line.Split("=", 2)
    $values[$parts[0].Trim()] = $parts[1].Trim()
}

if (-not $values.ContainsKey("POSTGRES_DB") -or $values["POSTGRES_DB"] -notmatch "staging") {
    throw "POSTGRES_DB deve identificare esplicitamente il database staging (es. lef_timesheet_staging)."
}

$expectedBackend = "apps.common.email_backend.StagingRedirectEmailBackend"
if ($values["EMAIL_BACKEND"] -ne $expectedBackend) {
    throw "Per lo staging EMAIL_BACKEND deve essere $expectedBackend, così nessuna email può raggiungere destinatari reali per errore."
}

if (
    -not $values.ContainsKey("EMAIL_REDIRECT_ALL_TO") -or
    [string]::IsNullOrWhiteSpace($values["EMAIL_REDIRECT_ALL_TO"]) -or
    $values["EMAIL_REDIRECT_ALL_TO"] -match "YOUR_TEST_EMAIL|example\.com"
) {
    throw "Configura EMAIL_REDIRECT_ALL_TO con il tuo indirizzo reale di test."
}

$composeArgs = @(
    "compose",
    "-p", $ProjectName,
    "--env-file", $EnvFile,
    "-f", $ComposeFile,
    "up", "-d", "--build"
)

& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Avvio dell'ambiente staging non riuscito."
}

Write-Host "Staging avviato in modo isolato."
Write-Host "Database: $($values['POSTGRES_DB'])"
Write-Host "Email di staging deviate verso: $($values['EMAIL_REDIRECT_ALL_TO'])"
$stagingPort = "8081"
if ($values.ContainsKey("STAGING_HTTP_PORT") -and -not [string]::IsNullOrWhiteSpace($values["STAGING_HTTP_PORT"])) {
    $stagingPort = $values["STAGING_HTTP_PORT"]
}
Write-Host "Apri: http://localhost:$stagingPort"
