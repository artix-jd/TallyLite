@echo off
setlocal
cd /d "%~dp0"
echo =========================================
echo       TallyLite Windows Build + Setup
echo =========================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required only to BUILD TallyLite.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto failed
pyinstaller --noconfirm --clean --windowed --name TallyLite --icon "ac_logo.ico" --collect-all customtkinter app.py
if errorlevel 1 goto failed
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php
  pause
  exit /b 1
)
"%ISCC%" "TallyLite-Setup.iss"
if errorlevel 1 goto failed
echo.
echo BUILD COMPLETE: Output\TallyLite-Setup-1.0.1.exe
echo Test the installer on a separate Windows PC before publishing.
pause
exit /b 0
:failed
echo BUILD FAILED. Take a screenshot of this window and share it.
pause
exit /b 1
