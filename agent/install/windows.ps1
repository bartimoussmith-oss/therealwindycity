# windycity-agent — Windows installer (no admin required for the user install).
# Run:  powershell -ExecutionPolicy Bypass -File windows.ps1
$ErrorActionPreference = "Stop"
Write-Host "== windycity-agent :: Windows install ==" -ForegroundColor Cyan

$py = $null
foreach ($cand in @("python", "py")) {
  try { $null = & $cand -V 2>$null; $py = $cand; break } catch {}
}
if (-not $py) {
  Write-Host "Python not found. Install it (no admin needed):" -ForegroundColor Yellow
  Write-Host "  winget install Python.Python.3.12"
  Write-Host "  -- or -- https://www.python.org/downloads/windows/  (check 'Add python.exe to PATH')"
  exit 1
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "git not found (optional, but you'll want it):  winget install Git.Git" -ForegroundColor Yellow
}

$Repo = if ($env:WY_REPO) { $env:WY_REPO } else { (Resolve-Path "$PSScriptRoot\..\..").Path }
$Bin  = Join-Path $env:USERPROFILE "bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

$launcher = @"
@echo off
set "WY_REPO=%WY_REPO%"
if "%WY_REPO%"=="" set "WY_REPO=$Repo"
$py "$Repo\agent\selfrun.py" %*
"@
Set-Content -Path (Join-Path $Bin "wyagent.cmd") -Value $launcher -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$Bin*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$Bin", "User")
  Write-Host "Added $Bin to your PATH (open a new terminal to pick it up)."
}

# firewall rule so the phone can reach the console (needs admin; skip if it fails)
try {
  if (-not (Get-NetFirewallRule -DisplayName "windycity-agent 8765" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "windycity-agent 8765" -Direction Inbound -LocalPort 8765 `
      -Protocol TCP -Action Allow -Profile Private | Out-Null
    Write-Host "Firewall rule added for port 8765 (private networks)."
  }
} catch { Write-Host "Could not add the firewall rule (not admin?). Allow Python when prompted instead." -ForegroundColor Yellow }

Write-Host ""
Write-Host "Installed.  Open a NEW terminal, then:" -ForegroundColor Green
Write-Host "  wyagent doctor"
Write-Host "  wyagent serve            # then open the LAN URL on your phone"
Write-Host "Optional: start at login ->  Task Scheduler -> Create Task -> wyagent.cmd serve"
