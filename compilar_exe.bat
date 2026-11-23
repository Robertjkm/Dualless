@echo off
REM Doble clic para compilar Dualless.exe --onedir en Windows x64.
cd /d "%~dp0"

call "%~dp0_preparar_entorno.bat"
if errorlevel 1 goto :err_prep

".venv\Scripts\python.exe" -c "import PyInstaller" >nul 2>nul
if not errorlevel 1 goto :build_now

echo Instalando PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :err_pyi

:build_now
echo Compilando Dualless.exe con icono y assets...
".venv\Scripts\python.exe" -m PyInstaller --name "Dualless" --windowed --onedir --clean --noconfirm --icon "dualcontrol\ui\assets\app_icon.ico" --add-data "dualcontrol\ui\assets;dualcontrol\ui\assets" run.py
if errorlevel 1 goto :err_build

echo.
echo ============================================================
echo   Listo! Tu ejecutable esta en: dist\Dualless\Dualless.exe
echo ============================================================
if /i not "%~1"=="--nopause" pause
exit /b 0

:err_prep
echo Error al preparar el entorno virtual.
if /i not "%~1"=="--nopause" pause
exit /b 1

:err_pyi
echo Error al instalar PyInstaller.
if /i not "%~1"=="--nopause" pause
exit /b 1

:err_build
echo.
echo Error durante la compilacion de Dualless.exe.
if /i not "%~1"=="--nopause" pause
exit /b 1
