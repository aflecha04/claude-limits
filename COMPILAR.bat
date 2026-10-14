@echo off
setlocal
title Compilar Claude Limits
cd /d "%~dp0"

set "NAME=Claude Limits"
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=python"

set "WORK=%TEMP%\CGBuild"
set "OUT=%~dp0PARA COMPARTIR"
set "LOCAL=%LOCALAPPDATA%\Claude Limits"
set "LOG=%TEMP%\claudelimits_build.log"

echo ==================================================
echo    Compilar Claude Limits
echo ==================================================
echo.

echo  [1/5] Cerrando el widget...
taskkill /IM "%NAME%.exe" /F >nul 2>&1
taskkill /IM "ClaudeGlass by Flecha.exe" /F >nul 2>&1

echo  [2/5] Preparando carpeta temporal fuera de OneDrive...
rmdir /S /Q "%WORK%" >nul 2>&1
mkdir "%WORK%" 2>nul
copy /Y "%~dp0claude_limits.pyw" "%WORK%\claude_limits.pyw" >nul
xcopy /E /I /Y /Q "%~dp0claudelimits" "%WORK%\claudelimits" >nul

echo  [3/5] Dependencias y compilacion (1-2 minutos)...
"%PY%" -m pip install --upgrade pillow pyinstaller > "%LOG%" 2>&1
pushd "%WORK%"
"%PY%" -m PyInstaller --onefile --noconsole --name "%NAME%" ^
    --workpath "%WORK%\build" --distpath "%WORK%\dist" --specpath "%WORK%" ^
    claude_limits.pyw >> "%LOG%" 2>&1
popd
if not exist "%WORK%\dist\%NAME%.exe" goto :fallo

echo  [4/5] Publicando en PARA COMPARTIR...
if not exist "%OUT%" mkdir "%OUT%"
copy /Y "%WORK%\dist\%NAME%.exe" "%OUT%\%NAME%.exe" >nul
if errorlevel 1 goto :fallo
rem  copia con la extension cambiada, para los equipos cuyo filtro
rem  de seguridad bloquea la descarga de archivos .exe
copy /Y "%OUT%\%NAME%.exe" "%OUT%\%NAME%.ex_" >nul

echo  [5/5] Instalando en tu equipo y abriendo...
rem  Se instala y se abre desde %LOCALAPPDATA%, NUNCA desde PARA COMPARTIR:
rem  al ejecutarse, el widget crea un config.json con la sessionKey junto
rem  al .exe, y esa carpeta es la que se comparte.
if not exist "%LOCAL%" mkdir "%LOCAL%"
copy /Y "%OUT%\%NAME%.exe" "%LOCAL%\%NAME%.exe" >nul
start "" "%LOCAL%\%NAME%.exe"

echo.
echo    LISTO
echo      %OUT%\%NAME%.exe      (esto es lo que compartes)
echo      %LOCAL%\%NAME%.exe    (el que se acaba de abrir)
echo.
pause
exit /b 0

:fallo
echo.
echo    FALLO al compilar. Detalle en:
echo    %LOG%
echo.
pause
exit /b 1
