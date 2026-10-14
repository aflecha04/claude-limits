@echo off
setlocal
title Compilar ClaudeGlass PRUEBA
cd /d "%~dp0"

rem  Compila la version de este codigo como COPIA DE PRUEBA:
rem  se instala en %LOCALAPPDATA%\ClaudeGlass PRUEBA y se abre junto a la
rem  normal, sin tocarla. No copia nada a PARA COMPARTIR.

set "NAME=ClaudeGlass PRUEBA"
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=python"

set "WORK=%TEMP%\CGBuildPrueba"
set "LOCAL=%LOCALAPPDATA%\ClaudeGlass PRUEBA"
set "LOG=%TEMP%\claudeglass_prueba_build.log"

echo ==================================================
echo    Compilar ClaudeGlass PRUEBA
echo ==================================================
echo.

echo  [1/4] Cerrando la copia de prueba (la normal sigue abierta)...
taskkill /IM "%NAME%.exe" /F >nul 2>&1

echo  [2/4] Preparando carpeta temporal fuera de OneDrive...
rmdir /S /Q "%WORK%" >nul 2>&1
mkdir "%WORK%" 2>nul
copy /Y "%~dp0claude_glass.pyw" "%WORK%\claude_glass.pyw" >nul
xcopy /E /I /Y /Q "%~dp0claudeglass" "%WORK%\claudeglass" >nul

echo  [3/4] Compilando (1-2 minutos)...
"%PY%" -m pip install --upgrade pillow pyinstaller > "%LOG%" 2>&1
pushd "%WORK%"
"%PY%" -m PyInstaller --onefile --noconsole --name "%NAME%" ^
    --workpath "%WORK%\build" --distpath "%WORK%\dist" --specpath "%WORK%" ^
    claude_glass.pyw >> "%LOG%" 2>&1
popd
if not exist "%WORK%\dist\%NAME%.exe" goto :fallo

echo  [4/4] Instalando la copia de prueba y abriendola...
if not exist "%LOCAL%" mkdir "%LOCAL%"
copy /Y "%WORK%\dist\%NAME%.exe" "%LOCAL%\%NAME%.exe" >nul
start "" "%LOCAL%\%NAME%.exe"

echo.
echo    LISTO: %LOCAL%\%NAME%.exe
echo    Para quitarla: BORRAR PRUEBA.bat
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
