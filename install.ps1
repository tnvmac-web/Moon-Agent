# Moon AI Agent — PowerShell Installer
# Run: powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = "Stop"

$InstallDir = "$env:LOCALAPPDATA\moon-ai-agent"
$HermesEnv = "$env:LOCALAPPDATA\hermes\.env"
$RepoUrl   = "https://github.com/tnvmac-web/Moon-Agent.git"

Write-Host "=== Moon AI Agent Installer ===" -ForegroundColor Cyan

# 1. Clone repo
if (Test-Path $InstallDir) {
    Write-Host "Removing existing install..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $InstallDir
}
Write-Host "Cloning repository..." -ForegroundColor Green
git clone $RepoUrl $InstallDir

# 2. Copy NVIDIA_API_KEY from Hermes env
$nvKey = Get-Content $HermesEnv | Select-String "^NVIDIA_API_KEY=" | ForEach-Object { $_ -replace "^NVIDIA_API_KEY=", "" }
if ($nvKey) {
    "NVIDIA_API_KEY=$nvKey" | Out-File -Encoding utf8 "$InstallDir\.env"
    Write-Host "NVIDIA_API_KEY configured" -ForegroundColor Green
} else {
    Write-Host "WARNING: NVIDIA_API_KEY not found in Hermes .env" -ForegroundColor Red
}

# 3. Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Green
cd $InstallDir
pip install -e . | Out-Null

# 4. Verify
Write-Host "`n=== Verification ===" -ForegroundColor Cyan
$env:NVIDIA_API_KEY = $nvKey
$test = moon assistant --backend mock --task "hello" 2>&1
if ($test -match "Mock response") {
    Write-Host "Moon installed successfully at $InstallDir" -ForegroundColor Green
    Write-Host "`nUsage:" -ForegroundColor Yellow
    Write-Host "  moon assistant --backend nvidia-nim --task `"<your task>`""
    Write-Host "  moon researcher --backend nvidia-nim --task `"<task>`""
    Write-Host "  moon coder --backend nvidia-nim --task `"<task>`""
} else {
    Write-Host "Install completed but verification failed. Run manually to debug." -ForegroundColor Red
}
