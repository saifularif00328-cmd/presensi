# Metode Absen & Absen dari HP Siswa

Sekolah memilih sendiri metode absen yang dipakai:

| Metode | Alat | Keterangan |
|---|---|---|
| **Kartu RFID** | reader USB, ESP32, Presensiku Pos | kartu ditempel di gerbang |
| **Scan QR** | kamera / scanner QR USB/COM, ESP32 + modul QR | kartu QR discan di gerbang |
| **Absen dari HP** | HP siswa (browser) | lokasi GPS harus di area sekolah/kegiatan + foto selfie |

Semua metode bisa aktif bersamaan. Metode yang dimatikan akan **ditolak** saat discan, dan
halaman *Scan Kartu* menampilkan keterangannya.

---

## 1. Mengatur metode (admin)

1. Masuk sebagai **admin**, lalu buka **Sistem → Metode Absen**.
2. Centang metode yang diizinkan.
3. **Absen HP berlaku untuk**:
   - *Semua siswa*, atau
   - *Kelas tertentu*. Centang kelasnya. Cocok untuk uji coba di 1–2 kelas dulu.
4. **Batas akurasi GPS**: bawaan 100 m.
   - GPS yang lebih buruk dari batas ini ditolak.
   - Akurasi yang lebih buruk dari separuh batas ditandai "perlu diperiksa".
5. **Simpan foto bukti**: bawaan 30 hari. Setelah itu foto dihapus otomatis tiap malam, tetapi
   catatan absennya tetap ada.
6. Klik **Simpan**.

## 2. Menentukan lokasi absen

Absen HP hanya diterima bila HP siswa berada **di dalam radius** salah satu lokasi.

### Lokasi sekolah (selalu berlaku)
1. Di bagian **Tambah lokasi**, tentukan titiknya dengan salah satu cara:
   - klik titik gerbang/lapangan di peta, **atau**
   - berdiri di sekolah lalu tekan **Pakai lokasi saya**.
2. Isi **Nama** (mis. "Gedung Sekolah") dan **Radius**.
   - 50–150 m biasanya cukup.
   - GPS di dalam gedung bisa meleset 20–50 m, jadi jangan terlalu kecil.
3. **Simpan lokasi**. Sekolah yang punya beberapa gedung bisa menambah beberapa lokasi.

### Lokasi kegiatan (PKL, kemah, lomba, kunjungan)
1. Pilih **Jenis: Kegiatan**.
2. Isi **tanggal mulai–selesai**. Di luar tanggal itu lokasi tidak berlaku.
3. Pilih **kelas** dan/atau tulis **NIS siswa** peserta (pisahkan dengan koma).
   - Bila keduanya dikosongkan, lokasi berlaku untuk semua siswa.
4. Siswa sasaran lokasi kegiatan **selalu boleh** absen HP di lokasi itu, walaupun kelasnya tidak
   termasuk cakupan absen HP.

## 3. Cara siswa absen dari HP

Siswa masuk ke portal dengan **NIS + PIN** (lihat [TUTORIAL_PORTAL.md](TUTORIAL_PORTAL.md)). Lalu:

1. Tekan tombol **Absen dari HP** di halaman portal.
2. Tekan **Mulai absen**, lalu pilih **Izinkan** saat diminta akses **lokasi** dan **kamera**.
3. Tunggu sampai lokasi terbaca (beberapa detik). Usahakan GPS menyala dan berada di tempat
   terbuka.
4. Hadapkan wajah ke kamera, lalu tekan **Ambil foto & absen**.
5. Hasil langsung muncul:
   - **masuk/pulang berhasil**, atau
   - **ditolak** beserta alasannya, misalnya di luar area, GPS kurang akurat, atau sesi
     kedaluwarsa.

Absen masuk/pulang mengikuti jam yang sama dengan scan kartu: status telat/pulang cepat dan WA ke
orang tua dikirim seperti biasa. Orang tua **tidak bisa** absen atas nama anaknya.

> **Satu siswa = satu HP.** HP yang dipakai pertama kali langsung terikat ke akun siswa itu. HP
> tersebut tidak bisa dipakai siswa lain, jadi tidak ada titip absen. Bila siswa ganti HP atau
> data browser terhapus, admin menekan **Reset** di tabel *HP terdaftar*
> (Sistem → Metode Absen).

## 4. Memeriksa absen HP (piket / BK / admin)

Buka **Presensi → Log Absen HP**. Halaman ini menampilkan:

- foto bukti, jam, jarak ke lokasi, akurasi GPS, dan tautan **peta**;
- semua percobaan yang **ditolak** beserta alasannya;
- tanda **⚠ Perlu diperiksa** bila:
  - GPS kurang akurat,
  - siswa berada di tepi area,
  - HP baru didaftarkan, atau
  - posisi GPS sudah lama (> 60 detik).

Tombol yang tersedia:

- **Sudah dicek**: hilangkan tanda periksa.
- **Batalkan**: hapus absen tersebut, misalnya bila foto bukan siswa yang bersangkutan.
  - Absen *pulang* dibatalkan lebih dulu sebelum absen *masuk*.
  - Pembatalan tercatat di log scan.

## 5. Keamanan & privasi

- Jarak dihitung **di server**, bukan di HP.
- Setiap absen memakai token sekali pakai yang berlaku 2 menit.
- Aplikasi "GPS palsu" tidak bisa dicegah 100% dari browser. Karena itu ada **foto bukti**, tanda
  periksa, dan tinjauan petugas. Pencocokan wajah otomatis menyusul di tahap berikutnya.
- Foto hanya bisa dilihat petugas sekolah dan dihapus otomatis sesuai pengaturan.
- Sampaikan ke orang tua/siswa bahwa lokasi & foto dipakai **hanya** sebagai bukti kehadiran
  (lihat halaman `/privasi`).
- Absen HP membutuhkan alamat **HTTPS** karena browser hanya mengizinkan GPS & kamera di HTTPS.
  Alamat `https://presensiku.biz.id/<kode>` sudah memenuhi syarat ini.

## Masalah umum

| Masalah | Solusi |
|---|---|
| "Izin lokasi ditolak" | Pengaturan browser → Situs → Lokasi → izinkan untuk presensiku.biz.id |
| "Sinyal GPS kurang akurat" | Nyalakan GPS mode akurasi tinggi, keluar ke tempat terbuka, tunggu 10 detik |
| "Anda di luar area absen" padahal di sekolah | Perbesar radius atau tambah titik lokasi di gedung tersebut |
| "Akun Anda terdaftar di HP lain" | Admin menekan **Reset** HP siswa di Sistem → Metode Absen |
| Kamera tidak muncul | Tombol berganti menjadi "Ambil foto dengan kamera HP", lalu pakai kamera bawaan |
| Peta admin tidak tampil | Butuh internet. Koordinat tetap bisa diisi manual (dari Google Maps: tekan lama → salin angka) |
