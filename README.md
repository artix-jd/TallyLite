# TallyLite

A local-first Windows desktop bookkeeping and accounting application.

## For Windows users
Download `TallyLite-Setup-1.0.0.exe` from GitHub Releases and run it. It installs TallyLite for the current Windows user and creates a Start menu shortcut. Python and Inno Setup are not required by end users.

## Build the installer (maintainers)
1. On a Windows build PC, install Python 3.10+ and Inno Setup 6.
2. Double-click `build_windows.bat`.
3. The installer is created at `Output\TallyLite-Setup-1.0.0.exe`.
4. Test it on a clean Windows PC before publishing.

Inno Setup: https://jrsoftware.org/isdl.php

## Privacy
TallyLite stores accounting data locally in `%LOCALAPPDATA%\TallyLite\`. Program files install separately in `%LOCALAPPDATA%\Programs\TallyLite\`. The installer does not bundle a developer's personal database, books, backups, or exports. Uninstalling the app does not intentionally delete accounting data.

The app is intended to work offline. Source-code review is not a formal security audit. Do not publish databases, backups, exports, credentials, or signing keys.

## Build from source
```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

## License
MIT. See `LICENSE`.
