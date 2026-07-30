# Run the Docker-only tests inside the backend container.
# These tests require WeasyPrint with GTK/Pango (not available on Windows natively).
#
# Prerequisites:
#   docker compose up -d backend
#
# Usage:
#   .\scripts\run_docker_tests.ps1              # Run docker_only marked tests
#   .\scripts\run_docker_tests.ps1 --all        # Run ALL tests (unit + integration + e2e)
#   .\scripts\run_docker_tests.ps1 --verbose    # Verbose output

param(
    [switch]$All,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

# Check if backend container is running
$containerStatus = docker compose ps backend --format "{{.Status}}" 2>$null
if (-not $containerStatus -or $containerStatus -notmatch "Up") {
    Write-Host "Starting backend container..." -ForegroundColor Yellow
    docker compose up -d backend
    Write-Host "Waiting for backend to be healthy..."
    Start-Sleep -Seconds 10
}

$pytestArgs = @("tests/")

if ($All) {
    # Run everything — no marker filter
    Write-Host "Running ALL tests in Docker..." -ForegroundColor Cyan
} else {
    # Only Docker-dependent tests
    $pytestArgs += @("-m", "docker_only")
    Write-Host "Running docker_only tests..." -ForegroundColor Cyan
}

if ($Verbose) {
    $pytestArgs += @("-v", "--tb=long")
} else {
    $pytestArgs += @("--tb=short", "-q")
}

$cmd = "python -m pytest $($pytestArgs -join ' ')"
Write-Host "  > docker compose exec backend $cmd" -ForegroundColor DarkGray

docker compose exec backend python -m pytest @pytestArgs

$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Host "`nAll Docker tests passed!" -ForegroundColor Green
} else {
    Write-Host "`nSome tests failed (exit code: $exitCode)" -ForegroundColor Red
}

exit $exitCode
