@echo off
REM Compila Dualless.exe y genera el instalador Dualless-Setup-v1.4.0.exe con Inno Setup.
cd /d "%~dp0"

if exist "dist\Dualless\Dualless.exe" goto :find_iscc
echo Primero compilando Dualless.exe...
call "%~dp0compilar_exe.bat" --nopause
if exist "dist\Dualless\Dualless.exe" goto :find_iscc

echo No se pudo generar dist\Dualless\Dualless.exe.
pause
exit /b 1

:find_iscc
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not "%ISCC%"=="" goto :run_iscc

echo No se encontro Inno Setup 6 instalado.
echo Descargalo gratis desde: https://jrsoftware.org/isinfo.php
echo Luego vuelve a ejecutar crear_instalador.bat.
pause
exit /b 1

:run_iscc
echo Generando instalador Dualless-Setup-v1.4.0.exe...
"%ISCC%" "installer\Dualless.iss"
if errorlevel 1 goto :err_iscc

echo.
echo ============================================================
echo   Listo! Instalador en: dist\Dualless-Setup-v1.4.0.exe
echo ============================================================
pause
exit /b 0

:err_iscc
echo Error al generar el instalador.
pause
exit /b 1
