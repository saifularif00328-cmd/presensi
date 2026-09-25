# Presensi Siswa Digital

Aplikasi absensi sekolah berbasis **QR code** yang berjalan sebagai server lokal
(offline-first) dan diakses lewat browser oleh admin, guru piket, dan guru BK.
Dibuat sesuai PRD *Presensi Siswa Digital v1.0*.

## Fitur

| Modul | Isi |
|---|---|
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

Butuh Python 3.10+.

```bash
pip install -r requirements.txt
python run.py            # tambahkan --open untuk otomatis membuka browser
```

Buka `http://localhost:5000`. **Login awal: `admin` / `admin123`** (segera ganti di menu Akun).
HP di WiFi yang sama bisa membuka `http://<IP-komputer>:5000`; alamatnya tercetak di konsol saat start.

Semua data (database SQLite, foto, kunci enkripsi, backup) tersimpan di folder `data/`.
Lokasinya bisa diubah dengan env `PRESENSI_DATA_DIR`. Port diatur dengan env `PRESENSI_PORT`.
Database memakai mode WAL + `synchronous=FULL` supaya tahan mati listrik, dan backup
otomatis dibuat setiap hari (14 terakhir disimpan).

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

## Lisensi (Basic / Pro / Enterprise)

| Tier | Fitur |
|---|---|
| Basic (tanpa kode) | Presensi & QR, data master, rekap presensi, cetak kartu — hanya akun admin yang bisa login |
| Pro | + Perizinan, Rekap Pelanggaran, Notifikasi WA, multi-user & role |
| Enterprise | + Modul Ibadah, Dashboard Multi-Cabang |

Lisensi ditandatangani digital (Ed25519) dan terikat ke **ID perangkat** + masa berlaku.
Aplikasi hanya membawa kunci publik, sehingga lisensi tidak bisa dipalsukan walaupun `.exe` dibongkar.

- **Vendor:** jalankan `python tools/vendor_init.py` sekali (membuat kunci privat & publik), lalu
  kelola lisensi lewat **server aktivasi** (`jalankan_server_lisensi.bat`) — panduan lengkap
  di [`license_server/README.md`](license_server/README.md), tutorial [ngrok](license_server/TUTORIAL_NGROK.md) (tanpa domain) dan [Cloudflare Tunnel](license_server/TUTORIAL_CLOUDFLARE.md) (domain sendiri).
  Kode offline juga bisa dibuat dengan `python tools/keygen.py --device <ID> --tier pro --hari 365`.
- **Sekolah:** menu **Lisensi** → *Aktivasi online* (kode aktivasi + alamat server) atau
  *Aktivasi offline* (tempel kode lisensi). Status dicek otomatis ke server saat online:
  pencabutan, perpanjangan, dan ganti tier diterima tanpa input ulang.

## Build `.exe` Windows

Di Windows, jalankan `build_exe.bat` (memakai PyInstaller + waitress).
Hasilnya ada di `dist\PresensiSiswa\PresensiSiswa.exe`, dan data tersimpan di `dist\PresensiSiswa\data\`.

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
