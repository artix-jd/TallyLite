# TallyLite

TallyLite is a lightning-fast, 100% offline-first double-entry bookkeeping and accounting software for Windows. Built as a private, local-first alternative to cloud SaaS and Tally.

## For Windows users

Download `TallyLite-Setup-1.0.0.exe` from [GitHub Releases](https://github.com/artix-jd/TallyLite/releases) and run it. It installs TallyLite for the current Windows user and creates a Start menu shortcut. Python and Inno Setup are not required by end users.

### Windows SmartScreen / Smart App Control Note

Because TallyLite is an independent, open-source application built without a commercial digital signing certificate, Windows 11 may display a blue protection warning when you run the installer for the first time.

If Windows blocks the installation:
1. Click the **More info** link on the warning window.
2. Click the **Run anyway** button that appears at the bottom.
*(Alternatively, right-click `TallyLite-Setup-1.0.0.exe`, select **Properties**, check the **Unblock** box at the bottom of the General tab, and click Apply).*

---

## Build the installer (maintainers)

1. On a Windows build PC, install Python 3.10+ and Inno Setup 6.
2. Double-click `build_windows.bat`.
3. The installer is created at `Output\TallyLite-Setup-1.0.0.exe`.
4. Test it on a clean Windows PC before publishing.

*Inno Setup:* [Download Inno Setup](https://jrsoftware.org/isdl.php)

---

## Privacy & Data Storage

TallyLite stores accounting data locally in `%LOCALAPPDATA%\TallyLite\`. Program files install separately in `%LOCALAPPDATA%\Programs\TallyLite\`. 

* The installer does not bundle any developer personal database, books, backups, or exports. 
* Uninstalling the app does not intentionally delete your accounting data.
* The app works 100% offline. Source-code review is not a formal security audit. Do not publish databases, backups, exports, credentials, or signing keys.

---

## Build from source

```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
