@echo off
setlocal EnableExtensions
title RotLab setup
cd /d "%~dp0"

echo.
echo  ==========================================
echo   RotLab - setup
echo  ==========================================
echo.
echo  Checking for Python...

call :findpython
if defined PYW goto run

echo.
echo  Python is not installed on this PC (or it is too old).
echo  RotLab needs Python 3.8 or newer. It is free and takes about a minute.
echo.
echo    [1] Install Python for me now (recommended)
echo    [2] Open the Python download page so I can install it myself
echo    [3] Cancel
echo.
choice /c 123 /n /m "  Press 1, 2 or 3: "
if errorlevel 3 goto end
if errorlevel 2 goto manual

:auto
where winget >NUL 2>NUL
if errorlevel 1 (
  echo.
  echo  This PC can't install it automatically, so let's do it by hand.
  goto manual
)
echo.
echo  Installing Python... (a window may ask for permission - click Yes)
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpython
if defined PYW goto run
echo.
echo  Python was installed, but Windows needs a fresh start of this setup to find it.
echo  Close this window and double-click "Install RotLab.cmd" again.
goto end

:manual
echo.
echo  Opening python.org...
echo.
echo  IMPORTANT: on the first screen of the Python installer, tick the box
echo             "Add python.exe to PATH" at the bottom, then click "Install Now".
echo.
echo  When it's finished, double-click "Install RotLab.cmd" again.
start "" "https://www.python.org/downloads/"
goto end

:run
echo  Found Python. Opening the installer...
start "" "%PYW%" "%~dp0Install RotLab.pyw"
exit /b 0

:end
echo.
pause
exit /b 0

rem ---- sets PYW to a working pythonw.exe (3.8+), or leaves it empty ----
:findpython
set "PYW="
for %%P in (py.exe) do if not "%%~$PATH:P"=="" (
  for /f "delims=" %%E in ('py -3 -c "import sys;assert sys.version_info[:2]>=(3,8);print(sys.exec_prefix)" 2^>NUL') do set "PYW=%%E\pythonw.exe"
)
if defined PYW if exist "%PYW%" exit /b 0
set "PYW="
for /f "delims=" %%E in ('python -c "import sys;assert sys.version_info[:2]>=(3,8);print(sys.exec_prefix)" 2^>NUL') do set "PYW=%%E\pythonw.exe"
if defined PYW if exist "%PYW%" exit /b 0
set "PYW="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\pythonw.exe" set "PYW=%%D\pythonw.exe"
if defined PYW exit /b 0
for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\pythonw.exe" set "PYW=%%D\pythonw.exe"
exit /b 0
