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

[Icons]
Name: "{autoprograms}\Job Hunter"; Filename: "{app}\JobHunter.exe"
Name: "{autodesktop}\Job Hunter"; Filename: "{app}\JobHunter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\JobHunter.exe"; Description: "{cm:LaunchProgram,Job Hunter}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove the 30-minute Auto-run task. Your CVs, profile and keys in %APPDATA%\Job Hunter are kept.
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Remote Job Hunter"" /F"; Flags: runhidden; RunOnceId: "DeleteAutoRun"
