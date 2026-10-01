# Tutorial VPS — semua sekolah di presensiku.biz.id/&lt;kode&gt;

Semua sekolah berjalan di **satu VPS**, dan sekolah **tidak memasang apa pun**. Alamatnya berupa
jalur:

| Sekolah | Alamat |
|---|---|
| SMP Negeri 1 | `https://presensiku.biz.id/smpn1` |
| SMP Negeri 2 | `https://presensiku.biz.id/smpn2` |

Halaman depan `https://presensiku.biz.id` berisi kotak **kode sekolah**.

Setiap sekolah punya database, folder, login, dan cookie sendiri. VPS **tidak membuka port web**;
semua akses lewat Cloudflare Tunnel, cukup diatur **sekali**.

```
Cloudflare ─▶ tunnel VPS ─▶ Nginx 127.0.0.1:8080 ─┬─ /smpn1/ ─▶ presensi@smpn1 :7001 ─┐
                                                  ├─ /smpn2/ ─▶ presensi@smpn2 :7002 ─┼─▶ MariaDB
                                                  └─ /       ─▶ halaman "kode sekolah" ┘
```

## 1. VPS
Rumahweb **VPS Linux S** (1 vCPU / 1 GB / 20 GB), OS **Ubuntu 24.04**, tanpa panel.

- **Paket S** cukup untuk ±1–3 sekolah. Skrip otomatis menambah swap 2 GB dan menghemat RAM
  MariaDB.
- Naik ke **Paket M** bila `presensi-sekolah status` menunjukkan RAM terpakai > 80%, atau bila lebih
  dari 2 sekolah memakai absen wajah.

Catat **IP VPS** dan **password root** dari email Rumahweb. **Jangan kirim password ke siapa pun.**

## 2. Masuk ke VPS lewat SSH (Windows)
1. Tekan tombol **Windows**, ketik `powershell`, lalu Enter.
2. Ketik perintah berikut (ganti dengan IP VPS Anda):
   ```
   ssh root@103.xxx.xxx.xxx
   ```
3. Pertama kali akan muncul pertanyaan `Are you sure you want to continue connecting`. Ketik `yes`
   lalu Enter.
4. Masukkan password root. **Huruf tidak tampil saat diketik** (itu normal). Tekan Enter.
5. Berhasil bila muncul `root@server1:~#`.

> Tempel teks di PowerShell dengan **klik kanan**. Keluar dari VPS dengan perintah `exit`.
> Setelah login pertama, ganti password root dengan perintah `passwd`.

## 3. Pasang aplikasi (±10 menit)
Di VPS, jalankan:
```bash
curl -fsSL https://raw.githubusercontent.com/saifularif00328-cmd/presensi/claude/aplikasi-sesuai-prd-bppvd6/deploy/install_vps.sh | bash
```
Skrip memasang:
- swap;
- MariaDB (hemat RAM);
- Nginx;
- aplikasi;
- firewall (hanya SSH);
- cloudflared;
- backup harian pukul 03.00.

## 4. Hubungkan ke Cloudflare (sekali saja)
1. Buka dash.cloudflare.com → **Zero Trust → Networks → Tunnels → Create a tunnel →
   Cloudflared**. Beri nama `vps`.
2. Pilih **Debian** · **64-bit**, lalu salin perintah `sudo cloudflared service install eyJ...`
   dan jalankan di VPS.
3. Klik **Next**, lalu isi **Public hostname**:
   - Subdomain: *(kosongkan)*
   - Domain: `presensiku.biz.id`
   - Type: `HTTP`
   - URL: `localhost:8080`
4. Klik **Save**, lalu buka `https://presensiku.biz.id`. Halaman "Kode sekolah" harus muncul.

> Sekolah baru **tidak perlu** diatur lagi di Cloudflare.

## 5. Tambah sekolah
```bash
presensi-sekolah tambah smpn1 --nama "SMP Negeri 1" --hari 365 --maks-siswa 1000 --zona Asia/Jakarta
```
- Alamat sekolah: `https://presensiku.biz.id/smpn1`.
- Login awal `admin` / `admin123`; password wajib diganti saat login pertama.
- `--hari 14` dapat dipakai untuk masa uji coba.
- Kode boleh berisi huruf kecil, angka, dan tanda `-`.

## 6. Pindahkan sekolah yang sudah memakai server sendiri
1. Di aplikasi lama: **Pengaturan → Backup** → unduh ZIP.
2. Dari laptop (PowerShell), kirim ZIP ke VPS:
   ```
   scp C:\Users\NAMA\Downloads\presensi-backup-xxx.zip root@IP-VPS:/root/
   ```
3. Di VPS:
   ```bash
   presensi-sekolah pindah smpn1 /root/presensi-backup-xxx.zip --nama "SMP Negeri 1" --hari 365
   ```
4. Alamat baru adalah `https://presensiku.biz.id/smpn1`. Ikuti langkah berikut:
   - Setel ulang **alamat server** di tiap ESP32 (portal Wi-Fi perangkat):
     `https://presensiku.biz.id/smpn1`.
   - Bagikan alamat baru ke guru dan orang tua; slip PIN yang dicetak ulang otomatis memakai alamat
     baru.
   - Hapus tunnel lama di komputer sekolah.

## 7. Mengelola langganan
| Perintah | Fungsi |
|---|---|
| `presensi-sekolah daftar` | Semua sekolah, status, tanggal berakhir, layanan |
| `presensi-sekolah perpanjang smpn1 --hari 180` | Perpanjang (menyambung dari tanggal habis) |
| `presensi-sekolah perpanjang smpn1 --sampai 2027-06-30 --maks-siswa 1200` | Atur tanggal & batas siswa |
| `presensi-sekolah nonaktif smpn1` / `aktifkan smpn1` | Mode baca-saja / aktif kembali |
| `presensi-sekolah backup --semua` | Backup manual (otomatis tiap 03.00, simpan 14) |
| `presensi-sekolah status` | RAM, disk, layanan |
| `presensi-sekolah hapus smpn1 --ya` | Hapus sekolah (backup dibuat dulu) |

## 8. Memperbarui aplikasi
```bash
curl -fsSL https://raw.githubusercontent.com/saifularif00328-cmd/presensi/claude/aplikasi-sesuai-prd-bppvd6/deploy/install_vps.sh | bash
systemctl restart 'presensi@*'
```

## 9. Backup ke luar VPS (disarankan)
```bash
apt install -y rclone && rclone config        # tambahkan remote "gdrive" (Google Drive)
echo '30 3 * * * root rclone copy /srv/presensi/_backup gdrive:presensi-backup' > /etc/cron.d/presensi-rclone
```

## Bila ada masalah
| Gejala | Periksa |
|---|---|
| `presensiku.biz.id` error 1033 / 502 | `systemctl status cloudflared` · `systemctl status nginx` |
| "Server sedang dimulai ulang" | `systemctl status presensi@smpn1` · `journalctl -u presensi@smpn1 -n 50` |
| `/kode` 404 | Kode salah, atau sekolah belum ditambah (`presensi-sekolah daftar`) |
