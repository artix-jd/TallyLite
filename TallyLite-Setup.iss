#define MyAppName "TallyLite"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TallyLite Contributors"
#define MyAppExeName "TallyLite.exe"

[Setup]
AppId={{A3D5B6E7-9C21-4F18-9A2D-6E1B7C4F8053}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\TallyLite
DefaultGroupName=TallyLite
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=TallyLite-Setup-{#MyAppVersion}
SetupIconFile=ac_logo.ico
UninstallDisplayIcon={app}\TallyLite.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\TallyLite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TallyLite"; Filename: "{app}\TallyLite.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\TallyLite"; Filename: "{app}\TallyLite.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\TallyLite.exe"; Description: "Launch TallyLite"; Flags: postinstall nowait skipifsilent
