@echo off
cd /d "%~dp0"
echo ==========================================
echo   HWP Passage Automation
echo ==========================================
echo.

set "PY_CMD="
where python >nul 2>&1
if %errorlevel%==0 set "PY_CMD=python"
if not "%PY_CMD%"=="" goto :found_py

where py >nul 2>&1
if %errorlevel%==0 set "PY_CMD=py -3"
if not "%PY_CMD%"=="" goto :found_py

echo [ERROR] Python is not installed or not in PATH.
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo Make sure to check Add Python to PATH during installation.
echo.
pause
exit /b 1

:found_py
echo Using Python: %PY_CMD%
if exist ".venv\Scripts\python.exe" goto :has_venv

echo [1/3] Creating virtual environment...
%PY_CMD% -m venv .venv
if errorlevel 1 goto :venv_fail
goto :has_venv

:venv_fail
echo [ERROR] Failed to create virtual environment.
pause
exit /b 1

:has_venv
set "VENV_PY=.venv\Scripts\python.exe"

echo [2/3] Installing required packages...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_fail

echo.
echo [3/3] Starting web app in your browser...
echo Keep this window open while using the app.
echo.
"%VENV_PY%" -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
echo.
echo App closed. Press any key to exit.
pause
exit /b 0

:pip_fail
echo.
echo [ERROR] Failed to install required packages.
pause
exit /b 1
