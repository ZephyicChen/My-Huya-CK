@echo off
rem Run the complete product test suite.
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONWARNINGS=ignore"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo Run run.bat first to create the local environment.
    exit /b 1
)

"%VENV_PY%" -m unittest discover -s tests -v
exit /b %errorlevel%
