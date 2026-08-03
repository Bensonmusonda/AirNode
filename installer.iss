; AirNode Inno Setup installer.
; Build: ISCC.exe /DAppVersion=1.0.0 /DSourceDir=dist\AirNode-1.0.0 installer.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\AirNode-1.0.0"
#endif
#define AppName "AirNode"
#define AppPublisher "Benson Musonda"
#define AppURL "https://github.com/Bensonmusonda/AirNode"

[Setup]
AppId={{8F4B1C22-9B2A-4E7C-9D3E-5A1C2B3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=AirNode-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; SignTool=signtool /f "cert.pfx" /t http://timestamp.digicert.com /fd sha256 $f
UninstallDisplayIcon={app}\AirNode.exe
UninstallDisplayName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start AirNode automatically when you log in"; GroupDescription: "Startup:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\AirNode.exe"
Name: "{group}\{#AppName} - Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AirNode.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AirNode.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\AirNode.exe"; Parameters: "--install-autostart"; Flags: runhidden; Tasks: autostart

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.airnode_*"
Type: files; Name: "{app}\airnode-config.json"
Type: files; Name: "{app}\airnode.log"
Type: filesandordirs; Name: "{app}\static\generated"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    Exec('schtasks.exe', '/Delete /TN "AirNode" /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;