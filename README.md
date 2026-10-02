# Presensi Siswa Digital

Aplikasi absensi sekolah dengan **kartu RFID + QR**, database **MySQL/MariaDB**, dan
**portal siswa & orang tua** yang bisa dibuka dari mana saja lewat **Cloudflare**.
Admin, guru piket, dan guru BK memakai browser; siswa tap kartu di reader USB atau perangkat
ESP32 di gerbang.

| Panduan | Isi |
|---|---|
| [`PANDUAN_PEMULA_VPS.md`](PANDUAN_PEMULA_VPS.md) | **Mulai di sini (pemula):** dari VPS baru sampai sekolah pertama online, langkah demi langkah |
| [`TUTORIAL_VPS.md`](TUTORIAL_VPS.md) | **Jalur utama:** semua sekolah di satu VPS, alamat `https://presensiku.biz.id/<kode>` — sekolah tidak memasang apa pun |
| [`TUTORIAL_SERVER_SEKOLAH.md`](TUTORIAL_SERVER_SEKOLAH.md) | Alternatif: installer Windows di komputer sekolah + Cloudflare Tunnel |
| [`TUTORIAL_MULTI_SCANNER.md`](TUTORIAL_MULTI_SCANNER.md) | Banyak scanner (USB/COM/nirkabel) di satu PC dengan **Presensiku Pos** + Layar Gerbang |
| [`TUTORIAL_ABSEN_HP.md`](TUTORIAL_ABSEN_HP.md) | Pilih metode absen (RFID / QR / HP) dan **absen dari HP siswa** berbasis lokasi + foto bukti + **pencocokan wajah** |
| [`TUTORIAL_RFID.md`](TUTORIAL_RFID.md) · [`firmware/README.md`](firmware/README.md) | Kartu RFID, reader USB, perakitan ESP32 |
| [`TUTORIAL_PORTAL.md`](TUTORIAL_PORTAL.md) | Panduan portal untuk orang tua & siswa |
| [`TUTORIAL_MULTICABANG.md`](TUTORIAL_MULTICABANG.md) | Dashboard beberapa sekolah/cabang |

## Fitur

| Modul | Isi |
|---|---|
| **Kartu RFID** | Tap kartu MIFARE 13,56 MHz lewat reader USB atau perangkat ESP32 + RC522 (LCD, buzzer, antrean offline); daftar kartu massal per kelas, blokir kartu hilang; menu Perangkat RFID (HMAC, anti-replay) |
| **Portal siswa & orang tua** | `/portal`: orang tua masuk dengan nomor WA + kode OTP, siswa dengan NIS + PIN; status hari ini, kalender kehadiran, rekap semester, kedisiplinan, ibadah, pengumuman; orang tua mengajukan izin/sakit + foto surat; bisa dipasang seperti aplikasi (PWA) |
| **Data Master** | Kelas (jenjang, wali kelas), Siswa (foto, NIS/NISN, WA ayah/ibu/wali, QR otomatis, import Excel/CSV), Guru/Staf, Tahun Ajaran & Semester (arsip) |
| **Presensi** | Scan QR (masuk/pulang, mode otomatis), Monitor Live (auto-refresh, filter kelas), Presensi Manual, Rekap (H/I/S/A/D + telat, ekspor Excel/PDF), SMT (rekap semester + % kehadiran) |
| **Perizinan** | Izin & Sakit (setujui/tolak, otomatis tercatat di presensi), Izin Keluar (jam keluar/kembali), Pengajuan Cetak Ulang Kartu |
| **Ibadah** (opsional) | Daftar jadwal, Tap Ibadah (kartu QR yang sama), Rekap harian & semester |
| **Kedisiplinan** | Tata Tertib, Rekap Pelanggaran (jenis, poin, tindak lanjut), Aturan Jam (per default/jenjang/kelas) |
| **Sistem** | Kalender Libur, Akses User (Admin, Guru Piket, Guru BK), Info/pengumuman, Pengaturan, Backup, Lisensi, Dashboard Multi-Cabang |
| **Notifikasi WA** | Fonnte API, token terenkripsi, template dengan `{nama_siswa}` `{kelas}` `{jam}` `{status}`, toggle per jenis, antrian offline, log & kirim ulang, info kuota |
| **Kartu pelajar** | Sisi depan: 5 template (Modern, Klasik, Minimal, Elegan, Gradien) × orientasi horizontal/vertikal × 8 pilihan warna, logo sekolah, pratinjau langsung; PDF siap cetak A4 (horizontal 2×5, vertikal 3×3) ukuran ID card 85,6×54 mm, satuan atau per kelas. Sisi belakang (tema mengikuti template): Syarat & Ketentuan, Visi & Misi, Profil Sekolah, Kontak & Kartu Ditemukan, atau Jam Sekolah & Tata Tertib, plus tanda tangan kepala sekolah. Cetak A4 bolak-balik (halaman belakang otomatis dicerminkan) atau printer kartu PVC |

### Aturan presensi
- **Absen masuk** → `Hadir` / `Telat` (setelah *batas telat*).
- **Absen pulang** → `Tepat Waktu` / `Pulang Cepat` (sebelum *jam pulang*).
- Masuk dan pulang hanya bisa **1× per hari**. Kalau kartu di-scan ulang, muncul peringatan berisi jam absen sebelumnya.
- Mode **Otomatis**: scan pertama dicatat sebagai masuk. Scan berikutnya dicatat sebagai pulang, tetapi hanya setelah jam *mulai absen pulang*.
- Setelah **jam tutup**:
  - siswa yang sudah masuk tapi belum absen pulang ditandai `Belum Pulang`;
  - siswa yang tidak tercatat sama sekali ditandai **Alpha**, dan orang tuanya menerima notifikasi WA.
- Tanggal di **Kalender Libur** dan hari di luar hari sekolah dilewati otomatis.
- Izin/Sakit/Dispensasi yang disetujui mengisi presensi dengan I/S/D. Kalau siswa itu ternyata datang dan scan, statusnya berubah jadi Hadir.

### Keamanan QR
QR hanya berisi `PSD1.<ID unik>.<checksum HMAC>`, tanpa data pribadi. Checksum memakai
secret per instalasi, jadi QR hasil menebak atau memalsukan ID akan ditolak. Tombol
**Ganti QR** (atau penyelesaian pengajuan kartu hilang) membuat kartu lama tidak berlaku.

## Menjalankan

Butuh Python 3.10+ dan server **MySQL 8 / MariaDB 10.6+**.

1. Buat user database (sekali), mis. di MariaDB:
   ```sql
   CREATE USER 'presensi'@'localhost' IDENTIFIED BY 'passwordkuat';
   GRANT ALL ON presensi.* TO 'presensi'@'localhost';
   ```
2. Isi `data/config.ini`:
   ```ini
   [database]
   host = 127.0.0.1
   port = 3306
   user = presensi
   password = passwordkuat
   database = presensi
   ```
   (atau env `PRESENSI_DB_URL=mysql://presensi:passwordkuat@127.0.0.1:3306/presensi`).
   Database & tabel dibuat otomatis saat aplikasi pertama kali jalan.
3. Jalankan:
   ```bash
   pip install -r requirements.txt
   python run.py            # tambahkan --open untuk otomatis membuka browser
   ```

Buka `http://localhost:5000`. **Login awal: `admin` / `admin123`** (segera ganti di menu Akun).
HP di WiFi yang sama bisa membuka `http://<IP-komputer>:5000`; alamatnya tercetak di konsol saat start.

Foto, kunci enkripsi, dan backup tersimpan di folder `data/` (ubah dengan env `PRESENSI_DATA_DIR`).
Port diatur dengan env `PRESENSI_PORT`. Zona waktu sekolah (WIB/WITA/WIT) diatur di Pengaturan.
Backup harian otomatis berupa ZIP (database + foto) di `data/backup/` (14 terakhir disimpan);
menu **Backup** mengunduh ZIP yang sama.

**Pindah dari versi lama (SQLite `data/presensi.db`):**
`python tools/migrasi_sqlite_ke_mysql.py` — seluruh data dipindah ke MySQL.

### Metode scan
1. **Scanner QR USB (HID)**: buka menu *Scan QR*. Kotak input selalu fokus, jadi scanner tinggal ditembakkan ke kartu.
2. **Kamera HP / webcam lewat browser**: tombol *Buka Kamera* (html5-qrcode sudah dibundel lokal, tetap jalan offline).
   Browser HP hanya mengizinkan kamera di **HTTPS atau localhost**. Kalau HP membuka lewat `http://192.168.x.x`, pilih salah satu:
   - Chrome Android: buka `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, tambahkan `http://<IP>:5000`, lalu restart Chrome; atau
   - jalankan server di balik reverse proxy HTTPS lokal (mis. Caddy).
3. **Webcam PC di server (OpenCV + pyzbar)**: `pip install opencv-python pyzbar`, lalu tekan *Mulai* di kartu “Webcam PC” pada halaman Scan. Di Linux, pyzbar juga butuh `libzbar0`.

### Notifikasi WhatsApp (Fonnte)
Menu **Notifikasi WA** (butuh lisensi Pro): isi token dari fonnte.com, atur template dan jenis notifikasi yang aktif.
Pesan masuk antrian lebih dulu. Job latar belakang mengecek koneksi tiap 20 detik lalu mengirim.
Selama offline, status pesan tetap *Menunggu Koneksi*. Status berubah jadi *Terkirim* begitu online.
Pesan yang ditolak 3× berstatus *Gagal* dan bisa dikirim ulang dari **Log Notifikasi**.

## Langganan (satu paket, semua fitur)

| Status | Artinya |
|---|---|
| **Uji coba** | 14 hari sejak instalasi, tanpa kode lisensi |
| **Aktif** | Kode lisensi valid (masa berlaku + batas jumlah siswa opsional) |
| **Masa tenggang** | 7 hari setelah berakhir — semua masih berjalan, muncul peringatan |
| **Habis** | Mode baca-saja: data tetap bisa dilihat & diekspor, tetapi absen/perubahan data ditolak |

Pengingat tampil 14 dan 3 hari sebelum berakhir. Lisensi ditandatangani digital (Ed25519) dan
terikat ke **ID perangkat** + masa berlaku, sehingga tidak bisa dipalsukan walaupun `.exe` dibongkar.

- **Server sekolah (alternatif):** menu **Langganan & Lisensi** → *Aktivasi online* (kode aktivasi) atau
  *Aktivasi offline*. Vendor mengelola kode lewat server aktivasi
  ([`license_server/README.md`](license_server/README.md)) atau offline:
  `python tools/keygen.py --device <ID> --hari 365 --maks-siswa 1000`.
- **VPS (`presensiku.biz.id/<kode>`):** status diatur vendor dengan `presensi-sekolah perpanjang/nonaktif ...`
  (berkas `data/_vendor.json`, mode `PRESENSI_MODE=cloud`).

## Keamanan akses internet
- Halaman login dikunci sementara setelah 5× salah (per akun) / 20× (per IP); password awal wajib diganti.
- IP & HTTPS asli dibaca dari Cloudflare/Nginx hanya bila datang dari proxy lokal; cookie `Secure`
  otomatis saat HTTPS; header keamanan (HSTS, nosniff, frame).
- Portal: OTP WhatsApp sekali pakai (5 menit, maks 3 kiriman/15 menit, 5× salah), PIN siswa hash +
  kunci sementara; orang tua/siswa hanya bisa melihat data anak/dirinya sendiri.

## Dashboard Multi-Cabang

Menu **Sistem → Multi-Cabang** di server pusat menampilkan ringkasan presensi hari ini dari
beberapa sekolah/cabang (hanya angka, tanpa data pribadi siswa). Setiap cabang cukup membagikan
URL server + token API-nya. Panduan lengkap (satu jaringan, Tailscale, ngrok, Cloudflare):
[`TUTORIAL_MULTICABANG.md`](TUTORIAL_MULTICABANG.md).

## Build installer Windows

1. `build_exe.bat` → `dist\PresensiSiswa\` (PyInstaller + waitress).
2. `powershell -ExecutionPolicy Bypass -File installer\siapkan_bundel.ps1` (sekali: MariaDB, cloudflared, WinSW).
3. Compile `installer\presensi.iss` di Inno Setup → `installer\Output\PasangPresensi-*.exe`.
   Installer memasang MariaDB + aplikasi sebagai Windows Service, firewall, dan pengaturan anti-sleep
   (`installer\pasang.ps1`). Lihat [`TUTORIAL_SERVER_SEKOLAH.md`](TUTORIAL_SERVER_SEKOLAH.md).

## Struktur kode

```
app/
  __init__.py          # app factory, registrasi blueprint, scheduler
  schema.sql, db.py    # skema & akses SQLite
  auth.py              # login, role, CSRF, pembatasan fitur per tier
  license.py           # ID perangkat & validasi kode lisensi
  qr.py                # payload QR + checksum, gambar QR
  scheduler.py         # APScheduler: antrian WA, tutup harian, kuota, backup
  services/            # attendance (logika scan), notify (Fonnte), rekap, export, webcam
  blueprints/          # main, master_data, presensi, perizinan, ibadah, kedisiplinan, sistem, notifikasi
  templates/, static/  # UI: sidebar (laptop) / bottom nav (HP), font Inter + ikon Lucide lokal
tests/                 # pytest
tools/keygen.py        # generator kode lisensi (vendor)
tools/build_icons.py   # membangun sprite ikon app/static/icons.svg dari lucide-static
tools/build_card_previews.py  # membuat gambar contoh template kartu (app/static/img/kartu)
```

## Pengujian

```bash
pip install pytest
python -m pytest -q
```

## Rencana pengembangan

- **Presensi wajah (opsional per siswa)** — pengenalan wajah offline dengan OpenCV YuNet + SFace
  (lisensi Apache-2.0), yang disimpan hanya vektor wajah, wajib persetujuan orang tua (UU PDP).
  1. *Mode kios*: kamera di gerbang, hasil masuk ke alur presensi yang sama (telat, WA, monitor).
  2. *Mode HP siswa*: login NIS + PIN terikat 1 HP, pindai **QR dinamis** (berganti tiap 20 detik)
     di layar gerbang lewat WiFi sekolah + selfie diverifikasi wajah; perlu HTTPS lokal.
