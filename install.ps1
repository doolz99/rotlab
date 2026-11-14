# RotLab one-line installer
#   Paste this into PowerShell:
#     irm https://raw.githubusercontent.com/doolz99/rotlab/main/install.ps1 | iex
#
# It downloads a tested RotLab version (the tag below) into this PC's own app folder
# (%LOCALAPPDATA%\RotLab\app, outside the synced project folder, so nobody you sync with can change the
# program), then runs the setup, which checks for Python and installs everything else.
# The project folder is C:\VegasProject, or the folder in $env:ROTLAB_DIR.
# Files downloaded this way are not marked "from the internet", so Windows won't block them.

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$version = '44657240edadcc706baa1789c4dabd474f934ab9'  # RotLab 4.5 (a fixed, tested commit)
$project = if ($env:ROTLAB_DIR) { $env:ROTLAB_DIR } else { 'C:\VegasProject' }
$app     = Join-Path $env:LOCALAPPDATA 'RotLab\app'
$env:ROTLAB_ROOT = $project

Write-Host ''
Write-Host '  RotLab installer' -ForegroundColor Cyan
Write-Host "  Project folder: $project"
Write-Host ''

New-Item -ItemType Directory -Force -Path $app | Out-Null

$zip = Join-Path $env:TEMP 'rotlab-main.zip'
$tmp = Join-Path $env:TEMP ('rotlab-' + [guid]::NewGuid().ToString('N'))

Write-Host '  Downloading RotLab...'
Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/doolz99/rotlab/archive/$version.zip" -OutFile $zip

Write-Host '  Unpacking...'
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$src = Get-ChildItem -Directory $tmp | Select-Object -First 1
Copy-Item -Path (Join-Path $src.FullName 'app\*') -Destination $app -Recurse -Force
Remove-Item -Recurse -Force $zip, $tmp -ErrorAction SilentlyContinue

Write-Host "  Installed to $app" -ForegroundColor Green
Write-Host '  Starting setup...'
Write-Host ''
Start-Process -FilePath (Join-Path $app 'Install RotLab.cmd') -WorkingDirectory $app
