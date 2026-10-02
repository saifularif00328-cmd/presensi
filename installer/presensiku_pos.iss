; ============================================================================
;  Installer "Presensiku Pos" (Inno Setup 6) — aplikasi PC pos untuk banyak scanner
;  Build: pyinstaller pos\presensiku_pos.spec  lalu  ISCC installer\presensiku_pos.iss
;  Hasil: installer\Output\presensiku-pos-setup.exe   (dibuat otomatis oleh GitHub Actions)
; ============================================================================
#define AppName "Presensiku Pos"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{9B1E4C2A-7D3F-4A61-8E5C-2F0B6A9D1C77}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Presensiku
DefaultDirName={autopf}\Presensiku Pos
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=presensiku-pos-setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#AppName}
CloseApplications=force

[Languages]
Name: "id"; MessagesFile: "Indonesian.isl"

[Files]
Source: "..\dist\PresensikuPos\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Dirs]
; data (pasangan server, antrean scan offline, salinan siswa) tidak dihapus saat uninstall
Name: "{commonappdata}\PresensikuPos"; Permissions: users-modify; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Layar Gerbang"; Filename: "{app}\PresensikuPos.exe"
Name: "{commondesktop}\Layar Gerbang"; Filename: "{app}\PresensikuPos.exe"
; berjalan otomatis saat Windows menyala (scan tetap tercatat walau layar belum dibuka)
Name: "{commonstartup}\Presensiku Pos"; Filename: "{app}\PresensikuPos.exe"

[Run]
Filename: "{app}\PresensikuPos.exe"; Description: "Jalankan Presensiku Pos sekarang"; Flags: postinstall nowait

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM PresensikuPos.exe"; Flags: runhidden; RunOnceId: "TutupPos"
