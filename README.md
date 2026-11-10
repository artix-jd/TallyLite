# TallyLite

A local-first Windows desktop bookkeeping and accounting application.

## Features
- Multiple books
- Income, expenses and transfers
- Ledgers and balances
- Daybook and ledger statements
- Trial Balance, Profit & Loss and Balance Sheet
- Local backups and CSV exports

## Privacy and data storage
TallyLite is designed to work offline. Accounting data is stored locally on the Windows computer in:

`%LOCALAPPDATA%\TallyLite\`

The reviewed source contains no obvious network/API upload calls. This is not a formal security audit. Do not share your database, backups, or exports publicly.

## Windows download (for regular users)
Download `TallyLite-Windows.zip` from the project's GitHub **Releases** page, extract the ZIP, open the `TallyLite` folder, and double-click `TallyLite.exe`. Python is not required for users of this packaged build.

## Build from source (for developers)
1. Install Python 3.10 or newer on Windows.
2. Double-click `build_windows.bat`.
3. When it finishes, find `TallyLite-Windows.zip` in this folder. This contains the app and runtime files.

## Developer run
```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

## License
MIT. See `LICENSE`.
