param(
    [int]$Port = 8081
)

$ErrorActionPreference = "Stop"

$checks = @(
    @{
        Name = "Liveness"
        Url = "http://localhost:$Port/health/"
        Expected = 200
    },
    @{
        Name = "Readiness"
        Url = "http://localhost:$Port/health/ready/"
        Expected = 200
    },
    @{
        Name = "Login"
        Url = "http://localhost:$Port/login/"
        Expected = 200
    }
)

foreach ($check in $checks) {
    try {
        $response = Invoke-WebRequest `
            -Uri $check.Url `
            -UseBasicParsing `
            -MaximumRedirection 0 `
            -TimeoutSec 10
    }
    catch {
        if (
            $_.Exception.Response -and
            [int]$_.Exception.Response.StatusCode -eq $check.Expected
        ) {
            Write-Host "[OK] $($check.Name): $($check.Url)"
            continue
        }
        throw "[ERRORE] $($check.Name): $($_.Exception.Message)"
    }

    if ($response.StatusCode -ne $check.Expected) {
        throw "[ERRORE] $($check.Name): atteso $($check.Expected), ricevuto $($response.StatusCode)."
    }

    Write-Host "[OK] $($check.Name): $($check.Url)"
}

Write-Host "Smoke test completato."
