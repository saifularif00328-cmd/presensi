# Tutorial Tahap 2 — Pindah ke VPS (setelah > 3 sekolah)

Semua sekolah berjalan di **satu VPS** (mis. Rumahweb VPS M, Ubuntu). Tiap sekolah tetap punya
database & folder sendiri. VPS **tidak membuka port web** — semua akses lewat Cloudflare Tunnel,
jadi alamat sekolah (`https://smpn1.presensiku.biz.id`) **tidak berubah** dan perangkat ESP32 /
orang tua tidak perlu disetel ulang.

```
Cloudflare ─▶ tunnel VPS ─▶ Nginx 127.0.0.1:8080 ─┬─▶ presensi@smpn1 :7001 ─┐
                                                  ├─▶ presensi@smpn2 :7002 ─┼─▶ MariaDB (1 database/sekolah)
                                                  └─▶ ...                   ─┘
```

## 1. Sewa VPS
Rumahweb → VPS Indonesia → **VPS Linux M** (1 vCPU / 2 GB, ±5–8 sekolah) → OS **Ubuntu 22.04/24.04**,
tanpa panel. Catat **IP** dan **password root** dari email.

## 2. Pasang (±10 menit)
Dari laptop (PowerShell / Terminal):
```bash
ssh root@IP-VPS
curl -fsSL https://raw.githubusercontent.com/saifularif00328-cmd/presensi/claude/aplikasi-sesuai-prd-bppvd6/deploy/install_vps.sh | bash
```
Skrip memasang MariaDB, Nginx, aplikasi, firewall (hanya SSH), cloudflared, dan backup harian.

## 3. Hubungkan VPS ke Cloudflare (sekali)
1. Cloudflare → **Networks → Tunnels → Create a tunnel** → nama `vps` → pilih **Debian/Ubuntu (64-bit)**.
2. Salin perintah `sudo cloudflared service install <TOKEN>` → jalankan di VPS.

## 4. Pindahkan satu sekolah
1. Di aplikasi sekolah lama: **Pengaturan → Backup** → unduh ZIP.
2. Kirim ZIP ke VPS (dari laptop): `scp presensi-backup-....zip root@IP-VPS:/root/`
3. Di VPS:
   ```bash
   presensi-sekolah pindah smpn1 /root/presensi-backup-....zip --nama "SMP Negeri 1" --hari 365
   ```
4. Cloudflare → **Tunnels**:
   - tunnel **smpn1** (tunnel sekolah) → *Public hostname* → **hapus** `smpn1.presensiku.biz.id`;
   - tunnel **vps** → *Public hostname* → **Add**: `smpn1` · `presensiku.biz.id` → HTTP `localhost:8080`.
5. Buka `https://smpn1.presensiku.biz.id` → data lengkap. Selesai; komputer sekolah boleh dimatikan
   (atau dipakai sebagai PC piket saja).

> Lakukan pemindahan di luar jam sekolah (mis. sore/malam). Tap kartu selama proses tersimpan di
> ESP32 / browser dan terkirim otomatis setelah alamat mengarah ke VPS.

## 5. Sekolah baru langsung di VPS
```bash
presensi-sekolah tambah smpn2 --nama "SMP Negeri 2" --hari 365 --maks-siswa 1000
```
Lalu di tunnel **vps** tambahkan Public hostname `smpn2.presensiku.biz.id` → `localhost:8080`.

## 6. Mengelola langganan
| Perintah | Fungsi |
|---|---|
| `presensi-sekolah daftar` | Semua sekolah, status, tanggal berakhir, layanan |
| `presensi-sekolah perpanjang smpn1 --hari 180` | Perpanjang (menyambung dari tanggal habis) |
| `presensi-sekolah perpanjang smpn1 --sampai 2027-06-30 --maks-siswa 1200` | Atur tanggal & batas siswa |
| `presensi-sekolah nonaktif smpn1` / `aktifkan smpn1` | Mode baca-saja / aktif kembali |
| `presensi-sekolah backup --semua` | Backup manual (otomatis tiap 03.00, simpan 14) |
| `presensi-sekolah status` | RAM, disk, layanan — **naik ke VPS L bila RAM terpakai > 80%** |
| `presensi-sekolah hapus smpn1 --ya` | Hapus sekolah (backup dibuat dulu) |

## 7. Memperbarui aplikasi
Jalankan ulang skrip pemasangan (aman diulang), lalu mulai ulang layanan:
```bash
curl -fsSL .../deploy/install_vps.sh | bash
systemctl restart 'presensi@*'
```

## 8. Backup ke luar VPS (disarankan)
```bash
apt install -y rclone && rclone config        # tambahkan remote "gdrive" (Google Drive)
echo '30 3 * * * root rclone copy /srv/presensi/_backup gdrive:presensi-backup' > /etc/cron.d/presensi-rclone
```
