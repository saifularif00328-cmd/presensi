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

## 2a. Amankan VPS (lakukan sekali, sebelum memasang aplikasi)
Gantilah login dengan password menjadi login dengan **kunci SSH**. Penebak password di internet
tidak bisa masuk walaupun mencoba jutaan kali.

> Bila terkunci: portal Rumahweb (clientzone) → layanan VPS → **Console/VNC** tetap bisa dipakai
> untuk masuk.

**1) Ganti password root & perbarui sistem** (di VPS):
```bash
passwd
apt update && apt upgrade -y
reboot
```
- `passwd`: buat password baru minimal 16 karakter dan simpan di password manager.
- Setelah `reboot`, tunggu 1 menit lalu `ssh root@IP-VPS` lagi.

**2) Buat kunci SSH di laptop** (PowerShell di laptop, **bukan** di VPS):
```powershell
ssh-keygen -t ed25519
```
Tekan Enter 3× (lokasi bawaan, tanpa passphrase), atau isi passphrase agar lebih aman.

**3) Kirim kunci publik ke VPS** (masih di PowerShell laptop, ganti IP):
```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@IP-VPS "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```
Masukkan password root sekali lagi. Setelah itu, `ssh root@IP-VPS` harus langsung masuk **tanpa
ditanya password**.

**4) Matikan login dengan password** (di VPS), **hanya setelah langkah 3 berhasil**:
```bash
cat > /etc/ssh/sshd_config.d/00-presensi.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl restart ssh
```
Jangan tutup jendela PowerShell yang sedang terhubung. Buka **jendela baru** dan coba
`ssh root@IP-VPS`:
- **Bisa masuk:** aman.
- **Gagal masuk:** di jendela lama, jalankan `rm /etc/ssh/sshd_config.d/00-presensi.conf && systemctl restart ssh`, lalu ulangi langkah 3.

> Simpan cadangan file `C:\Users\NAMA\.ssh\id_ed25519` (mis. di flashdisk). Tanpa file itu, masuk
> hanya bisa lewat Console Rumahweb. **Jangan pernah membagikan file tanpa `.pub` tersebut.**

**5) Sisanya otomatis oleh skrip pemasangan (langkah 3):**

| Pengaman | Fungsi | Cek |
|---|---|---|
| Firewall UFW | Hanya port SSH terbuka; web lewat Cloudflare Tunnel, bukan port terbuka | `ufw status` |
| Fail2ban | IP yang 5× gagal login SSH diblokir 1 jam | `fail2ban-client status sshd` |
| Update otomatis | Patch keamanan Ubuntu dipasang tiap hari | `cat /etc/apt/apt.conf.d/20auto-upgrades` |
| MariaDB | Hanya bisa diakses dari dalam VPS (127.0.0.1) | `ss -tlnp \| grep 3306` |
| Aplikasi | Tiap sekolah jalan sebagai user `presensi` (bukan root), database & password sendiri | `presensi-sekolah daftar` |

**6) Kebiasaan aman:**
- Di panel Cloudflare, aktifkan **SSL/TLS → Always Use HTTPS**.
- Aktifkan juga **Security → Bots → Bot Fight Mode**.
- Aktifkan **2FA** di akun Cloudflare, Rumahweb, DomaiNesia, dan GitHub.
- Login admin tiap sekolah memakai password kuat. Aplikasi sudah memaksa password awal diganti dan
  mengunci login setelah beberapa kali salah.
- Salin backup ke luar VPS (bagian 9).
- Bila tersedia, aktifkan **snapshot** di Rumahweb sebelum memperbarui aplikasi.

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
Dashboard Zero Trust meminta kartu/PayPal, jadi tunnel dibuat dari VPS:
```bash
cloudflared tunnel login                 # buka tautannya, pilih presensiku.biz.id, Authorize
bash /opt/presensi/deploy/tunnel_vps.sh  # buat tunnel "vps", DNS, layanan cloudflared
```
Buka `https://presensiku.biz.id`; halaman "Kode sekolah" harus tampil. Sekolah baru **tidak perlu**
diatur lagi di Cloudflare.

## 4a. Demo gratis dari halaman depan
`https://presensiku.biz.id` berisi formulir **Daftar demo gratis**. Pendaftar mengisi nama sekolah,
WA, kode alamat, dan password admin. Sekolah lalu **dibuat otomatis** (±30 detik): layanan
`presensi-daftar` menulis antrean, dan `presensi-antrean.path` (root) menjalankan
`presensi-sekolah proses-antrean`.

Atur sekali:
```bash
presensi-sekolah setel --wa 081234567890 --hari-demo 7 --maks-demo 5
# opsional: WA pemberitahuan tiap ada pendaftar baru (token Fonnte milik Anda)
presensi-sekolah setel --notif-token TOKEN_FONNTE
```
- **Demo berakhir:** aplikasi menjadi baca-saja dan admin melihat **popup "Perpanjang via
  WhatsApp"** berisi pesan siap kirim (nama sekolah, kode, jumlah siswa). Popup juga muncul 2 hari
  sebelum demo berakhir.
- **Setelah membayar:** `presensi-sekolah perpanjang <kode> --hari 365`.
- **14 hari setelah demo berakhir tanpa perpanjangan:** `rapikan` (cron harian) menghentikan
  layanannya agar RAM VPS tidak habis. Data tetap tersimpan, dan alamat sekolah menampilkan
  halaman "demo berakhir" + tombol WA. `perpanjang` menghidupkannya lagi.
- **Kuota:** `--maks-demo` membatasi jumlah demo aktif bersamaan; Paket S ±5. Data pendaftar bisa
  dilihat dengan `presensi-sekolah daftar` dan `presensi-sekolah info <kode>`.
- **Anti-spam:** kolom jebakan bot, batas 3 pendaftaran/IP/hari, dan 1 demo per nomor WA. Bila
  perlu, tambahkan Cloudflare Turnstile (gratis):
  `/etc/presensi/daftar.env` berisi `DAFTAR_TURNSTILE_SITE=...` dan `DAFTAR_TURNSTILE_SECRET=...`,
  lalu `systemctl restart presensi-daftar`.

## 4b. Panel pribadi vendor — https://presensiku.biz.id/vendor
Buat akun dengan `presensi-sekolah akun-vendor` (password + Google Authenticator; jalankan ulang
untuk mengganti akun / HP hilang).

Isi panel:

| Halaman | Isi |
|---|---|
| **Sekolah** | Semua sekolah dengan filter demo / berlangganan / habis ≤14 hari / habis; jumlah siswa, absen terakhir, kontak WA, RAM VPS |
| **Detail sekolah** | Perpanjang (1/3/6/12 bulan atau tanggal) + catat pembayaran, batas siswa, nonaktif/aktifkan, ubah kontak, tombol WA "tawarkan perpanjangan" & "kirim konfirmasi" |
| **+ Tambah** | Sekolah berlangganan baru (tanpa SSH) |
| **Pengaturan** | Nomor WA, nama merek, lama & kuota demo |

Keamanan:
- Login gagal 5× per IP (atau 20× total per jam) dikunci 15 menit.
- Cookie sesi hanya untuk `/vendor`, HttpOnly, Secure, SameSite=Strict, berlaku 8 jam; ada token
  CSRF.
- Panel tidak berjalan sebagai root: perubahan dikirim ke antrean yang dijalankan
  `presensi-sekolah proses-antrean`, hanya untuk aksi yang terdaftar.

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

## 9. Keamanan data: backup Google Drive, uji pulih, alarm
Berjalan otomatis setelah `install_vps.sh`:

| Jadwal | Pekerjaan |
|---|---|
| 03.00 tiap hari | Backup semua sekolah ke `/srv/presensi/_backup` (14 terakhir) → lalu ke Google Drive **terenkripsi** (30 hari) + `daftar-sekolah.json` |
| 04.00 tiap Minggu | **Uji pulih**: backup terbaru (dari Drive bila terpasang) dipulihkan ke database sementara, dicek, lalu dihapus |
| Tiap 10 menit | **Cek kesehatan**: disk, RAM, layanan, tiap sekolah, backup, Drive, uji pulih → `_kesehatan.json`, panel vendor, `/sehat`, WA ke Anda |

### Pasang Google Drive (sekali)
0. **Client ID Google sendiri** (client bersama rclone dihentikan selama 2026): di console.cloud.google.com buat project →
   aktifkan *Google Drive API* → *OAuth consent screen* (External; cukup App name + email, kolom homepage/domain kosongkan)
   → *Audience* → **Publish app** (agar izin tidak kedaluwarsa tiap 7 hari) → *Clients* → Create client → **Desktop app**.
   Simpan Client ID & secret bersama sandi backup. Pesan "Your app requires verification" boleh diabaikan — tidak perlu verifikasi.
1. Di VPS: `rclone config` → `n` (new) → nama `gdrive` → Storage `drive` → tempel client_id & client_secret → scope **`3`**
   (`drive.file`: hanya file buatan rclone — tidak butuh verifikasi Google) → service account Enter → advanced `n`
   → **Use web browser? `n`**. Muncul perintah `rclone authorize "drive" "eyJ..."`.
2. Di laptop Windows: unduh rclone (rclone.org/downloads → Windows AMD64), ekstrak, buka PowerShell di folder itu,
   jalankan `.\rclone.exe authorize "drive" "eyJ..."` (salin persis dari VPS) → pilih akun Google → bila muncul
   "Google belum memverifikasi aplikasi ini": **Lanjutan → Buka (tidak aman)** → **Allow**.
   Salin token yang muncul (antara `--->` dan `<---`) → tempel di VPS → team drive `n` → `y` → `q`.
3. `presensi-sekolah backup-drive --pasang` → **simpan sandi 1 & sandi 2** yang tampil (kertas / password manager).
   Tanpa kedua sandi ini backup di Drive tidak bisa dibuka.
4. Uji: `presensi-sekolah backup --semua` lalu `presensi-sekolah uji-pulih`.

### Alarm
- WA ke nomor vendor saat ada masalah kritis (pengingat tiap 6 jam, kabar saat normal): butuh
  `presensi-sekolah setel --notif-token TOKEN_FONNTE`.
- **UptimeRobot** (gratis, juga menangkap VPS mati total): uptimerobot.com → Add New Monitor → HTTP(s) →
  URL `https://presensiku.biz.id/sehat` → interval 5 menit → kontak email/aplikasi. `/sehat` menjawab 503 bila
  ada masalah kritis atau pemeriksaan berhenti.
- Manual: `presensi-sekolah cek-kesehatan`.

### Pemulihan bencana (VPS hilang / pindah VPS)
1. VPS baru → `install_vps.sh` → `cloudflared tunnel login` + `tunnel_vps.sh` (bagian 3–4).
2. `rclone config` (gdrive, seperti di atas) → `presensi-sekolah backup-drive --pasang --sandi <sandi 1> --sandi2 <sandi 2>`.
3. `presensi-sekolah ambil-drive` → berkas di `/srv/presensi/_pulih/` (+ `daftar-sekolah.json` berisi nama, tanggal
   langganan, kontak).
4. Tiap sekolah: `presensi-sekolah pindah <kode> /srv/presensi/_pulih/<kode>-<tanggal>.zip --nama "..." --sampai <tanggal>`.
5. `presensi-sekolah setel --wa ...` dan `presensi-sekolah akun-vendor`.

## Bila ada masalah
| Gejala | Periksa |
|---|---|
| `presensiku.biz.id` error 1033 / 502 | `systemctl status cloudflared` · `systemctl status nginx` |
| Alarm "Backup ke Google Drive gagal" | `presensi-sekolah backup-drive` (lihat pesan); token Drive kedaluwarsa → `rclone config reconnect gdrive:` |
| "Server sedang dimulai ulang" | `systemctl status presensi@smpn1` · `journalctl -u presensi@smpn1 -n 50` |
| `/kode` 404 | Kode salah, atau sekolah belum ditambah (`presensi-sekolah daftar`) |
