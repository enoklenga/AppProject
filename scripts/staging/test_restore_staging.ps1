param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,

    [string]$EnvFile = ".env.staging",
    [string]$ComposeFile = "docker-compose.staging.yml",
    [string]$ProjectName = "lef-timesheet-staging"
)

$ErrorActionPreference = "Stop"
$composeArgs = @(
    "compose",
    "-p", $ProjectName,
    "--env-file", $EnvFile,
    "-f", $ComposeFile
)

function Invoke-Compose {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Arguments,
        [string]$ErrorMessage = "Comando Docker Compose non riuscito."
    )

    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

function Get-ContainerEnvironmentValue {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Name
    )

    $value = (& docker @composeArgs exec -T db printenv $Name)
    if ($LASTEXITCODE -ne 0) {
        throw "Impossibile leggere $Name dal database staging."
    }

    $value = ($value | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "La variabile $Name è vuota nel database staging."
    }

    return $value
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Name,
        [string]$DefaultValue = ""
    )

    $line = Get-Content $EnvFile |
        Where-Object {
            $_ -match "^\s*$([regex]::Escape($Name))\s*="
        } |
        Select-Object -Last 1

    if (-not $line) {
        return $DefaultValue
    }

    return (($line -split "=", 2)[1]).Trim()
}

if (-not (Test-Path $BackupFile)) {
    throw "File di backup non trovato: $BackupFile"
}

if (-not (Test-Path $EnvFile)) {
    throw "File $EnvFile non trovato. Copiare prima .env.staging.example come .env.staging."
}

if (-not (Test-Path $ComposeFile)) {
    throw "File Docker Compose non trovato: $ComposeFile"
}

$resolvedBackup = (Resolve-Path $BackupFile).Path
$remoteFile = "/tmp/lef_timesheet_staging_restore.dump"
$stagingPort = Get-DotEnvValue `
    -Name "STAGING_HTTP_PORT" `
    -DefaultValue "8081"

Write-Host ""
Write-Host "=== COLLAUDO STAGING LEF TIMESHEET ==="
Write-Host "Progetto Docker: $ProjectName"
Write-Host "Backup: $resolvedBackup"
Write-Host "Porta web: $stagingPort"
Write-Host ""

Write-Host "1. Avvio database staging isolato..."
Invoke-Compose `
    -Arguments @("up", "-d", "db") `
    -ErrorMessage "Avvio del database staging non riuscito."

$dbUser = Get-ContainerEnvironmentValue -Name "POSTGRES_USER"
$dbName = Get-ContainerEnvironmentValue -Name "POSTGRES_DB"

Write-Host "2. Attesa disponibilità PostgreSQL..."
$databaseReady = $false
for ($attempt = 1; $attempt -le 40; $attempt++) {
    & docker @composeArgs exec -T db `
        pg_isready `
        -U $dbUser `
        -d $dbName *> $null

    if ($LASTEXITCODE -eq 0) {
        $databaseReady = $true
        break
    }

    Start-Sleep -Seconds 2
}

if (-not $databaseReady) {
    throw "Il database staging non è diventato disponibile."
}

Write-Host "3. Copia del backup nel database staging..."
Invoke-Compose `
    -Arguments @("cp", $resolvedBackup, "db:$remoteFile") `
    -ErrorMessage "Copia del backup nel database staging non riuscita."

try {
    Write-Host "4. Ripristino del backup..."
    & docker @composeArgs exec -T db `
        pg_restore `
        -U $dbUser `
        -d $dbName `
        --clean `
        --if-exists `
        --no-owner `
        --no-privileges `
        $remoteFile

    if ($LASTEXITCODE -ne 0) {
        throw "Ripristino del backup nel database staging non riuscito."
    }
}
finally {
    & docker @composeArgs exec -T db rm -f $remoteFile 2>$null
}

Write-Host "5. Avvio applicazione e Nginx staging..."
Invoke-Compose `
    -Arguments @("up", "-d", "--build", "web", "nginx") `
    -ErrorMessage "Avvio dell'applicazione staging non riuscito."

Write-Host "6. Attesa endpoint di readiness..."
$readyUrl = "http://localhost:$stagingPort/health/ready/"
$applicationReady = $false

for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        $response = Invoke-WebRequest `
            -Uri $readyUrl `
            -UseBasicParsing `
            -TimeoutSec 5

        if ($response.StatusCode -eq 200) {
            $applicationReady = $true
            break
        }
    }
    catch {
        # L'applicazione può essere ancora in fase di avvio.
    }

    Start-Sleep -Seconds 2
}

if (-not $applicationReady) {
    & docker @composeArgs logs web --tail=100
    throw "L'applicazione staging non ha superato il readiness check."
}

Write-Host "7. Collaudo applicativo e integrità dati..."
Invoke-Compose `
    -Arguments @(
        "exec",
        "-T",
        "web",
        "python",
        "manage.py",
        "collauda_ambiente"
    ) `
    -ErrorMessage "Il collaudo applicativo ha rilevato errori."

Write-Host "8. Verifica pagina di login..."
$loginUrl = "http://localhost:$stagingPort/login/"
$loginResponse = Invoke-WebRequest `
    -Uri $loginUrl `
    -UseBasicParsing `
    -TimeoutSec 10

if ($loginResponse.StatusCode -ne 200) {
    throw "La pagina di login non risponde correttamente."
}

Write-Host ""
Write-Host "COLLAUDO COMPLETATO CON SUCCESSO."
Write-Host "Ambiente staging: http://localhost:$stagingPort/"
Write-Host "Database operativo originale: non modificato."
Write-Host ""
Write-Host "Al termine usare .\scripts\staging\stop_staging.ps1. Aggiungere -RemoveData solo per eliminare anche il database di prova."
