@echo off
setlocal
cd /d "%~dp0"
set "VENV=.venv\Scripts\python.exe"
echo.
echo  Native PDF Eraser - Windows Starter
 echo.
if not exist "%VENV%" (
    echo Creating isolated Python environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto :failed
)
if not exist ".venv\installed.ok" (
    echo Abhängigkeiten werden installiert (beim ersten Start ist Internet nötig)...
    "%VENV%" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :failed
    echo installed > ".venv\installed.ok"
)
"%VENV%" main.py
if errorlevel 1 goto :failed
exit /b 0
:failed
 echo.
 echo Start/Einrichtung fehlgeschlagen. Bitte prüfen, ob Python 3.11 oder neuer installiert ist.
 echo Press any key to close this window.
 pause >nul
exit /b 1
