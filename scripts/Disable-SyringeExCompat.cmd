@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "CFG=%ROOT%\Resources\ClientDefinitions.ini"
set "BAK=%CFG%.autoreloader.bak"

if not exist "%CFG%" (
    echo [ERROR] Not found: %CFG%
    pause
    exit /b 1
)

if exist "%BAK%" (
    copy /y "%BAK%" "%CFG%" >nul
    echo [OK] Restored from backup.
    pause
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='%CFG%'; $t=Get-Content -LiteralPath $p -Raw; if($t -match '(?m)^GameLauncherExecutableName=AutoReloader\.SyringeLauncher\.exe\r?$'){ $t=$t -replace '(?m)^GameLauncherExecutableName=AutoReloader\.SyringeLauncher\.exe\r?$','GameLauncherExecutableName=Syringe.exe'; Set-Content -LiteralPath $p -Value $t -Encoding UTF8; Write-Host '[OK] Restored Syringe.exe' } else { Write-Host '[INFO] Nothing to restore' }"

echo.
echo Restart the MO client for the change to take effect.
pause
