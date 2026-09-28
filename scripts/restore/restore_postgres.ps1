param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,

    [string]$ComposeFile = "docker-compose.yml",

    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$composeArgs = @("compose", "-f", $ComposeFile)

function Get-ContainerEnvironmentValue {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Name
    )

    $value = (& docker @composeArgs exec -T db printenv $Name)
    if ($LASTEXITCODE -ne 0) {
        throw "Impossibile leggere $Name dal container PostgreSQL."
    }

    $value = ($value | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "La variabile $Name è vuota nel container PostgreSQL."
    }

    return $value
}

if (-not $ConfirmRestore) {
    throw "Operazione distruttiva: rieseguire con -ConfirmRestore."
}

if (-not (Test-Path $BackupFile)) {
    throw "File di backup non trovato: $BackupFile"
}

$resolvedBackup = (Resolve-Path $BackupFile).Path
$remoteFile = "/tmp/lef_timesheet_restore.dump"

$dbUser = Get-ContainerEnvironmentValue -Name "POSTGRES_USER"
$dbName = Get-ContainerEnvironmentValue -Name "POSTGRES_DB"

$services = @(
    & docker @composeArgs config --services
)
if ($LASTEXITCODE -ne 0) {
    throw "Impossibile leggere i servizi Docker Compose."
}

$servicesToStop = @("web", "reminder") |
    Where-Object { $services -contains $_ }

Write-Host "Copia del backup nel container PostgreSQL..."
& docker @composeArgs cp $resolvedBackup "db:$remoteFile"
if ($LASTEXITCODE -ne 0) {
    throw "Copia del backup non riuscita."
}

try {
    if ($servicesToStop.Count -gt 0) {
        Write-Host "Arresto temporaneo servizi: $($servicesToStop -join ', ')"
        & docker @composeArgs stop @servicesToStop
        if ($LASTEXITCODE -ne 0) {
            throw "Arresto dei servizi applicativi non riuscito."
        }
    }

    Write-Host "Ripristino database in corso..."
    Write-Host "Database: $dbName"
    Write-Host "Utente: $dbUser"

    & docker @composeArgs exec -T db `
        pg_restore `
        -U $dbUser `
        -d $dbName `
        --clean `
        --if-exists `
        --no-owner `
        $remoteFile

    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore non riuscito."
    }

    Write-Host "Ripristino completato."
}
finally {
    & docker @composeArgs exec -T db rm -f $remoteFile 2>$null

    if ($servicesToStop.Count -gt 0) {
        Write-Host "Riavvio servizi: $($servicesToStop -join ', ')"
        & docker @composeArgs start @servicesToStop
    }
}
