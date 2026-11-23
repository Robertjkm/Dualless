@echo off
REM Helper interno de Dualless v1.4.0: verifica y repara .venv, pip y dependencias.
cd /d "%~dp0"

set "PY_CMD="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY_CMD=python"
if not "%PY_CMD%"=="" goto :python_ok

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"
if not "%PY_CMD%"=="" goto :python_ok

echo [ERROR] No se encontro Python 3 instalado en Windows.
echo Instalalo desde https://www.python.org/downloads/
echo IMPORTANTE: marca "Add python.exe to PATH" durante la instalacion.
exit /b 1

:python_ok
if exist ".venv\Scripts\python.exe" goto :check_pip

echo [1/3] Creando entorno virtual de Dualless - no cierres esta ventana...
%PY_CMD% -m venv .venv
if not errorlevel 1 goto :check_pip

echo [AVISO] Reintentando crear .venv limpio...
if exist ".venv" rmdir /s /q ".venv"
%PY_CMD% -m venv --clear .venv
if not errorlevel 1 goto :check_pip

echo [ERROR] No se pudo crear el entorno virtual .venv.
exit /b 1

:check_pip
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if not errorlevel 1 goto :check_deps

echo [AVISO] pip no esta disponible en .venv. Reparando con ensurepip...
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if not errorlevel 1 goto :check_deps

echo [AVISO] .venv estaba incompleto. Recreando entorno virtual desde cero...
rmdir /s /q ".venv"
%PY_CMD% -m venv .venv
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if not errorlevel 1 goto :check_deps

echo [AVISO] Instalando pip mediante bootstrap oficial get-pip.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '.venv\get-pip.py'"
if exist ".venv\get-pip.py" ".venv\Scripts\python.exe" ".venv\get-pip.py"
if exist ".venv\get-pip.py" del /f /q ".venv\get-pip.py" >nul 2>nul

".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if not errorlevel 1 goto :check_deps

echo [ERROR] No se pudo reparar pip en .venv.
echo Reinstala Python desde https://www.python.org/downloads/ marcando "pip" y "Add python.exe to PATH".
exit /b 1

:check_deps
".venv\Scripts\python.exe" -c "import PySide6, vgamepad" >nul 2>nul
if not errorlevel 1 goto :check_audio

echo [2/3] Instalando dependencias principales de Dualless...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not errorlevel 1 goto :check_audio

echo [ERROR] Error al instalar las dependencias principales.
exit /b 1

:check_audio
".venv\Scripts\python.exe" -c "import pyaudiowpatch" >nul 2>nul
if not errorlevel 1 goto :done

echo [3/3] Instalando modulo opcional de audio WASAPI pyaudiowpatch...
".venv\Scripts\python.exe" -m pip install pyaudiowpatch >nul 2>nul

:done
exit /b 0
