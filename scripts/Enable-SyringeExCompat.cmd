@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "CFG=%ROOT%\Resources\ClientDefinitions.ini"
set "EXE=%ROOT%\AutoReloader.SyringeLauncher.exe"

if not exist "%CFG%" (
    echo [ERROR] Not found: %CFG%
    pause
    exit /b 1
)
if not exist "%EXE%" (
    echo [ERROR] Not found: %EXE%
    pause
    exit /b 1
)

if not exist "%CFG%.autoreloader.bak" (
    copy /y "%CFG%" "%CFG%.autoreloader.bak" >nul
    echo [OK] Backup: %CFG%.autoreloader.bak
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='%CFG%'; $t=Get-Content -LiteralPath $p -Raw; if($t -match '(?m)^GameLauncherExecutableName=Syringe\.exe\r?$'){ $t=$t -replace '(?m)^GameLauncherExecutableName=Syringe\.exe\r?$','GameLauncherExecutableName=AutoReloader.SyringeLauncher.exe'; Set-Content -LiteralPath $p -Value $t -Encoding UTF8; Write-Host '[OK] ClientDefinitions.ini patched' } else { Write-Host '[INFO] Already patched or line not found' }"

echo.
echo Restart the MO client for the change to take effect.
pause
