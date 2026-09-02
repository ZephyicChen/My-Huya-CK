@echo off
rem Pre-release checks: tests, defaults, whitespace, and tracked local data.
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
call tests.bat
if errorlevel 1 exit /b 1

"%~dp0.venv\Scripts\python.exe" "%~dp0release_check.py"
if errorlevel 1 exit /b 1

echo.
echo ===== Git changes =====
git -c core.quotepath=false status --short
echo.
echo Release checks passed.
exit /b 0
