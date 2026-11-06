@echo off
setlocal
cd /d "%~dp0"
set "VENV=.venv\Scripts\python.exe"
echo.
echo  Native PDF Eraser - Windows EXE Builder
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
"%VENV%" -m pip install --disable-pip-version-check -r requirements.txt "pyinstaller>=6,<7"
if errorlevel 1 goto :failed
"%VENV%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Native-PDF-Eraser" --icon "assets\native_pdf_eraser.ico" --add-data "assets;assets" --collect-all pymupdf main.py
if errorlevel 1 goto :failed
echo.
echo  BUILD COMPLETED
 echo  EXE-Datei: dist\Native-PDF-Eraser.exe
 echo  This single EXE can be copied to other Windows computers (no Python needed there).
 echo.
pause
exit /b 0
:failed
echo.
echo Build fehlgeschlagen. Bitte Internetverbindung und Python 3.11+ prüfen.
pause
exit /b 1
