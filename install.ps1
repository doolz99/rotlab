# RotLab one-line installer
#   Paste this into PowerShell:
#     irm https://raw.githubusercontent.com/doolz99/rotlab/main/install.ps1 | iex
#
# It downloads RotLab into C:\VegasProject\_hub\app (or the folder in $env:ROTLAB_DIR),
# then runs the setup, which checks for Python and installs everything else.
# Files downloaded this way are not marked "from the internet", so Windows won't block them.

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$project = if ($env:ROTLAB_DIR) { $env:ROTLAB_DIR } else { 'C:\VegasProject' }
$app     = Join-Path $project '_hub\app'

Write-Host ''
Write-Host '  RotLab installer' -ForegroundColor Cyan
Write-Host "  Project folder: $project"
Write-Host ''

New-Item -ItemType Directory -Force -Path $app | Out-Null

$zip = Join-Path $env:TEMP 'rotlab-main.zip'
$tmp = Join-Path $env:TEMP ('rotlab-' + [guid]::NewGuid().ToString('N'))

Write-Host '  Downloading RotLab...'
Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/doolz99/rotlab/archive/refs/heads/main.zip' -OutFile $zip

Write-Host '  Unpacking...'
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Copy-Item -Path (Join-Path $tmp 'rotlab-main\app\*') -Destination $app -Recurse -Force
Remove-Item -Recurse -Force $zip, $tmp -ErrorAction SilentlyContinue

Write-Host "  Installed to $app" -ForegroundColor Green
Write-Host '  Starting setup...'
Write-Host ''
Start-Process -FilePath (Join-Path $app 'Install RotLab.cmd') -WorkingDirectory $app
