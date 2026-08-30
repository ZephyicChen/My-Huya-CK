@echo off
rem ===========================================================================
rem  Entry point: prepare .venv and Chromium, then run python -m huya_ck
rem
rem  Lookup order for Python:
rem    1. existing .venv       -> use it to run ensure_env.py (idempotent)
rem    2. host Python 3.10+    -> use it to create .venv via ensure_env.py
rem    3. no Python found      -> silent winget install of Python 3.12, then 2
rem ===========================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem ---- config ---------------------------------------------------------------
set "PYTHONUTF8=1"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "PY_MIN_CHECK=import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
if not defined PLAYWRIGHT_DOWNLOAD_HOST set "PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright"

rem ---- main flow ------------------------------------------------------------
call :ensure_env
if errorlevel 1 (
    echo Environment setup failed. Install Python 3.10 or newer and add it to PATH.
    pause
    exit /b 1
)

"%VENV_PY%" -m huya_ck
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" pause
exit /b %APP_EXIT%

rem ===========================================================================
rem  Subroutines
rem ===========================================================================

rem Ensure the .venv environment exists and works; return 1 on failure
:ensure_env
if exist "%VENV_PY%" (
    "%VENV_PY%" "%~dp0ensure_env.py"
    exit /b %errorlevel%
)
call :find_host_python
if errorlevel 1 exit /b 1
"%HOST_PY%" "%~dp0ensure_env.py"
if errorlevel 1 exit /b 1
if not exist "%VENV_PY%" exit /b 1
exit /b 0

rem Set HOST_PY to a working Python 3.10+; return 1 on failure
rem Order: py -3 -> python -> winget auto-install
:find_host_python
set "HOST_PY="
call :try_host_python "py -3" && exit /b 0
call :try_host_python "python" && exit /b 0
call :install_python
exit /b %errorlevel%

rem %1 = python command; set HOST_PY and return 0 if version >= 3.10, else 1
:try_host_python
%~1 -c "%PY_MIN_CHECK%" 2>nul
if errorlevel 1 exit /b 1
set "HOST_PY=%~1"
exit /b 0

rem No Python: silent user-scope winget install (no admin needed), then locate
rem python.exe directly (winget's PATH change does not reach this session);
rem return 1 on failure
:install_python
where winget >nul 2>nul
if errorlevel 1 (
    echo [env] Python 3.10+ not found and winget is unavailable.
    exit /b 1
)
echo [env] Python not found. Installing Python 3.12 via winget ^(this runs once^)...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
set "HOST_PY="
for /f "delims=" %%i in ('dir /b /o-n "%LOCALAPPDATA%\Programs\Python\Python3*\python.exe" 2^>nul') do (
    if not defined HOST_PY set "HOST_PY=%%i"
)
if not defined HOST_PY (
    echo [env] winget install finished but python.exe was not found.
    echo [env] Install Python 3.10+ manually, reopen this window, and retry.
    exit /b 1
)
"%HOST_PY%" -c "%PY_MIN_CHECK%" 2>nul
if errorlevel 1 (
    echo [env] Installed Python is older than 3.10.
    exit /b 1
)
exit /b 0
