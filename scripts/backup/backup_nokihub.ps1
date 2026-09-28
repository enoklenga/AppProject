param(
    [string]$OutputDirectory = ".\backups",
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$composeArgs = @("compose", "-f", $ComposeFile)

function Get-ContainerEnvironmentValue {
    param([Parameter(Mandatory=$true)][string]$Name)
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
$bundleDirectory = Join-Path $OutputDirectory "nokihub_$timestamp"
New-Item -ItemType Directory -Force -Path $bundleDirectory | Out-Null

$dbRemote = "/tmp/nokihub_$timestamp.dump"
$privateRemote = "/tmp/private_media_$timestamp.tar.gz"
$mediaRemote = "/tmp/media_$timestamp.tar.gz"

$dbLocal = Join-Path $bundleDirectory "database.dump"
$privateLocal = Join-Path $bundleDirectory "private_media.tar.gz"
$mediaLocal = Join-Path $bundleDirectory "media.tar.gz"

$dbUser = Get-ContainerEnvironmentValue -Name "POSTGRES_USER"
$dbName = Get-ContainerEnvironmentValue -Name "POSTGRES_DB"

Write-Host "1/3 Backup PostgreSQL..."
& docker @composeArgs exec -T db pg_dump -U $dbUser -d $dbName -Fc -f $dbRemote
if ($LASTEXITCODE -ne 0) { throw "pg_dump non riuscito." }
& docker @composeArgs cp "db:$dbRemote" $dbLocal
if ($LASTEXITCODE -ne 0) { throw "Copia dump PostgreSQL non riuscita." }

Write-Host "2/3 Backup documenti riservati..."
$privateCode = "import tarfile,pathlib; root=pathlib.Path('/app/private_media'); root.mkdir(parents=True,exist_ok=True); tf=tarfile.open('$privateRemote','w:gz'); tf.add(root,arcname='private_media'); tf.close()"
& docker @composeArgs exec -T web python -c $privateCode
if ($LASTEXITCODE -ne 0) { throw "Backup private_media non riuscito." }
& docker @composeArgs cp "web:$privateRemote" $privateLocal
if ($LASTEXITCODE -ne 0) { throw "Copia private_media non riuscita." }

Write-Host "3/3 Backup media applicativi..."
$mediaCode = "import tarfile,pathlib; root=pathlib.Path('/app/media'); root.mkdir(parents=True,exist_ok=True); tf=tarfile.open('$mediaRemote','w:gz'); tf.add(root,arcname='media'); tf.close()"
& docker @composeArgs exec -T web python -c $mediaCode
if ($LASTEXITCODE -ne 0) { throw "Backup media non riuscito." }
& docker @composeArgs cp "web:$mediaRemote" $mediaLocal
if ($LASTEXITCODE -ne 0) { throw "Copia media non riuscita." }

foreach ($file in @($dbLocal, $privateLocal, $mediaLocal)) {
    if (-not (Test-Path $file)) { throw "Backup mancante: $file" }
    if ((Get-Item $file).Length -le 0) { throw "Backup vuoto: $file" }
}

$manifest = [ordered]@{
    created_at = (Get-Date).ToString("o")
    compose_file = $ComposeFile
    database = "database.dump"
    private_media = "private_media.tar.gz"
    media = "media.tar.gz"
    sha256 = [ordered]@{
        database = (Get-FileHash $dbLocal -Algorithm SHA256).Hash.ToLowerInvariant()
        private_media = (Get-FileHash $privateLocal -Algorithm SHA256).Hash.ToLowerInvariant()
        media = (Get-FileHash $mediaLocal -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $bundleDirectory "manifest.json") -Encoding UTF8

& docker @composeArgs exec -T db rm -f $dbRemote 2>$null
& docker @composeArgs exec -T web rm -f $privateRemote $mediaRemote 2>$null

Write-Host "Backup completo creato: $((Resolve-Path $bundleDirectory).Path)"
Write-Host "Contiene database + private_media + media."
