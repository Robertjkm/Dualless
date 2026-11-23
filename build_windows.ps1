# build_windows.ps1
# Genera Dualless.exe (Windows x64, autocontenido) usando PyInstaller.
# Incluye automáticamente el icono oficial (app_icon.ico) y todos los assets PNG.
#
# El ejecutable final queda en: dist\Dualless\Dualless.exe

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "No se encontró .venv. Ejecuta primero ejecutar.bat."
    exit 1
}

& .\.venv\Scripts\python.exe -m PyInstaller `
    --name "Dualless" `
    --windowed `
    --onedir `
    --clean `
    --noconfirm `
    --icon "dualcontrol\ui\assets\app_icon.ico" `
    --add-data "dualcontrol\ui\assets;dualcontrol\ui\assets" `
    run.py

Write-Host ""
Write-Host "Listo. Ejecutable en: dist\Dualless\Dualless.exe"
Write-Host "Los perfiles se guardan junto al .exe, en una carpeta 'profiles'."
