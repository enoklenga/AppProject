param(
    [Parameter(Mandatory=$true)]
    [string]$BackupDirectory,

    [string]$ComposeFile = "docker-compose.yml",

    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$composeArgs = @("compose", "-f", $ComposeFile)

if (-not $ConfirmRestore) {
    throw "Operazione distruttiva: rieseguire con -ConfirmRestore."
}
if (-not (Test-Path $BackupDirectory)) {
    throw "Directory di backup non trovata: $BackupDirectory"
}

$bundle = (Resolve-Path $BackupDirectory).Path
$dbFile = Join-Path $bundle "database.dump"
$privateFile = Join-Path $bundle "private_media.tar.gz"
$mediaFile = Join-Path $bundle "media.tar.gz"
foreach ($file in @($dbFile, $privateFile, $mediaFile)) {
    if (-not (Test-Path $file)) { throw "File di backup mancante: $file" }
}

function Get-ContainerEnvironmentValue {
    param([Parameter(Mandatory=$true)][string]$Name)
    $value = (& docker @composeArgs exec -T db printenv $Name)
    if ($LASTEXITCODE -ne 0) { throw "Impossibile leggere $Name." }
    return ($value | Out-String).Trim()
}

$dbUser = Get-ContainerEnvironmentValue -Name "POSTGRES_USER"
$dbName = Get-ContainerEnvironmentValue -Name "POSTGRES_DB"
$dbRemote = "/tmp/nokihub_restore.dump"
$privateRemote = "/tmp/private_media_restore.tar.gz"
$mediaRemote = "/tmp/media_restore.tar.gz"

$services = @(& docker @composeArgs config --services)
if ($LASTEXITCODE -ne 0) { throw "Impossibile leggere i servizi Docker Compose." }
$toStop = @("nginx", "reminder", "web") | Where-Object { $services -contains $_ }

Write-Host "Arresto servizi applicativi: $($toStop -join ', ')"
if ($toStop.Count -gt 0) {
    & docker @composeArgs stop @toStop
    if ($LASTEXITCODE -ne 0) { throw "Arresto servizi non riuscito." }
}

try {
    Write-Host "Ripristino database..."
    & docker @composeArgs cp $dbFile "db:$dbRemote"
    if ($LASTEXITCODE -ne 0) { throw "Copia dump nel container non riuscita." }
    & docker @composeArgs exec -T db pg_restore -U $dbUser -d $dbName --clean --if-exists --no-owner $dbRemote
    if ($LASTEXITCODE -ne 0) { throw "pg_restore non riuscito." }

    Write-Host "Avvio web isolato per il ripristino dei file..."
    & docker @composeArgs start web
    if ($LASTEXITCODE -ne 0) { throw "Avvio web non riuscito." }

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        & docker @composeArgs exec -T web python -c "print('ready')" *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw "Il container web non è diventato disponibile." }

    & docker @composeArgs cp $privateFile "web:$privateRemote"
    if ($LASTEXITCODE -ne 0) { throw "Copia private_media non riuscita." }
    & docker @composeArgs cp $mediaFile "web:$mediaRemote"
    if ($LASTEXITCODE -ne 0) { throw "Copia media non riuscita." }

    $restoreCode = @"
import pathlib, shutil, tarfile
for root_name, archive_name in [('private_media', '$privateRemote'), ('media', '$mediaRemote')]:
    root = pathlib.Path('/app') / root_name
    root.mkdir(parents=True, exist_ok=True)
    for child in root.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    with tarfile.open(archive_name, 'r:gz') as archive:
        archive.extractall('/app', filter='data')
"@
    & docker @composeArgs exec -T web python -c $restoreCode
    if ($LASTEXITCODE -ne 0) { throw "Ripristino file applicativi non riuscito." }

    & docker @composeArgs exec -T web rm -f $privateRemote $mediaRemote 2>$null
    & docker @composeArgs exec -T db rm -f $dbRemote 2>$null

    foreach ($service in @("reminder", "nginx")) {
        if ($services -contains $service) {
            & docker @composeArgs start $service
            if ($LASTEXITCODE -ne 0) { throw "Riavvio $service non riuscito." }
        }
    }

    Write-Host "Ripristino completo terminato: database + private_media + media."
}
catch {
    Write-Error $_
    Write-Warning "Nginx non viene riavviato automaticamente dopo un restore fallito."
    throw
}
