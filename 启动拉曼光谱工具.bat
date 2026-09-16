@echo off
title Raman Spectrum Toolkit
chcp 65001 >nul
cd /d "%~dp0"
where pyw >nul 2>nul
if "%errorlevel%"=="0" (
    start "" pyw "%~dp0jws2csv.py" %*
    exit /b
)
where pythonw >nul 2>nul
if "%errorlevel%"=="0" (
    start "" pythonw "%~dp0jws2csv.py" %*
    exit /b
)
py "%~dp0jws2csv.py" %*
if errorlevel 1 pause
