@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
"%VENV_PY%" -m pip install -r requirements.txt
"%VENV_PY%" -m pip install pyinstaller pywin32 pywebview

"%VENV_PY%" -m PyInstaller --noconfirm --onedir --windowed ^
    --name "HWP_Passage_Automation" ^
    --add-data "app.py;." ^
    --add-data "core;core" ^
    --add-data ".streamlit;.streamlit" ^
    --collect-all streamlit ^
    --collect-all google.genai ^
    --collect-all pydantic ^
    desktop_launcher.py

echo.
echo Build complete! Share the dist\HWP_Passage_Automation\ folder.
pause
endlocal
