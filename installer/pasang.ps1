# ============================================================================
#  Presensi Siswa Digital — penyiapan server sekolah (Windows)
#  Dijalankan otomatis oleh installer (sebagai Administrator). Aman diulang.
#
#  Yang dilakukan:
#   1. MariaDB (MySQL) sebagai Windows Service "PresensiDB" (port 3306, hanya localhost)
#   2. Database + user "presensi" dengan password acak -> data\config.ini
#   3. Aplikasi sebagai Windows Service "PresensiApp" (auto start, hidup lagi bila berhenti)
#   4. Firewall: port 5000 dibuka untuk jaringan sekolah (Private/Domain)
#   5. Komputer tidak pernah sleep/hibernate; Windows Update tidak restart di jam sekolah
# ============================================================================
param([string]$Folder = $PSScriptRoot)
$ErrorActionPreference = "Stop"
Set-Location $Folder

function Log($t) { Write-Host "[Presensi] $t" }
function AcakPassword { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ }) }

$Data    = Join-Path $Folder "data"
$DbData  = Join-Path $Folder "mysql-data"
$MariaDB = Get-ChildItem (Join-Path $Folder "mariadb") -Directory | Select-Object -First 1
if (-not $MariaDB) { $MariaDB = Get-Item (Join-Path $Folder "mariadb") }
$Bin     = Join-Path $MariaDB.FullName "bin"
$Config  = Join-Path $Data "config.ini"
New-Item -ItemType Directory -Force -Path $Data | Out-Null

# ---------------------------------------------------------------- 1. MariaDB
$svcDb = Get-Service -Name "PresensiDB" -ErrorAction SilentlyContinue
if (-not $svcDb) {
    Log "Menyiapkan database MariaDB..."
    $rootPw = AcakPassword
    $install = Join-Path $Bin "mariadb-install-db.exe"
    if (-not (Test-Path $install)) { $install = Join-Path $Bin "mysql_install_db.exe" }
    & $install "--datadir=$DbData" "--service=PresensiDB" "--password=$rootPw" "--port=3306" | Out-Host
    # hanya terima koneksi dari komputer ini
    Add-Content -Path (Join-Path $DbData "my.ini") -Value "`r`n[mysqld]`r`nbind-address=127.0.0.1`r`ncharacter-set-server=utf8mb4`r`ncollation-server=utf8mb4_unicode_ci`r`n"
    Set-Content -Path (Join-Path $Data "root.txt") -Value "Password root MariaDB (simpan baik-baik): $rootPw"
    Set-Service -Name "PresensiDB" -StartupType Automatic
    Start-Service -Name "PresensiDB"
    Start-Sleep -Seconds 5

    Log "Membuat database & user aplikasi..."
    $appPw = AcakPassword
    $sql = "CREATE DATABASE IF NOT EXISTS presensi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; " +
           "CREATE USER IF NOT EXISTS 'presensi'@'localhost' IDENTIFIED BY '$appPw'; " +
           "GRANT ALL PRIVILEGES ON presensi.* TO 'presensi'@'localhost'; FLUSH PRIVILEGES;"
    $client = Join-Path $Bin "mariadb.exe"
    if (-not (Test-Path $client)) { $client = Join-Path $Bin "mysql.exe" }
    & $client "-uroot" "-p$rootPw" "-h127.0.0.1" "-e" $sql
    @"
[database]
host = 127.0.0.1
port = 3306
user = presensi
password = $appPw
database = presensi
"@ | Set-Content -Path $Config -Encoding UTF8
} else {
    Log "Database PresensiDB sudah ada — dilewati."
    if ($svcDb.Status -ne "Running") { Start-Service -Name "PresensiDB" }
}

# ---------------------------------------------------------------- 2. aplikasi sebagai service
$svcApp = Get-Service -Name "PresensiApp" -ErrorAction SilentlyContinue
$winsw = Join-Path $Folder "layanan\PresensiApp.exe"
if (-not $svcApp) {
    Log "Memasang layanan aplikasi..."
    & $winsw install | Out-Host
}
& sc.exe failure PresensiApp reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
& sc.exe failure PresensiDB reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
Set-Service -Name "PresensiApp" -StartupType Automatic
Restart-Service -Name "PresensiApp" -ErrorAction SilentlyContinue
if ((Get-Service -Name "PresensiApp").Status -ne "Running") { Start-Service -Name "PresensiApp" }

# ---------------------------------------------------------------- 3. firewall
if (-not (Get-NetFirewallRule -DisplayName "Presensi Siswa 5000" -ErrorAction SilentlyContinue)) {
    Log "Membuka port 5000 untuk jaringan sekolah..."
    New-NetFirewallRule -DisplayName "Presensi Siswa 5000" -Direction Inbound -Protocol TCP `
        -LocalPort 5000 -Action Allow -Profile Private,Domain | Out-Null
}

# ---------------------------------------------------------------- 4. anti-sleep & Windows Update
Log "Mengatur daya: tidak pernah sleep/hibernate saat tercolok listrik..."
powercfg /change standby-timeout-ac 0 | Out-Null
powercfg /change hibernate-timeout-ac 0 | Out-Null
powercfg /change disk-timeout-ac 0 | Out-Null
# jam aktif Windows Update 06.00-18.00 -> restart otomatis hanya di luar jam sekolah
$wu = "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
if (-not (Test-Path $wu)) { New-Item -Path $wu -Force | Out-Null }
Set-ItemProperty -Path $wu -Name "ActiveHoursStart" -Value 6 -Type DWord
Set-ItemProperty -Path $wu -Name "ActiveHoursEnd" -Value 18 -Type DWord

Log "Selesai. Buka http://localhost:5000 (login awal admin / admin123)."
