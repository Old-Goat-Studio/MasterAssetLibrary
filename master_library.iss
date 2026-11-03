; SPDX-License-Identifier: Apache-2.0
; Inno Setup script for the Master Asset Library. Build it with
; `python tools/package.py --installer`, which first makes the PyInstaller folder in
; build\dist\MasterAssetLibrary and the icon build\MasterAssetLibrary.ico, then runs:
;   ISCC /DAppVersion=0.1.0 /DAppBuild=1 master_library.iss
; The installer lands in build\installer\.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppBuild
  #define AppBuild "0"
#endif
#define AppName "Master Asset Library"
#define AppExe "MasterAssetLibrary.exe"

[Setup]
AppId={{9C3E5B71-2D84-4F0A-B6E2-7A51C8D90F34}
AppName={#AppName}
AppVersion={#AppVersion}.{#AppBuild}
AppVerName={#AppName} {#AppVersion} (build {#AppBuild})
AppPublisher=Old Goat Studio
VersionInfoVersion={#AppVersion}.{#AppBuild}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=build\installer
OutputBaseFilename=MasterAssetLibrary-Setup-{#AppVersion}.{#AppBuild}
SetupIconFile=build\MasterAssetLibrary.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; One folder, so the Qt libraries stay separate files that users can replace (LGPL).
Source: "build\dist\MasterAssetLibrary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; A new build replaces the old one completely (no stale libraries from an earlier build).
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; The library and settings are the user's own and are left in place on uninstall.
