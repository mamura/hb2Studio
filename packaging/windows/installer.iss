#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
#ifndef DistDir
  #error DistDir deve apontar ao onedir produzido pelo PyInstaller
#endif
#ifndef OutputPath
  #error OutputPath deve apontar a pasta de saída do instalador
#endif
[Setup]
AppId={{32B7B5DD-9451-4A79-A3EC-03244BE36DA7}
AppName=HB2 Studio
AppVersion={#AppVersion}
AppPublisher=HB2 Studio
DefaultDirName={localappdata}\Programs\HB2 Studio
DefaultGroupName=HB2 Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableDirPage=yes
Uninstallable=yes
UninstallDisplayName=HB2 Studio
UninstallDisplayIcon={app}\HB2Studio.exe
OutputDir={#OutputPath}
OutputBaseFilename=HB2Studio-{#AppVersion}-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\HB2 Studio\HB2 Studio"; Filename: "{app}\HB2Studio.exe"; WorkingDir: "{userdocs}"
Name: "{userprograms}\HB2 Studio\Desinstalar HB2 Studio"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\HB2Studio.exe"; Description: "Abrir HB2 Studio"; Flags: nowait postinstall skipifsilent
