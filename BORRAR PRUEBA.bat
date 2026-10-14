@echo off
setlocal
title Borrar Claude Limits PRUEBA
cd /d "%~dp0"

rem  Quita la copia de prueba y todo lo suyo. La version normal no se toca.

echo ==================================================
echo    Borrar Claude Limits PRUEBA
echo ==================================================
echo.
echo  Se cierra y se borra la copia de prueba, con sus ajustes y su
echo  sessionKey. Tu widget de siempre sigue igual.
echo.
pause

taskkill /IM "Claude Limits PRUEBA.exe" /F >nul 2>&1
taskkill /IM "ClaudeGlass PRUEBA.exe" /F >nul 2>&1
ping -n 2 127.0.0.1 >nul
rmdir /S /Q "%LOCALAPPDATA%\ClaudeGlass PRUEBA" >nul 2>&1
rmdir /S /Q "%APPDATA%\ClaudeGlass PRUEBA" >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "ClaudeGlass PRUEBA" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Claude Limits PRUEBA" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run" /v "ClaudeGlass PRUEBA" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run" /v "Claude Limits PRUEBA" /f >nul 2>&1
for /f "tokens=1,* delims=: " %%A in ('cmdkey /list ^| findstr /C:"ClaudeGlass PRUEBA/sessionKey"') do cmdkey /delete:"%%B" >nul 2>&1
cmdkey /delete:"ClaudeGlass PRUEBA/sessionKey" >nul 2>&1

echo.
echo    LISTO: copia de prueba borrada.
echo.
pause
