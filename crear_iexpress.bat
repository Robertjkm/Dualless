@echo off
REM Empaqueta Dualless.exe v1.4.0 con IExpress nativo de Windows.
cd /d "%~dp0"

if exist "dist\Dualless.exe" goto :make_sed
echo Compilando primero el ejecutable unico dist\Dualless.exe...
call "%~dp0compilar_onefile.bat" --nopause
if exist "dist\Dualless.exe" goto :make_sed

echo No se pudo generar dist\Dualless.exe.
pause
exit /b 1

:make_sed
set "SED_FILE=%CD%\installer\dualless_iexpress.sed"
set "OUT_EXE=%CD%\dist\Dualless-IExpress-v1.4.0.exe"
set "SRC_DIR=%CD%\dist\"

echo Generando directiva IExpress...
> "%SED_FILE%" echo [Version]
>> "%SED_FILE%" echo Class=IEXPRESS
>> "%SED_FILE%" echo SEDVersion=3
>> "%SED_FILE%" echo [Options]
>> "%SED_FILE%" echo PackagePurpose=InstallApp
>> "%SED_FILE%" echo ShowInstallProgramWindow=0
>> "%SED_FILE%" echo HideExtractAnimation=1
>> "%SED_FILE%" echo UseLongFileName=1
>> "%SED_FILE%" echo InsideCompressed=0
>> "%SED_FILE%" echo CAB_FixedSize=0
>> "%SED_FILE%" echo CAB_ResvCodeSigning=0
>> "%SED_FILE%" echo RebootMode=N
>> "%SED_FILE%" echo InstallPrompt=Deseas iniciar Dualless v1.4.0?
>> "%SED_FILE%" echo DisplayLicense=
>> "%SED_FILE%" echo FinishMessage=
>> "%SED_FILE%" echo TargetName=%OUT_EXE%
>> "%SED_FILE%" echo FriendlyName=Dualless v1.4.0
>> "%SED_FILE%" echo AppLaunched=Dualless.exe
>> "%SED_FILE%" echo PostInstallCmd=^<None^>
>> "%SED_FILE%" echo AdminQuietInstCmd=
>> "%SED_FILE%" echo UserQuietInstCmd=
>> "%SED_FILE%" echo SourceFiles=SourceFiles
>> "%SED_FILE%" echo [Strings]
>> "%SED_FILE%" echo FILE0="Dualless.exe"
>> "%SED_FILE%" echo [SourceFiles]
>> "%SED_FILE%" echo SourceFiles0=%SRC_DIR%
>> "%SED_FILE%" echo [SourceFiles0]
>> "%SED_FILE%" echo %%FILE0%%=

echo Ejecutando IExpress de Windows...
iexpress.exe /N "%SED_FILE%"
if errorlevel 1 goto :err_iexp

echo.
echo ============================================================
echo   Listo! Paquete IExpress en: dist\Dualless-IExpress-v1.4.0.exe
echo ============================================================
pause
exit /b 0

:err_iexp
echo Error al generar el paquete con IExpress.
pause
exit /b 1
