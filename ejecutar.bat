@echo off
REM Doble clic en este archivo: prepara/repara el entorno automaticamente y abre Dualless v1.4.0.
cd /d "%~dp0"

call "%~dp0_preparar_entorno.bat"
if errorlevel 1 goto :prep_fail

echo Iniciando Dualless v1.4.0...
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto :run_fail
exit /b 0

:prep_fail
echo.
echo No se pudo preparar el entorno de Dualless.
pause
exit /b 1

:run_fail
echo.
echo Dualless se cerro con un error.
pause
exit /b 1
