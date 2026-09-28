param(
    [string]$EnvFile = ".env.staging",
    [string]$ComposeFile = "docker-compose.staging.yml",
    [string]$ProjectName = "lef-timesheet-staging"
)

$ErrorActionPreference = "Stop"

$composeArgs = @(
    "compose",
    "-p", $ProjectName,
    "--env-file", $EnvFile,
    "-f", $ComposeFile,
    "exec", "-T", "web",
    "python", "manage.py", "shell", "-c",
    "from django.conf import settings; from django.core.mail import send_mail; print('BACKEND:', settings.EMAIL_BACKEND); print('REDIRECT:', settings.EMAIL_REDIRECT_ALL_TO); print('RESULT:', send_mail('Test email staging Nokihub','Se ricevi questa email, lo staging sta inviando correttamente e il redirect di sicurezza è attivo.',None,['destinatario-originale@example.invalid'],fail_silently=False))"
)

& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Test email staging non riuscito."
}
