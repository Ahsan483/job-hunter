; Inno Setup script for JobHunterSetup.exe. Run installer\build.ps1 rather than this file directly:
; it builds build\dist\JobHunter with PyInstaller first.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{10036058-60D5-49FE-842A-862152EBB4A7}
AppName=Job Hunter
AppVersion={#AppVersion}
AppVerName=Job Hunter {#AppVersion}
AppPublisher=Code Projects Official
AppPublisherURL=https://www.codeprojectsofficial.com/tools/job-hunter
AppSupportURL=https://github.com/Ahsan483/job-hunter/issues
AppUpdatesURL=https://www.codeprojectsofficial.com/tools/job-hunter
; Installs for the current user only: no admin prompt. Your files stay in %APPDATA%\Job Hunter.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Job Hunter
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\build\installer
OutputBaseFilename=JobHunterSetup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\JobHunter.exe
UninstallDisplayName=Job Hunter
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\dist\JobHunter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The window needs Microsoft Edge WebView2. Windows 11 and up-to-date Windows 10 have it; otherwise it is installed.
Source: "..\build\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{autoprograms}\Job Hunter"; Filename: "{app}\JobHunter.exe"
Name: "{autodesktop}\Job Hunter"; Filename: "{app}\JobHunter.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 (needed for the window)..."; Flags: waituntilterminated runhidden; Check: NeedsWebView2
Filename: "{app}\JobHunter.exe"; Description: "{cm:LaunchProgram,Job Hunter}"; Flags: nowait postinstall skipifsilent
; The window's one-click update runs this installer silently with /UPDATE: open Job Hunter again afterwards.
Filename: "{app}\JobHunter.exe"; Flags: nowait runasoriginaluser; Check: IsUpdate

[UninstallRun]
; Remove the 30-minute Auto-run task. Your CVs, profile and keys in %APPDATA%\Job Hunter are kept.
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Remote Job Hunter"" /F"; Flags: runhidden; RunOnceId: "DeleteAutoRun"

[Code]
const
  WebView2Id = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key + WebView2Id, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function NeedsWebView2: Boolean;
begin
  Result := not (HasWebView2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\') or
                 HasWebView2(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\') or
                 HasWebView2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\'));
end;

function IsUpdate: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/UPDATE') = 0 then
      Result := True;
end;
