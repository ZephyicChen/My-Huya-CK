@echo off
rem Entry point: prepare .venv and Chromium, then run python -m huya_ck.
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
if not defined PLAYWRIGHT_DOWNLOAD_HOST set "PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

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

:ensure_env
if exist "%VENV_PY%" (
    "%VENV_PY%" "%~dp0ensure_env.py"
    exit /b %errorlevel%
)
call :find_host_python
if errorlevel 1 exit /b 1
%HOST_PY% "%~dp0ensure_env.py"
if errorlevel 1 exit /b 1
if not exist "%VENV_PY%" exit /b 1
exit /b 0

:find_host_python
set "HOST_PY="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" 2>nul
if not errorlevel 1 (
    set "HOST_PY=py -3"
    exit /b 0
)
python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" 2>nul
if not errorlevel 1 (
    set "HOST_PY=python"
    exit /b 0
)
echo [env] Python 3.10+ not found.
exit /b 1
