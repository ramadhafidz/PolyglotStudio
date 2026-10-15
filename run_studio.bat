@echo off
title Switch Mod Studio
cd /d "%~dp0"
echo Membuka Switch Mod Studio...
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Aplikasi ditutup dengan error (%ERRORLEVEL%).
    pause
)
