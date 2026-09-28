param(
    [string]$EnvFile = ".env.production",
    [string]$ComposeFile = "docker-compose.prod.yml",
    [int]$Tail = 150
)

& docker compose --env-file $EnvFile -f $ComposeFile logs web nginx reminder db --tail $Tail
