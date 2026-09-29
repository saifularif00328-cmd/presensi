# ============================================================================
#  Unduh komponen installer (sekali, di laptop vendor yang ada internet):
#    powershell -ExecutionPolicy Bypass -File installer\siapkan_bundel.ps1
#  Hasil: installer\bundel\{mariadb\, cloudflared.exe, WinSW-x64.exe}
#  Versi bisa diganti di bawah bila ada versi yang lebih baru.
# ============================================================================
$ErrorActionPreference = "Stop"
$MariaDBVersi = "11.4.5"   # LTS
$Bundel = Join-Path $PSScriptRoot "bundel"
New-Item -ItemType Directory -Force -Path $Bundel | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Unduh($url, $tujuan) {
    Write-Host "Mengunduh $url"
    Invoke-WebRequest -Uri $url -OutFile $tujuan -UseBasicParsing
}

$zip = Join-Path $env:TEMP "mariadb.zip"
Unduh "https://archive.mariadb.org/mariadb-$MariaDBVersi/winx64-packages/mariadb-$MariaDBVersi-winx64.zip" $zip
$mdb = Join-Path $Bundel "mariadb"
if (Test-Path $mdb) { Remove-Item -Recurse -Force $mdb }
Expand-Archive -Path $zip -DestinationPath $mdb
# buang file yang tidak diperlukan agar installer lebih kecil
Get-ChildItem $mdb -Recurse -Include "*.pdb", "mysql-test", "sql-bench" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Unduh "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" (Join-Path $Bundel "cloudflared.exe")
Unduh "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" (Join-Path $Bundel "WinSW-x64.exe")
Write-Host "Selesai. Sekarang jalankan build_exe.bat lalu compile installer\presensi.iss di Inno Setup."
