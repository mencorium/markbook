; /markbook_desktop/installer/markbook.iss
; Inno Setup script: builds MarkbookSetup.exe from the PyInstaller output.
;   1. pyinstaller markbook.spec --noconfirm      (creates dist\Markbook)
;   2. open this file in Inno Setup and press Build, or:
;      "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\markbook.iss
; Inno Setup is free: https://jrsoftware.org/isdl.php

#define AppName     "Markbook"
#define AppVersion  "1.0.0"
#define AppPublisher "Joel"
#define AppExe      "markbook.exe"

[Setup]
AppId={{B7C3F2A1-7E4D-4C8B-9A15-3D6E2F0A9C41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=MarkbookSetup-{#AppVersion}
SetupIconFile=..\assets\markbook.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; per-user install needs no administrator rights; use "admin" to install for everyone
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; everything PyInstaller produced
Source: "..\dist\Markbook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; a starting .env, kept if the person already has one
Source: "..\.env"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start Markbook"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the .env is written by the app on first run, so remove it with the program
Type: files; Name: "{app}\.env"

[Messages]
WelcomeLabel2=This will install {#AppName} on your computer.%n%nMarkbook stores marks in PostgreSQL. If PostgreSQL is not installed yet, install it first from https://www.postgresql.org/download/windows/ — Markbook will ask for the connection the first time it starts.%n%nYour own data (marks, backups, logs) is never removed by the uninstaller.
