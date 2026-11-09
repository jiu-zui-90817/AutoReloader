# 本地 / CI 试验：Nuitka standalone，目录结构对齐当前 PyInstaller 产物
#   dist-nuitka/editor/   INI工程编辑器.exe + 依赖 + editor.ico + qt.conf
#   dist-nuitka/workshop/ 战术工坊.exe + 依赖 + workshop.ico + qt.conf
#
# 用法（仓库根目录，Windows + Python 3.12）:
#   powershell -ExecutionPolicy Bypass -File scripts/build_nuitka_test.ps1
#   powershell -File scripts/build_nuitka_test.ps1 -Target workshop
#   powershell -File scripts/build_nuitka_test.ps1 -Target editor
#
# 说明：编辑器历史上在 MainWindow 初始化时 segfault；本脚本用于复测。

param(
    [ValidateSet("both", "editor", "workshop")]
    [string]$Target = "both"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "Frontend"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root
Write-Host "ROOT=$Root"

function Ensure-Pip([string[]]$pkgs) {
    python -m pip install --upgrade pip | Out-Null
    python -m pip install @pkgs
}

function Write-QtConf([string]$OutDir) {
    $qwin = Get-ChildItem $OutDir -Recurse -Filter "qwindows.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $qwin) {
        Write-Warning "no qwindows.dll under $OutDir"
        return
    }
    $outFull = (Resolve-Path $OutDir).Path
    $pluginsParent = $qwin.Directory.Parent.FullName
    $prefix = "."
    $pluginsRel = "PySide6/plugins"
    $norm = $pluginsParent.Replace([char]0x5C, "/")
    $outNorm = $outFull.Replace([char]0x5C, "/")
    $marker = "/_internal/"
    $mi = $norm.ToLower().IndexOf($marker)
    if ($mi -ge 0) {
        $prefix = "_internal"
        $after = $norm.Substring($mi + $marker.Length).TrimStart([char]0x2F)
        if ($after.Length -gt 0) { $pluginsRel = $after }
    } else {
        $rel = $norm
        if ($rel.StartsWith($outNorm)) { $rel = $rel.Substring($outNorm.Length) }
        $rel = $rel.TrimStart([char]0x2F)
        if ($rel.Length -gt 0) { $pluginsRel = $rel }
    }
    if (Test-Path (Join-Path $OutDir "PySide6")) {
        $prefix = "."
        if (Test-Path (Join-Path $OutDir "PySide6/plugins")) {
            $pluginsRel = "PySide6/plugins"
        } elseif (Test-Path (Join-Path $OutDir "PySide6/qt-plugins")) {
            $pluginsRel = "PySide6/qt-plugins"
        }
    }
    Write-Host "qt.conf Prefix=$prefix Plugins=$pluginsRel"
    Set-Content -Encoding ASCII -Path (Join-Path $OutDir "qt.conf") -Value "[Paths]`nPrefix = $prefix`nPlugins = $pluginsRel`n"
}

function Slim-QtJunk([string]$OutDir) {
    $keep = @("platforms", "styles", "imageformats", "iconengines")
    Get-ChildItem $OutDir -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(translations|qml|QtWebEngine|resources)$' } |
        ForEach-Object { Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue }
    Get-ChildItem $OutDir -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @("plugins", "qt-plugins") } |
        ForEach-Object {
            Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                if ($keep -notcontains $_.Name) {
                    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
                }
            }
        }
    foreach ($pat in @("*WebEngine*", "*Qt6Quick*", "*Qt6Qml*", "*Qt6Multimedia*", "*Qt6Pdf*", "opengl32sw.dll")) {
        Get-ChildItem $OutDir -Recurse -File -Filter $pat -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -Force $_.FullName -ErrorAction SilentlyContinue }
    }
}

function Build-EditorNuitka {
    Write-Host "===== Nuitka EDITOR ====="
    Ensure-Pip @("nuitka", "ordered-set", "zstandard", "-r", "Frontend/editor/requirements.txt")
    New-Item -ItemType Directory -Force -Path Frontend/editor/schemas | Out-Null
    Copy-Item -Force shared/schemas/common_flags.json Frontend/editor/schemas/common_flags.json

    $out = Join-Path $Root "dist-nuitka/editor"
    Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $out | Out-Null

    $icon = ""
    if (Test-Path "assets/editor.ico") { $icon = "--windows-icon-from-ico=assets/editor.ico" }

    Push-Location Frontend/editor
    $args = @(
        "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        "--windows-console-mode=disable",
        "--output-dir=../../dist-nuitka/editor-build",
        "--output-filename=INIEditor.exe",
        "--include-data-files=config.json=config.json",
        "--include-data-dir=schemas=schemas",
        "--nofollow-import-to=matplotlib,numpy,pandas,scipy,tkinter",
        "--nofollow-import-to=PySide6.QtWebEngine,PySide6.QtWebEngineCore,PySide6.QtQml,PySide6.QtQuick",
        "--nofollow-import-to=PySide6.QtMultimedia,PySide6.QtCharts,PySide6.QtPdf,PySide6.Qt3DCore"
    )
    if ($icon) { $args += $icon }
    $args += "main.py"
    Write-Host "nuitka $($args -join ' ')"
    python @args
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Nuitka editor failed" }
    Pop-Location

    $built = Get-ChildItem "dist-nuitka/editor-build" -Directory | Where-Object { $_.Name -like "*.dist" } | Select-Object -First 1
    if (-not $built) { throw "editor .dist not found" }
    Copy-Item -Path (Join-Path $built.FullName "*") -Destination $out -Recurse -Force
    Copy-Item -Force Frontend/editor/config.json "$out/config.json" -ErrorAction SilentlyContinue
    if (Test-Path "assets/editor.ico") { Copy-Item -Force "assets/editor.ico" "$out/editor.ico" }
    New-Item -ItemType Directory -Force -Path "$out/schemas" | Out-Null
    Copy-Item -Force shared/schemas/common_flags.json "$out/schemas/common_flags.json"
    Slim-QtJunk $out
    Write-QtConf $out
    if (Test-Path "$out/INIEditor.exe") {
        Move-Item -Force "$out/INIEditor.exe" (Join-Path $out "INI工程编辑器.exe")
    }
    $mb = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Host "Editor Nuitka size: $mb MB -> $out"
}

function Build-WorkshopNuitka {
    Write-Host "===== Nuitka WORKSHOP ====="
    Ensure-Pip @("nuitka", "ordered-set", "zstandard", "-r", "Frontend/workshop/requirements.txt")
    New-Item -ItemType Directory -Force -Path Frontend/workshop/schemas | Out-Null
    Copy-Item -Force shared/schemas/common_flags.json Frontend/workshop/schemas/common_flags.json
    if (Test-Path "scripts/patch_workshop_icon.py") {
        python scripts/patch_workshop_icon.py
    }

    $out = Join-Path $Root "dist-nuitka/workshop"
    Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $out | Out-Null

    $icon = ""
    if (Test-Path "assets/workshop.ico") { $icon = "--windows-icon-from-ico=assets/workshop.ico" }

    $env:PYTHONPATH = $Root
    Push-Location Frontend/workshop
    $args = @(
        "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        "--windows-console-mode=disable",
        "--output-dir=../../dist-nuitka/workshop-build",
        "--output-filename=Workshop.exe",
        "--include-package=shared",
        "--include-package=fields",
        "--include-package=app",
        "--include-data-dir=schemas=schemas",
        "--include-data-files=../../shared/profiles.json=profiles.json",
        "--nofollow-import-to=matplotlib,numpy,tkinter",
        "--nofollow-import-to=PySide6.QtWebEngineCore,PySide6.QtQml,PySide6.QtQuick,PySide6.QtMultimedia,PySide6.QtCharts,PySide6.QtPdf"
    )
    if ($icon) { $args += $icon }
    $args += "main.py"
    Write-Host "nuitka $($args -join ' ')"
    python @args
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Nuitka workshop failed" }
    Pop-Location

    $built = Get-ChildItem "dist-nuitka/workshop-build" -Directory | Where-Object { $_.Name -like "*.dist" } | Select-Object -First 1
    if (-not $built) { throw "workshop .dist not found" }
    Copy-Item -Path (Join-Path $built.FullName "*") -Destination $out -Recurse -Force
    Copy-Item -Force shared/profiles.json "$out/profiles.json" -ErrorAction SilentlyContinue
    if (Test-Path "assets/workshop.ico") { Copy-Item -Force "assets/workshop.ico" "$out/workshop.ico" }
    New-Item -ItemType Directory -Force -Path "$out/schemas" | Out-Null
    Copy-Item -Force shared/schemas/common_flags.json "$out/schemas/common_flags.json"
    Slim-QtJunk $out
    Write-QtConf $out
    if (Test-Path "$out/Workshop.exe") {
        Move-Item -Force "$out/Workshop.exe" (Join-Path $out "战术工坊.exe")
    }
    $mb = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Host "Workshop Nuitka size: $mb MB -> $out"
}

if ($Target -eq "both" -or $Target -eq "editor") { Build-EditorNuitka }
if ($Target -eq "both" -or $Target -eq "workshop") { Build-WorkshopNuitka }

Write-Host "Done. Output under dist-nuitka/"
