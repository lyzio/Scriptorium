; Inno Setup script for the Scriptorum setup program (design document F10).
; build.py runs it with ISCC and passes the /D values below; it is not meant
; to be compiled by hand.
;
; Installs for the current user by default (no administrator needed); the
; first page lets the user choose to install for everyone instead. Registers
; .scav (opens the adventure) and .scmod (offers to install the module), each
; with its own icon, and removes them again on uninstall.

#ifndef AppVersion
  #error AppVersion is not set: run build.py instead of compiling this by hand
#endif

[Setup]
AppId={{5B1C2A0E-7D44-4E1B-9C0F-3A6E2D8B5F17}
AppName=Scriptorum
AppVersion={#AppVersion}
AppVerName=Scriptorum {#AppVersion}
AppPublisher=Scriptorum project
AppComments=A text processor for game masters writing their own adventures
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Scriptorum
DefaultGroupName=Scriptorum
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion={#MinVersion}
ChangesAssociations=yes
SetupIconFile={#IconsDir}\scriptorum.ico
UninstallDisplayIcon={app}\Scriptorum.exe
UninstallDisplayName=Scriptorum {#AppVersion}
WizardStyle=modern
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
Compression=lzma2/max
SolidCompression=yes
InfoBeforeFile={#InstallNotes}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\scav.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "{#IconsDir}\scmod.ico"; DestDir: "{app}\icons"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Scriptorum"; Filename: "{app}\Scriptorum.exe"
Name: "{autodesktop}\Scriptorum"; Filename: "{app}\Scriptorum.exe"; Tasks: desktopicon

[Registry]
; HKA is the current user's classes for a per-user install, the machine's for an all-users install.
Root: HKA; Subkey: "Software\Classes\.scav"; ValueType: string; ValueName: ""; ValueData: "{#ScavProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.scav\OpenWithProgids"; ValueType: string; ValueName: "{#ScavProgId}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#ScavProgId}"; ValueType: string; ValueName: ""; ValueData: "Scriptorum adventure"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ScavProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icons\scav.ico"
Root: HKA; Subkey: "Software\Classes\{#ScavProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Scriptorum.exe"" ""%1"""

Root: HKA; Subkey: "Software\Classes\.scmod"; ValueType: string; ValueName: ""; ValueData: "{#ScmodProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.scmod\OpenWithProgids"; ValueType: string; ValueName: "{#ScmodProgId}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#ScmodProgId}"; ValueType: string; ValueName: ""; ValueData: "Scriptorum module"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ScmodProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icons\scmod.ico"
Root: HKA; Subkey: "Software\Classes\{#ScmodProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Scriptorum.exe"" ""%1"""

Root: HKA; Subkey: "Software\Classes\Applications\Scriptorum.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Scriptorum"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\Scriptorum.exe\SupportedTypes"; ValueType: string; ValueName: ".scav"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\Scriptorum.exe\SupportedTypes"; ValueType: string; ValueName: ".scmod"; ValueData: ""

[Run]
Filename: "{app}\Scriptorum.exe"; Description: "{cm:LaunchProgram,Scriptorum}"; Flags: nowait postinstall skipifsilent
