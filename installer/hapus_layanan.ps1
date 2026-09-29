# Dijalankan saat uninstall: hentikan & hapus layanan. Folder data dan mysql-data TIDAK dihapus.
$ErrorActionPreference = "SilentlyContinue"
foreach ($svc in "PresensiApp", "cloudflared", "PresensiDB") {
    Stop-Service -Name $svc -Force
}
& (Join-Path $PSScriptRoot "layanan\PresensiApp.exe") uninstall
& (Join-Path $PSScriptRoot "cloudflared.exe") service uninstall
sc.exe delete PresensiDB | Out-Null
Remove-NetFirewallRule -DisplayName "Presensi Siswa 5000"
