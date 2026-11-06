@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [CI76] Preparing Python 3.12 environment...
    py -3.12 -m venv .venv
    if errorlevel 1 goto :err
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto :err
)
.venv\Scripts\python.exe main.py
if errorlevel 1 goto :err
exit /b 0
:err
echo.
echo CI76 tool failed to start. Review the error above.
pause
exit /b 1
