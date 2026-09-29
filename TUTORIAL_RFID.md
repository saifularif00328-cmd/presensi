# Tutorial Kartu RFID

Absen harian dengan **tap kartu** (MIFARE 13,56 MHz). Kartu yang sama tetap bisa discan QR-nya
sebagai cadangan. Dua cara membaca kartu:

| Alat | Tempat | Cara kerja |
|---|---|---|
| **Reader RFID USB** 13,56 MHz (Rp100–250 rb) | Meja piket / TU | Dicolok ke PC/laptop, bekerja seperti keyboard. Buka menu **Scan Kartu** lalu tap. |
| **Perangkat ESP32 + RC522** (±Rp150–200 rb) | Gerbang, musala | Mandiri tanpa PC, ada LCD & buzzer. Rakitan & firmware: [`firmware/README.md`](firmware/README.md). |

> Beli kartu **MIFARE Classic 1K 13,56 MHz** (PVC putih bisa dicetak). Kartu **125 kHz (EM4100)
> tidak terbaca** oleh RC522.

## 1. Cetak kartu
Menu **Cetak Kartu** → pilih template → **mode printer kartu PVC** → cetak di kartu RFID polos
(desain + QR tercetak, chip RFID ada di dalam kartu).

## 2. Daftarkan kartu ke siswa
**Cara cepat (reader USB):** menu **Kartu RFID** → pilih kelas → nama siswa pertama otomatis
terpilih → tap kartunya → tersimpan dan pindah ke siswa berikutnya. Ulangi sampai semua kelas.

**Lewat perangkat gerbang:** tap kartu baru di ESP32 (LCD: *Kartu RFID belum terdaftar*) →
di menu **Kartu RFID**, bagian *Kartu baru yang di-tap*, pilih siswa pemiliknya → **Pasang**.

## 3. Kartu hilang / rusak
Menu **Kartu RFID** → cari siswa → **Blokir** (kartu lama ditolak bila di-tap:
*Kartu diblokir — milik …*) → daftarkan kartu pengganti seperti langkah 2.
**Lepas** dipakai bila kartu hanya ingin dipindah ke siswa lain.

## 4. Perangkat gerbang
1. **Sistem → Perangkat RFID → Tambah perangkat**: nama (mis. *Gerbang Utama*) dan mode:
   - *Otomatis* — tap pertama = masuk, tap setelah jam pulang = pulang,
   - *Masuk saja* / *Pulang saja* — untuk gerbang terpisah,
   - *Tap ibadah* — di musala (jadwal yang sedang berlangsung dipilih otomatis).
2. Klik **Isian** → isikan *alamat server*, *kode perangkat*, dan *rahasia* ke perangkat
   (lihat [`firmware/README.md`](firmware/README.md) bagian *Menyetel perangkat*).
3. Titik hijau di daftar = perangkat online. Versi & waktu terakhir terhubung juga tampil.

## 5. Saat internet / server terputus
- **ESP32**: LCD *TERSIMPAN Offline (n)*; tap dikirim otomatis dengan **jam tap asli** saat koneksi
  kembali (sampai 1.000 tap).
- **Halaman Scan Kartu** (reader USB): muncul *n scan tersimpan offline*; dikirim otomatis. Jangan
  tutup/muat ulang browser sampai angka itu hilang.
- Notifikasi WA untuk tap tertunda dikirim bila masih di hari yang sama.

## 6. Uji tanpa alat
`python tools/simulasi_perangkat.py --server <alamat> --kode <kode> --rahasia <rahasia> tap A1B2C3D4`
