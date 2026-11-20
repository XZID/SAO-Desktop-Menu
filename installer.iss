; SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)
; Inno Setup script for the optional one-click installer (SAO-Desktop-Menu-Setup.exe).
; It is built automatically on GitHub (.github/workflows/build.yml) - you don't need to run it yourself.
; Expects the PyInstaller output in "dist\SAO Desktop Menu\".

#define AppName "SAO Desktop Menu"
#define AppExe "SAO Desktop Menu.exe"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #undef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8E3B1C7A-5D2F-4F4B-9C61-3A7E2B9D4F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Arthur_Zid
AppCopyright=Copyright (c) 2026 Arthur_Zid
; installs just for the current user: no admin password needed
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=installer-output
OutputBaseFilename=SAO-Desktop-Menu-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nHold the middle mouse button on an empty spot of your desktop and drag down: an SAO-style menu slides open with every app on your PC.%n%nby Arthur_Zid

[Tasks]
Name: "startup";     Description: "Start SAO Desktop Menu automatically when I log in"; GroupDescription: "Options:"
Name: "intro";       Description: "Play the LINK START intro when my PC starts";      GroupDescription: "Options:"
Name: "wallpaper";   Description: "Use the SAO wallpaper (your current one comes back if you uninstall)"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\SAO Desktop Menu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}";      Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\Stop {#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--stop"
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";       Filename: "{app}\{#AppExe}"; Parameters: "--startup"; Tasks: startup

[Run]
; save the choices from the Options page
Filename: "{app}\{#AppExe}"; Parameters: "--set intro=true";          Tasks: intro;         Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: "--set intro=false";         Tasks: not intro;     Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: "--set set_wallpaper=true";  Tasks: wallpaper;     Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: "--set set_wallpaper=false"; Tasks: not wallpaper; Flags: runhidden waituntilterminated
; last page: "Launch SAO Desktop Menu now"
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; turn it off and put the old wallpaper back before removing files
Filename: "{app}\{#AppExe}"; Parameters: "--stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopMenu"

[UninstallDelete]
; settings, icon cache and the menu's private browser profile
Type: filesandordirs; Name: "{localappdata}\SAO Desktop Menu"

[Code]
// When updating to a newer version, stop the running copy first so its files can be replaced.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  rc: Integer;
begin
  if FileExists(ExpandConstant('{app}\{#AppExe}')) then
    Exec(ExpandConstant('{app}\{#AppExe}'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Result := '';
end;
