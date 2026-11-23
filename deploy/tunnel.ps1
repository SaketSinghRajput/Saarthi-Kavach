<#
 No-account fallback: expose the LOCAL app (already running on :8000) through a Cloudflare quick tunnel.
 Usage:  powershell -ExecutionPolicy Bypass -File deploy\tunnel.ps1 [-Port 8000]
 Downloads cloudflared.exe to tools\bin if missing (retried), then runs it and prints the https URL.
 The URL is random and lives ONLY while this window and the laptop stay on. Testing/backup, not the submission URL.
 Set APP_PASSCODE in .env before starting the app: the tunnel makes it reachable by anyone with the link.
#>
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$bin = Join-Path $root 'tools\bin'
$exe = Join-Path $bin 'cloudflared.exe'
if (-not (Test-Path $exe)) {
    New-Item -ItemType Directory -Force $bin | Out-Null
    $url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
    for ($i = 1; $i -le 3; $i++) {
        try { Invoke-WebRequest -Uri $url -OutFile "$exe.part" -UseBasicParsing; Move-Item "$exe.part" $exe -Force; break }
        catch { if ($i -eq 3) { throw "download failed after 3 tries: $($_.Exception.Message)" }; Start-Sleep -Seconds (2 * $i) }
    }
}
try { Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3 | Out-Null }
catch { throw "nothing answering on http://127.0.0.1:$Port - start the app first" }
Write-Host "WARNING: this link works only while this laptop is on and this window is open." -ForegroundColor Yellow
Write-Host "Look for the https://<random>.trycloudflare.com line below (also printed by cloudflared)." -ForegroundColor Cyan
& $exe tunnel --url "http://127.0.0.1:$Port" --no-autoupdate
