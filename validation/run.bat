@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PLAYWRIGHT_BROWSERS_PATH=%CD%\.playwright-browsers"
set "PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\validation;%PYTHONPATH%"

echo ==========================================
echo   Validation probe (to be deleted)
echo ==========================================
echo.
if not exist "%VENV_PY%" (
    echo Run root run.bat to install env first.
    pause
    exit /b 1
)

:menu
echo   [1] login
echo   [2] capture URI
echo   [3] send-test
echo   [4] list latest raw log
echo   [5] analyze log
echo   [0] exit
echo.
set "choice="
set /p choice=choice:
if "%choice%"=="1" goto login
if "%choice%"=="2" goto capture
if "%choice%"=="3" goto sendtest
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto analyze
if "%choice%"=="0" exit /b 0
echo invalid
goto menu

:login
"%VENV_PY%" -m huya_probe login
pause
goto menu

:capture
set "room="
set /p room=room id or URL:
if "%room%"=="" goto menu
echo %room% | findstr /i "huya.com" >nul
if %errorlevel%==0 (
    "%VENV_PY%" -m huya_probe capture --url "%room%"
) else (
    "%VENV_PY%" -m huya_probe capture --room "%room%"
)
pause
goto menu

:sendtest
set "room="
set /p room=room id or URL:
if "%room%"=="" goto menu
echo %room% | findstr /i "huya.com" >nul
if %errorlevel%==0 (
    "%VENV_PY%" -m huya_probe send-test --url "%room%"
) else (
    "%VENV_PY%" -m huya_probe send-test --room "%room%"
)
pause
goto menu

:logs
set "latest="
for /f "delims=" %%f in ('dir /b /o-d "validation\event-captures\*-raw.jsonl" 2^>nul') do (
    if not defined latest set "latest=%%f"
)
if not defined latest (
    echo no raw logs
) else (
    echo latest: validation\event-captures\%latest%
)
pause
goto menu

:analyze
"%VENV_PY%" -m huya_probe analyze --log-dir validation\event-captures
pause
goto menu
