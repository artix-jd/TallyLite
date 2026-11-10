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
if exist "ac_logo.ico" (
  pyinstaller --noconfirm --clean --windowed --name TallyLite --icon "ac_logo.ico" --add-data "ac_logo.ico;." --add-data "README.md;." --add-data "CHANGELOG.md;." --collect-all customtkinter app.py
) else (
  pyinstaller --noconfirm --clean --windowed --name TallyLite --add-data "README.md;." --add-data "CHANGELOG.md;." --collect-all customtkinter app.py
)
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
echo BUILD COMPLETE: Output\TallyLite-Setup-1.0.0.exe
echo Upload that Setup.exe to GitHub Releases.
pause
exit /b 0
:failed
echo BUILD FAILED. Share a screenshot of this window.
pause
exit /b 1
