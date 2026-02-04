<#
BatteryHub Docker Management Script
#>

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet('start','stop','restart','logs','status','remove','help')]
    [string]$Command
)

# Function to display help
function Show-Help {
    Write-Host "BatteryHub Docker Management Script" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\manage-docker.ps1 <command>" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Available commands:" -ForegroundColor Green
    Write-Host "  start    - Start the container"
    Write-Host "  stop     - Stop the container"
    Write-Host "  restart  - Restart the container"
    Write-Host "  logs     - Show live logs"
    Write-Host "  status   - Show container status"
    Write-Host "  remove   - Stop and remove container"
    Write-Host "  help     - Show this help message"
    exit 0
}

# Check if Docker is running
function Check-DockerRunning {
    try {
        docker version | Out-Null
    } catch {
        Write-Host "✗ Docker is not running. Please start Docker Desktop." -ForegroundColor Red
        exit 1
    }
}

# Start container
function Start-Container {
    $running = docker ps --filter "name=batteryhub" --format "{{.Names}}"
    if ($running -eq "batteryhub") {
        Write-Host "✓ Container is already running" -ForegroundColor Yellow
        Write-Host "Dashboard: http://localhost:5000" -ForegroundColor White
        return
    }
    docker start batteryhub
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to start container" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Container started successfully!" -ForegroundColor Green
    Write-Host "Dashboard: http://localhost:5000" -ForegroundColor White
}

# Stop container
function Stop-Container {
    docker stop batteryhub
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to stop container" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Container stopped" -ForegroundColor Green
}

# Restart container
function Restart-Container {
    docker restart batteryhub
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to restart container" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Container restarted" -ForegroundColor Green
    Write-Host "Dashboard: http://localhost:5000" -ForegroundColor White
}

# Show logs
function Show-Logs {
    Write-Host "Showing logs (Ctrl+C to exit)..." -ForegroundColor Yellow
    docker logs -f batteryhub
}

# Show status
function Show-Status {
    Write-Host "Container Status:" -ForegroundColor Cyan
    docker ps -a --filter "name=batteryhub" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# Remove container
function Remove-Container {
    docker stop batteryhub 2>$null
    docker rm batteryhub
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to remove container" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Container removed" -ForegroundColor Green
}

# Main execution
if ($Command -eq 'help') {
    Show-Help
}

Check-DockerRunning

switch ($Command) {
    'start'    { Start-Container }
    'stop'     { Stop-Container }
    'restart'  { Restart-Container }
    'logs'     { Show-Logs }
    'status'   { Show-Status }
    'remove'   { Remove-Container }
}
