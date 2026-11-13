# Runs the RotLab hub with a small test workspace, opens RotLabTV.exe over Notepad, and takes screenshots
# (closed, then with both drawers and the chat open) so the result can be checked without a Windows PC.
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$out = Join-Path $PWD "out"
$ci = Join-Path $PWD "ci"
$root = Join-Path $ci "W"
New-Item -ItemType Directory -Force -Path "$root\_hub", "$ci\ad\VegasHub", "$root\Shared\Sounds" | Out-Null
Copy-Item -Recurse -Force app "$root\_hub\app"
'{"name":"Abdullah","phone_uploads":false,"github_updates":false,"live":false}' | Set-Content "$ci\ad\VegasHub\config.json"
Copy-Item app\hub.ico "$root\Shared\logo.ico"
[IO.File]::WriteAllBytes("$root\Shared\Sounds\whoosh_03.wav", [byte[]](0..2000 | % { 0 }))
$env:APPDATA = "$ci\ad"; $env:HUB_NO_BROWSER = "1"; $env:HUB_ROOT = $root
$hub = Start-Process python -ArgumentList "`"$root\_hub\app\hub.py`" --background" -PassThru -RedirectStandardOutput "$out\hub.out.txt" -RedirectStandardError "$out\hub.err.txt"
$up = $false
for ($i = 0; $i -lt 40; $i++) { Start-Sleep 1; try { Invoke-RestMethod http://localhost:8765/api/state | Out-Null; $up = $true; break } catch {} }
"hub up: $up" | Out-File "$out\test.txt"
function post($p, $b) { try { Invoke-RestMethod -Method Post -ContentType "application/json" -Uri "http://localhost:8765$p" -Body ($b | ConvertTo-Json) } catch { "post $p failed: $_" | Out-File -Append "$out\test.txt" } }
post "/api/ws/project_new" @{ name = "Park video"; type = "video" } | Out-Null
post "/api/chat" @{ text = "testing the TV window" } | Out-Null
function shot($name) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save("$out\$name.png", [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
}
# something behind the TV, to see that the gaps really are see-through
$np = Start-Process notepad -PassThru -WindowStyle Maximized
Start-Sleep 2
shot "0-before"
$tv = Start-Process "$out\RotLabTV.exe" -ArgumentList "--port 8765 --query &test=1" -PassThru
Start-Sleep 5
shot "1-closed"
Start-Sleep 7
shot "2-open"
# click-through check: click far from the TV; Notepad should get it (we type into it afterwards)
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point 40, 300
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class M { [DllImport("user32.dll")] public static extern void mouse_event(int f, int x, int y, int d, int e); }
"@
[M]::mouse_event(2, 0, 0, 0, 0); [M]::mouse_event(4, 0, 0, 0, 0)
Start-Sleep 1
[System.Windows.Forms.SendKeys]::SendWait("clickthrough-ok")
Start-Sleep 1
shot "3-clickthrough"
"tv running: $(-not $tv.HasExited)" | Out-File -Append "$out\test.txt"
Get-Process | ? { $_.ProcessName -like "rotlab*" -or $_.ProcessName -like "msedgewebview2*" } | Select-Object ProcessName, Id, MainWindowTitle | Out-String | Out-File -Append "$out\test.txt"
Copy-Item "$ci\ad\VegasHub\hub.log" "$out\hub.log" -ErrorAction SilentlyContinue
Stop-Process -Id $tv.Id -ErrorAction SilentlyContinue
Stop-Process -Id $hub.Id -ErrorAction SilentlyContinue
Stop-Process -Id $np.Id -ErrorAction SilentlyContinue
exit 0
