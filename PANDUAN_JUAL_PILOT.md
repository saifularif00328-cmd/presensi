# Panduan Jual & Pilot (untuk vendor)

Dokumen ini untuk **Anda sebagai penyedia layanan**. Isinya urutan dari menyiapkan server,
menjalankan uji coba (pilot) di 1–2 sekolah, sampai sekolah berlangganan.

Halaman publik yang sudah tersedia:

| Halaman | Isi |
|---|---|
| `https://presensiku.biz.id/` | Beranda + pendaftaran demo gratis |
| `/harga` | Paket & harga (diatur dari panel vendor), kalkulator per jumlah siswa, FAQ, tombol "Minta penawaran" |
| `/panduan` | Langkah memulai untuk admin sekolah |
| `/syarat` | Syarat & ketentuan layanan |
| `/privasi` | Kebijakan privasi (termasuk absen HP & data wajah) |

> **Penting:** isi `/syarat` dan `/privasi` adalah draf yang wajar untuk layanan sejenis,
> **bukan nasihat hukum**. Sebaiknya dibaca ulang dan disesuaikan sebelum ditawarkan luas,
> terutama soal pengembalian dana, batas tanggung jawab, dan data wajah.

---

## A. Menyiapkan server (sekali, ±30 menit)

- [ ] **Perbarui VPS** ke versi terbaru:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/saifularif00328-cmd/presensi/claude/aplikasi-sesuai-prd-bppvd6/deploy/install_vps.sh | bash
  systemctl restart 'presensi@*'
  ```
- [ ] `systemctl status presensi-wajah` menunjukkan **active (running)** (mesin wajah).
- [ ] **Backup Google Drive**: jalankan `presensi-sekolah backup-drive --pasang`. Tulis **dua sandi**
      yang muncul di kertas dan simpan di tempat aman.
- [ ] Jalankan `presensi-sekolah uji-pulih`, hasilnya harus sukses.
- [ ] **UptimeRobot**: pantau `https://presensiku.biz.id/sehat` tiap 5 menit, dengan pemberitahuan
      ke email/WA Anda.
- [ ] **Presensiku Pos**: unggah installer terbaru dengan `presensi-sekolah pasang-pos` (file dari
      GitHub Actions).
- [ ] **Panel vendor** `/vendor` → **Pengaturan**:
  - nomor WA, lama demo, kuota demo;
  - **harga** per tahun / semester, jumlah siswa yang termasuk harga dasar, tambahan per 100
    siswa, dan biaya pemasangan.
  - Biarkan harga 0 bila ingin halaman Harga menampilkan "Minta penawaran".
- [ ] Buka `/harga`, `/panduan`, `/syarat` dari HP dan pastikan tampil benar.

### Menentukan harga (hasil riset Oktober 2026)

**Harga pasar** (dari halaman harga publik, dikumpulkan lewat pencarian web; bisa sudah berubah):

| Model | Kisaran | Setara sekolah 250 siswa / tahun |
|---|---|---|
| Per siswa per bulan (web + WA) | Rp3.000–5.000 / siswa / bulan | Rp9–15 juta |
| Paket bulanan per sekolah | Rp150.000–750.000 / bulan (makin mahal makin banyak siswa) | Rp1,8–9 juta |
| Paket tahunan per sekolah | ±Rp1,26–2,5 juta / tahun (paket terkecil, ±100 siswa) | Rp2,5 juta ke atas |
| Gratis | Ada yang gratis untuk ≤100 siswa | Rp0 (fitur terbatas) |
| Beli putus (skrip, pasang sendiri) | Rp350.000–1,2 juta sekali | Tanpa server, tanpa bantuan |

**Biaya Anda:**
- VPS S ±Rp60.000/bulan (±Rp720.000/tahun), cukup untuk ±5 sekolah.
- Naik ke paket yang lebih besar bila sekolah bertambah.

**Biaya WhatsApp ditanggung sekolah** langsung ke penyedia gateway.
- Contoh Fonnte: gratis 1.000 pesan/bulan (ada watermark), ±Rp66.000 untuk 10.000 pesan/bulan.
- Sekolah 150 siswa × 2 pesan × 22 hari ≈ 6.600 pesan/bulan.
- Sampaikan biaya ini sejak awal agar tidak mengejutkan.

**Rekomendasi harga perintis (launching, sekolah desa)**:

| Isian di Panel Vendor → Pengaturan | Nilai |
|---|---|
| Per tahun | **Rp900.000** |
| Termasuk s.d. siswa | **150** |
| Tambahan per 100 siswa / tahun | **Rp150.000** |
| Per semester | **Rp500.000** |
| Pemasangan | **0** (gratis, online) |

Hasilnya:

| Jumlah siswa | Per tahun | Setara per bulan |
|---|---|---|
| 100–150 | Rp900.000 | Rp75.000 |
| 250 | Rp1.050.000 | Rp87.500 |
| 400 | Rp1.350.000 | Rp112.500 |
| 600 | Rp1.650.000 | Rp137.500 |

Alasannya:
- **Mudah di-ACC kepala sekolah.** Setara **Rp75–140 ribu per bulan**, kira-kira seharga paket
  internet bulanan, dan dibayar sekali setahun.
- **Tidak memicu perang harga.** Anda tidak melawan yang gratis atau beli putus. Anda menjual
  layanan lengkap (server, backup, bantuan WA) dengan **satu harga transparan**, dan harga ini
  tidak perlu diturunkan lagi. Yang membedakan Anda adalah pelayanan untuk sekolah desa:
  - tetap jalan saat internet putus;
  - alat scan murah;
  - bantuan pemasangan.
- **Tetap untung.** 5 sekolah × ±Rp1 juta ≈ Rp5 juta/tahun, sementara biaya server ±Rp720 ribu.
  Biaya terbesar Anda adalah waktu membantu sekolah, jadi jangan menggratiskan kunjungan ke
  lokasi. Transport ke sekolah dihitung terpisah sesuai jarak.

Strategi:
- Sebut ini **"harga perintis"** untuk ±20 sekolah pertama, **dikunci 2 tahun** bagi sekolah
  tersebut.
- Sekolah berikutnya bisa dikenakan harga normal, mis. Rp1.200.000 per tahun termasuk 150
  siswa.
- Lebih baik **memberi bonus** daripada memotong harga, misalnya:
  - 2 bulan gratis untuk pembayaran tahunan;
  - kartu QR siap cetak;
  - pelatihan operator.
- Jangan menyebut atau menjelekkan merek pesaing di materi promosi.

Isi lewat panel vendor, atau lewat VPS:
```bash
presensi-sekolah setel --harga-tahun 900000 --siswa-termasuk 150 --harga-per-100 150000 \
  --harga-semester 500000 --harga-pasang 0
```

### ⚠️ Sumber dana sekolah (Dana BOS) — wajib dicek
- Juknis BOSP **melarang sekolah menyewa aplikasi pendataan dan aplikasi PPDB daring**.
- Beberapa situs penjelas menafsirkannya lebih luas: aplikasi berbayar apa pun dari pihak luar
  Kementerian/Dinas tidak boleh dibayar dari BOS.
- Saya belum bisa membuka teks resmi Permendikdasmen terbaru untuk memastikan.
- Aturan juga bisa ditafsirkan berbeda oleh tiap Dinas atau inspektorat.

Karena itu:
- **Jangan pernah menjanjikan "bisa dibayar pakai dana BOS".**
- Sasaran awal paling aman adalah sekolah yang dananya dari **yayasan / dana sendiri**:
  - madrasah swasta,
  - pesantren,
  - SD/SMP/SMK swasta.
- Untuk sekolah negeri, minta kepala sekolah **mengonfirmasi ke Dinas Pendidikan / pengawas**
  sebelum membayar. Sumber dana sepenuhnya keputusan sekolah.

### ⚠️ Legalitas usaha Anda
- Layanan aplikasi yang dipakai pengguna di Indonesia **wajib terdaftar sebagai PSE Lingkup Privat**
  di Komdigi melalui OSS. Untuk itu Anda perlu **NIB** dulu.
- PSE wajib yang tidak terdaftar bisa langsung **diblokir** tanpa peringatan bertahap.
- Daftarkan sebelum menjual luas. Proses OSS bisa dilakukan sendiri.
- Bila ragu dengan klasifikasi usahanya, tanyakan ke petugas OSS / Mal Pelayanan Publik
  setempat.

### Privasi (UU PDP) — sudah disesuaikan di /privasi dan /syarat
- Sekolah = **Pengendali** data, Anda = **Prosesor** data.
- Data anak dan data biometrik (wajah) termasuk data yang dilindungi khusus. Data wajah butuh
  persetujuan orang tua; aplikasi sudah mencatatnya.
- Backup di Google Drive dan jaringan Cloudflare bisa berada di luar Indonesia. Keduanya
  disebutkan terbuka, dan backup dienkripsi sebelum dikirim.
- Janji pemberitahuan kebocoran data ke sekolah: paling lambat 3 × 24 jam.

---

## B. Memilih sekolah pilot

- [ ] Pilih 1–2 sekolah, idealnya ≤ 500 siswa, dengan **operator/TU yang responsif** dan kepala
      sekolah yang mendukung.
- [ ] Sepakati **masa pilot** (mis. 4 minggu) dan **ukuran keberhasilan** di awal (lihat bagian F).
- [ ] Buat sekolahnya dari panel vendor → **Tambah sekolah**. Atur masa aktif selama pilot +
      2 minggu.
- [ ] Sepakati siapa yang menyediakan alat: reader/scanner, PC gerbang, nomor WA sekolah.

## C. H-7 sampai H-1 (persiapan bersama operator)

Ikuti `/panduan` bersama operator, lewat panggilan video atau datang langsung:

- [ ] Password admin sudah diganti. Akun piket & BK sudah dibuat.
- [ ] Aturan jam, kalender libur, dan tahun ajaran sudah diisi.
- [ ] Data siswa diimpor dari Excel. Cek ulang **nomor WA orang tua** (yang salah tidak menerima
      pesan).
- [ ] Kartu dicetak (QR) atau didaftarkan (RFID). Uji 10 kartu acak.
- [ ] Alat di gerbang terpasang. Bila memakai 2+ scanner, Presensiku Pos terpasang dan Layar
      Gerbang tampil.
- [ ] WhatsApp gateway terhubung. Kirim pesan uji ke 2–3 orang tua yang bersedia.
- [ ] Surat edaran ke orang tua: alamat portal, cara masuk, dan nomor WA sekolah.
- [ ] Bila absen HP/wajah dipakai: titik lokasi sudah diisi, dan formulir persetujuan wajah sudah
      dibagikan.

## D. Hari pertama

- [ ] Siaga sejak 30 menit sebelum jam masuk, di lokasi atau online.
- [ ] Pantau **Monitor Live** dan **panel vendor → kesehatan server**.
- [ ] Catat setiap kendala:
  - kartu tidak terbaca,
  - antrean panjang,
  - nama salah,
  - WA tidak terkirim.
- [ ] Setelah jam masuk:
  - cek rekap harian bersama operator;
  - tandai siswa yang belum punya kartu;
  - siswa yang lupa kartu dicatat di **Presensi Manual**.

## E. Minggu 1–4

- [ ] **Harian (5 menit)**:
  - tidak ada alarm WA dari server;
  - backup semalam sukses (panel vendor);
  - bila absen HP aktif, cek **Log Absen HP** bagian "perlu diperiksa".
- [ ] **Akhir minggu 1**: rapat singkat dengan operator. Perbaiki data, kartu rusak, dan posisi
      scanner.
- [ ] **Minggu 2–3**: aktifkan fitur tambahan satu per satu bila diinginkan:
  - absen HP untuk 1 kelas;
  - mode wajah **Tandai**.
- [ ] Kumpulkan masukan dari guru piket, BK, dan 3–5 orang tua.

## F. Evaluasi (akhir pilot)

| Ukuran | Target wajar |
|---|---|
| Tap/scan berhasil pada percobaan pertama | ≥ 95% |
| Waktu rata-rata per siswa di gerbang | ≤ 3 detik |
| WA orang tua terkirim | ≥ 95% (sisanya biasanya nomor salah) |
| Server tidak bisa diakses di jam sekolah | 0 kejadian / sangat jarang |
| Operator bisa mengelola sendiri tanpa bantuan harian | Ya |

Angka 1–3 bisa dilihat di Monitor/Rekap, Log Notifikasi, dan UptimeRobot. Bila target tercapai,
ajukan penawaran berlangganan.

## G. Menjadi pelanggan

1. Kirim penawaran: tautan `/harga?siswa=<jumlah>` atau dokumen resmi + nomor rekening.
2. Setelah pembayaran masuk, buka panel vendor → sekolah → **Perpanjang**. Isi lama langganan +
   **nominal** (tercatat di riwayat pembayaran), lalu kirim kuitansi.
3. Minta izin memakai nama sekolah / testimoni untuk promosi (tertulis).
4. Pengingat perpanjangan otomatis muncul di aplikasi sekolah menjelang berakhir. Anda juga
   melihat sekolah yang **Akan habis** di panel vendor, dengan tombol "Tawarkan perpanjangan" via WA.

## Template pesan WhatsApp

**Setelah demo didaftarkan**
> Halo Bapak/Ibu {nama}, terima kasih sudah mencoba Presensiku untuk {sekolah}. Aplikasi sudah
> aktif di {alamat}. Panduan memulai: https://presensiku.biz.id/panduan. Kalau berkenan, kami bisa
> bantu lewat video call 30 menit untuk memasang data & kartu pertama. Kapan waktu yang cocok?

**Menjelang demo berakhir**
> Halo Bapak/Ibu {nama}, masa demo {sekolah} berakhir {tanggal}. Bagaimana pengalaman sekolah
> sejauh ini? Bila ingin dilanjutkan, rincian harga ada di https://presensiku.biz.id/harga. Data
> yang sudah diisi tetap tersimpan, jadi tidak perlu mengulang.

**Penawaran**
> Berikut penawaran untuk {sekolah} (±{jumlah} siswa): {harga}/tahun, semua fitur, termasuk
> pembaruan, backup harian, dan bantuan WhatsApp. Pembayaran transfer ke {rekening}; kuitansi kami
> kirimkan setelah pembayaran.
