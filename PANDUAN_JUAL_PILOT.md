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

### Menentukan harga
Tulis biaya bulanan Anda: VPS, domain, waktu dukungan, dan cadangan bila naik ke VPS lebih
besar. Lalu tentukan berapa sekolah yang realistis Anda layani di tahun pertama.

**Harga tahunan per sekolah sebaiknya ≥ (biaya setahun ÷ jumlah sekolah) + nilai waktu dukungan
Anda.**

- Paket **semester** membantu sekolah yang anggarannya per semester.
- Harga **per 100 siswa** membuat sekolah kecil tetap terjangkau.
- Biaya **WhatsApp gateway** dibayar sekolah langsung ke penyedianya, jadi jangan dimasukkan ke
  harga Anda.

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
