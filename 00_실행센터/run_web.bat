@echo off
setlocal enableextensions
chcp 65001 >nul
title Prism Web [PORT 10000]

rem -- Project root = this bat folder's parent (00_xxx\..)
set "ROOT=%~dp0.."
pushd "%ROOT%" >nul 2>&1
set "ROOT=%CD%"
popd >nul 2>&1

set "PORT=10000"
set "URL=http://127.0.0.1:%PORT%/"

echo [INFO] ROOT = %ROOT%
echo [INFO] URL  = %URL%
echo.

rem -- Find Python: C:\Python312-32 -> py -3 -> python
set "PYEXE="
if exist "C:\Python312-32\python.exe" set "PYEXE=C:\Python312-32\python.exe"
if not defined PYEXE ( where py >nul 2>nul && set "PYEXE=py -3" )
if not defined PYEXE ( where python >nul 2>nul && set "PYEXE=python" )
if not defined PYEXE (
  echo [ERROR] Python not found. Install Python or add it to PATH.
  pause
  exit /b 1
)
echo [INFO] PYEXE = %PYEXE%
echo.

rem -- Clean restart: stop any previous server still holding the port (so new code loads)
echo [INFO] Stopping previous instance on port %PORT% (if any) ...
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  echo [INFO]   killing old PID %%P
  taskkill /F /PID %%P >nul 2>&1
)
rem -- brief pause so the port is fully released before rebind
ping -n 2 127.0.0.1 >nul

rem -- Open browser, then run server via ASCII launcher (Korean path handled in Python)
start "" "%URL%"
cd /d "%ROOT%"
%PYEXE% run_server.py %PORT%

echo.
echo [INFO] Server stopped. Press any key to close.
pause >nul
endlocal