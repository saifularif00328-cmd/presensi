; ============================================================================
;  Installer Windows "Presensi Siswa Digital" (Inno Setup 6, gratis: jrsoftware.org)
;
;  Isi installer:
;    - aplikasi (hasil build_exe.bat: dist\PresensiSiswa\*)
;    - MariaDB portable (database MySQL)          -> installer\bundel\mariadb\
;    - cloudflared.exe (Cloudflare Tunnel)        -> installer\bundel\cloudflared.exe
;    - WinSW-x64.exe (pembungkus Windows Service) -> installer\bundel\WinSW-x64.exe
;  Siapkan bundel sekali dengan: powershell -ExecutionPolicy Bypass -File installer\siapkan_bundel.ps1
;  Lalu buka file ini di Inno Setup -> Build -> Compile. Hasil: installer\Output\PasangPresensi.exe
; ============================================================================
#define AppName "Presensi Siswa Digital"
#define AppVersion "2.0.0"

[Setup]
AppId={{6C7A2B8E-3F1D-4C55-9E2B-0A1B2C3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Presensiku
DefaultDirName=C:\PresensiSiswa
DisableDirPage=no
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=PasangPresensi-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#AppName}

[Languages]
Name: "id"; MessagesFile: "Indonesian.isl"

[Files]
Source: "..\dist\PresensiSiswa\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "bundel\mariadb\*"; DestDir: "{app}\mariadb"; Flags: recursesubdirs ignoreversion
Source: "bundel\cloudflared.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "bundel\WinSW-x64.exe"; DestDir: "{app}\layanan"; DestName: "PresensiApp.exe"; Flags: ignoreversion
Source: "layanan\PresensiApp.xml"; DestDir: "{app}\layanan"; Flags: ignoreversion
Source: "pasang.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "hapus_layanan.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; folder data & database TIDAK dihapus saat uninstall (data sekolah aman)
Name: "{app}\data"; Flags: uninsneveruninstall
Name: "{app}\mysql-data"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Buka Presensi"; Filename: "http://localhost:5000"
Name: "{commondesktop}\Presensi Siswa"; Filename: "http://localhost:5000"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\pasang.ps1"" -Folder ""{app}"""; \
  StatusMsg: "Menyiapkan database dan layanan (1-2 menit)..."; Flags: runhidden waituntilterminated
Filename: "http://localhost:5000"; Description: "Buka aplikasi Presensi"; Flags: postinstall shellexec nowait

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\hapus_layanan.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "HapusLayanan"
