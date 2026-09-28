param(
    [string]$OutputDirectory = ".\backups",
    [string]$ComposeFile = "docker-compose.yml"
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

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$remoteFile = "/tmp/lef_timesheet_$timestamp.dump"
$localFile = Join-Path $OutputDirectory "lef_timesheet_$timestamp.dump"

$dbUser = Get-ContainerEnvironmentValue -Name "POSTGRES_USER"
$dbName = Get-ContainerEnvironmentValue -Name "POSTGRES_DB"

Write-Host "Creazione backup PostgreSQL..."
Write-Host "Database: $dbName"
Write-Host "Utente: $dbUser"

try {
    & docker @composeArgs exec -T db `
        pg_dump `
        -U $dbUser `
        -d $dbName `
        -Fc `
        -f $remoteFile

    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump non riuscito."
    }

    & docker @composeArgs cp "db:$remoteFile" $localFile

    if ($LASTEXITCODE -ne 0) {
        throw "Copia del backup non riuscita."
    }

    if (-not (Test-Path $localFile)) {
        throw "Il file di backup non è stato creato localmente."
    }

    $backupInfo = Get-Item $localFile
    if ($backupInfo.Length -le 0) {
        throw "Il file di backup creato è vuoto."
    }

    Write-Host "Backup creato: $($backupInfo.FullName)"
    Write-Host "Dimensione: $($backupInfo.Length) byte"
}
finally {
    & docker @composeArgs exec -T db rm -f $remoteFile 2>$null
}
