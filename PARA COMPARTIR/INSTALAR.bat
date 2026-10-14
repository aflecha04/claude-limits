@echo off
setlocal enabledelayedexpansion
title Instalar ClaudeGlass by Flecha
cd /d "%~dp0"

set "NAME=ClaudeGlass by Flecha"
set "DEST=%LOCALAPPDATA%\ClaudeGlass"
set "EXE=%DEST%\%NAME%.exe"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"

echo ==================================================
echo    ClaudeGlass by Flecha  -  instalar o actualizar
echo ==================================================
echo.

if not exist "%~dp0%NAME%.exe" (
    echo  ERROR: no encuentro "%NAME%.exe" junto a este archivo.
    echo.
    echo  Si has descargado el archivo terminado en .ex_ renombralo
    echo  quitandole el guion bajo del final. Y si vienes de un ZIP,
    echo  descomprimelo ENTERO en una carpeta antes de ejecutar esto.
    echo.
    pause
    exit /b 1
)

echo  [1/6] Cerrando cualquier version abierta...
taskkill /IM "%NAME%.exe" /F >nul 2>&1
taskkill /IM "ClaudeGlass.exe" /F >nul 2>&1
taskkill /IM "ClaudeGlass_ANTIGUO.exe" /F >nul 2>&1
ping -n 3 127.0.0.1 >nul

echo  [2/6] Copiando la version nueva...
if not exist "%DEST%" mkdir "%DEST%" >nul 2>&1
copy /Y "%~dp0%NAME%.exe" "%EXE%" >nul
if errorlevel 1 (
    echo.
    echo  ERROR: no se ha podido copiar en %DEST%
    echo  Cierra el widget a mano y vuelve a intentarlo.
    echo.
    pause
    exit /b 1
)
echo        instalado en: %EXE%

echo  [3/6] Quitando accesos directos de arranque antiguos...
set "QUITADOS=0"
for %%F in ("%STARTUP%\ClaudeGlass*.lnk" "%STARTUP%\Claude Usage*.lnk") do (
    if exist "%%~F" (
        del /Q "%%~F" >nul 2>&1
        if not exist "%%~F" set /a QUITADOS+=1
    )
)
echo        accesos directos viejos quitados: !QUITADOS!

echo  [4/6] Configurando el arranque con Windows...
rem  Se usa el registro y NO un acceso directo por PowerShell: en equipos
rem  con AppLocker o Constrained Language Mode la llamada COM esta
rem  bloqueada y fallaba en silencio (de ahi el "no se inicia solo").
reg add "%RUNKEY%" /v "ClaudeGlass by Flecha" /t REG_SZ /d "\"%EXE%\"" /f >nul 2>&1
rem  Windows guarda APARTE si esa entrada esta desactivada (Administrador
rem  de tareas > Inicio). Si quedo desactivada por una version anterior, la
rem  clave de arriba no sirve de nada: hay que borrar ese veto.
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run" /v "ClaudeGlass by Flecha" /f >nul 2>&1

set "ARRANQUE=NO"
reg query "%RUNKEY%" /v "ClaudeGlass by Flecha" >nul 2>&1
if not errorlevel 1 set "ARRANQUE=SI"

if "!ARRANQUE!"=="SI" (
    echo        OK: arrancara solo al iniciar sesion
) else (
    echo        AVISO: tu equipo no deja escribir esa clave de registro.
    echo        El widget funciona igual, pero no arrancara solo.
    echo        Puedes activarlo desde el propio widget:
    echo           clic derecho ^> Iniciar con Windows
)

echo  [5/6] Limpiando restos de la version anterior...
if exist "%DEST%\ClaudeGlass.exe" del /Q "%DEST%\ClaudeGlass.exe" >nul 2>&1
if exist "%DEST%\ClaudeGlass_ANTIGUO.exe" del /Q "%DEST%\ClaudeGlass_ANTIGUO.exe" >nul 2>&1

echo  [6/6] Abriendo el widget...
start "" "%EXE%"
ping -n 3 127.0.0.1 >nul

echo.
echo ==================================================
echo    LISTO
echo ==================================================
echo.
echo    - Instalado en:  %EXE%
echo    - Arranque con Windows: !ARRANQUE!
echo    - Tu sessionKey se conserva: NO hay que volver
echo      a configurarla.
echo    - Clic derecho sobre el widget = menu completo.
echo.
echo    Esta version ya NO puede abrirse por duplicado,
echo    asi que se acabo el parpadeo entre tema claro y
echo    oscuro.
echo.
pause
