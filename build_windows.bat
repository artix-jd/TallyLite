@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo          TallyLite Windows Builder
echo ========================================

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required to BUILD the app. End users do not need Python.
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

if exist "TallyLite-Windows.zip" del "TallyLite-Windows.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\TallyLite' -DestinationPath 'TallyLite-Windows.zip' -Force"
if errorlevel 1 goto failed

echo.
echo BUILD COMPLETE.
echo Portable user download: TallyLite-Windows.zip
echo Upload this ZIP to GitHub Releases for easy installation.
echo Do not include any personal books, backups, or exports.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Take a screenshot of this window and share it.
pause
exit /b 1
