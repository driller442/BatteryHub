<#
BatteryHub Docker Build and Deployment Script
#>

# Check if Docker is running
function Check-DockerRunning {
    try {
        docker version | Out-Null
        Write-Host "? Docker is running" -ForegroundColor Green
    } catch {
        Write-Host "? Docker is not running. Please start Docker Desktop." -ForegroundColor Red
        exit 1
    }
}

# Stop and remove existing container
function Stop-Container {
    $container = docker ps -a --filter "name=batteryhub" --format "{{.ID}}"
    if ($container) {
        docker stop batteryhub 2>$null
        docker rm batteryhub 2>$null
        Write-Host "? Removed existing batteryhub container" -ForegroundColor Yellow
    }
}

# Build Docker image
function Build-Image {
    Write-Host "Building Docker image..." -ForegroundColor Yellow
    docker build -t driller44/batteryhub:latest .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "? Docker build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "? Successfully built driller44/batteryhub:latest" -ForegroundColor Green
}

# Create data directory if missing
function Create-DataDir {
    if (-not (Test-Path -Path "data")) {
        New-Item -ItemType Directory -Path "data" | Out-Null
        Write-Host "? Created data directory" -ForegroundColor Yellow
    }
}

# Run Docker container
function Run-Container {
    Write-Host "Starting container..." -ForegroundColor Yellow
    docker run -d --name batteryhub -p 5000:5000 -v ${PWD}/data:/app/data -v ${PWD}/config.json:/app/config.json driller44/batteryhub:latest
    if ($LASTEXITCODE -ne 0) {
        Write-Host "? Failed to start container" -ForegroundColor Red
        exit 1
    }
    Write-Host "? Container started successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "=== Access BatteryHub ===" -ForegroundColor Cyan
    Write-Host "Dashboard: http://localhost:5000" -ForegroundColor White
    Write-Host "Logs: .\manage-docker.ps1 logs" -ForegroundColor White
    Write-Host "Stop: .\manage-docker.ps1 stop" -ForegroundColor White
}

# Main execution
Write-Host "=== BatteryHub Docker Build Script ===" -ForegroundColor Cyan
Write-Host ""
Check-DockerRunning
Stop-Container
Build-Image
Create-DataDir
Run-Container

# Option to push to Docker Hub
Write-Host ""
$push = Read-Host "Push to Docker Hub? (y/N)"
if ($push -eq 'y' -or $push -eq 'Y') {
    Write-Host "Logging into Docker Hub..." -ForegroundColor Yellow
    docker login
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Pushing image..." -ForegroundColor Yellow
        docker push driller44/batteryhub:latest
        if ($LASTEXITCODE -eq 0) {
            Write-Host "? Successfully pushed to Docker Hub" -ForegroundColor Green
            Write-Host "Pull command: docker pull driller44/batteryhub:latest" -ForegroundColor White
        } else {
            Write-Host "? Failed to push to Docker Hub" -ForegroundColor Red
        }
    } else {
        Write-Host "? Docker login failed" -ForegroundColor Red
    }
}
