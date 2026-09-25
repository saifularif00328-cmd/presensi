# Tutorial: Server Lisensi Online dengan ngrok (dari nol, tanpa domain)

Hasil akhir: server lisensi di laptop Anda bisa dihubungi sekolah lewat alamat tetap gratis
seperti **`https://nama-acak.ngrok-free.app`**. Tanpa membeli domain, tanpa setting router.

```
Aplikasi sekolah ──internet──▶ ngrok ──tunnel──▶ laptop Anda (API :8500)
                                                  └ halaman admin :8501 (hanya laptop Anda)
```

Perkiraan waktu: ±20 menit.

---

## Langkah 1 — Daftar akun ngrok

1. Buka **https://dashboard.ngrok.com/signup**.
2. Daftar dengan email (atau tombol Google / GitHub), lalu verifikasi email.
3. Jika ditanya tujuan pemakaian, pilih apa saja yang sesuai (mis. *Development*).

## Langkah 2 — Unduh ngrok

Cara termudah (tanpa mengubah pengaturan Windows):

1. Buka **https://ngrok.com/download** → pilih **Windows** → unduh file ZIP.
2. Ekstrak ZIP → muncul file **`ngrok.exe`**.
3. **Salin `ngrok.exe` ke folder aplikasi Presensi** (folder yang sama dengan
   `jalankan_server_lisensi.bat`).

> Windows Defender/antivirus kadang bertanya saat pertama kali menjalankan ngrok → pilih
> *Allow / Izinkan*. ngrok adalah program resmi.

## Langkah 3 — Hubungkan ngrok ke akun Anda (authtoken)

1. Di dashboard ngrok buka menu **Your Authtoken** (bagian *Getting Started*).
2. Klik **Copy** pada token.
3. Buka Command Prompt **di folder aplikasi** (klik address bar File Explorer → ketik `cmd` →
   Enter), lalu jalankan (tempel token dengan klik kanan):
   ```bat
   ngrok config add-authtoken TEMPEL_TOKEN_ANDA_DI_SINI
   ```
   Berhasil bila muncul `Authtoken saved to configuration file`.

## Langkah 4 — Ambil domain statis gratis

Akun gratis ngrok mendapat **1 domain tetap** (tidak berubah setiap dijalankan).

1. Di dashboard ngrok buka menu **Domains** (di bawah *Universal Gateway* / *Cloud Edge*,
   tergantung versi tampilan).
2. Jika belum ada domain, klik **+ New Domain / Create Domain** → domain gratis dibuat otomatis,
   contohnya `bright-otter-happily.ngrok-free.app` (atau berakhiran `.ngrok-free.dev` — pakai persis seperti di dashboard).
3. **Salin nama domain tersebut** (tanpa `https://`).

## Langkah 5 — Simpan domain untuk dijalankan otomatis

1. Di folder aplikasi, buka folder **`vendor`** (dibuat otomatis saat langkah 6; jika belum ada,
   buat folder baru bernama `vendor`).
2. Buat file teks baru bernama **`ngrok_domain.txt`**, isi **satu baris** saja dengan domain Anda:
   ```
   bright-otter-happily.ngrok-free.app
   ```
   Simpan (pastikan namanya `ngrok_domain.txt`, bukan `ngrok_domain.txt.txt`).

## Langkah 6 — Buat kunci vendor (sekali saja)

Di Command Prompt folder aplikasi:
```bat
venv\Scripts\python tools\vendor_init.py
```
**Backup `vendor\private_key.pem` ke flashdisk** — jangan sampai hilang atau tersebar.

> Jika folder `venv` belum ada, jalankan dulu `jalankan.bat` sekali (atau langsung lanjut ke
> langkah 7 — file .bat akan menyiapkannya).

## Langkah 7 — Jalankan server lisensi + ngrok

Klik dua kali **`jalankan_server_lisensi.bat`**. Akan terbuka:

- Jendela **server lisensi** (jangan ditutup).
- Jendela **ngrok** berisi baris seperti:
  ```
  Forwarding   https://bright-otter-happily.ngrok-free.app -> http://localhost:8500
  ```
- Browser membuka **`http://localhost:8501`** → halaman admin → buat password admin.

## Langkah 8 — Uji dari luar

Dari HP memakai **data seluler** (bukan WiFi rumah), buka:
```
https://bright-otter-happily.ngrok-free.app/api/check
```
- Akun gratis ngrok menampilkan **halaman peringatan ngrok** dulu → klik **Visit Site**.
- Lalu muncul **Method Not Allowed** → **berhasil**, API bisa dihubungi dari internet.

Halaman peringatan itu hanya muncul di browser. Aplikasi sekolah otomatis melewatinya.

Membuka `https://...ngrok-free.app/` akan menampilkan **Not Found** — ini **benar**: halaman
admin sengaja hanya ada di laptop Anda (`http://localhost:8501`).

## Langkah 9 — Pasang alamat server di aplikasi

1. Buka `app\license.py` dengan Notepad, cari:
   ```python
   DEFAULT_SERVER_URL = os.environ.get("PRESENSI_LICENSE_SERVER", "")
   ```
   ubah menjadi (pakai domain Anda, **dengan** `https://`):
   ```python
   DEFAULT_SERVER_URL = os.environ.get("PRESENSI_LICENSE_SERVER", "https://bright-otter-happily.ngrok-free.app")
   ```
2. Simpan, lalu build aplikasi (`build_exe.bat`) untuk dibagikan ke sekolah.

## Langkah 10 — Terbitkan lisensi pertama

1. Di `http://localhost:8501` → **Buat lisensi baru** (nama sekolah, tier, masa berlaku).
2. Kirim **kode aktivasi** (mis. `K7QX-M2LP-AD9R`) ke sekolah.
3. Sekolah: **Akun → Lisensi → Aktivasi online** → masukkan kode → **Aktifkan**.
4. Sekolah muncul di **Perangkat teraktivasi** pada halaman admin. Selesai!

Tips uji coba di laptop sendiri: di aplikasi Presensi isi alamat server
`https://bright-otter-happily.ngrok-free.app` — kalau aktivasi berhasil, jalur internetnya sudah benar.

---

## Pemakaian sehari-hari

- Klik dua kali **`jalankan_server_lisensi.bat`** saat ingin melayani aktivasi (server + ngrok
  menyala bersamaan). Laptop **tidak harus menyala terus** — sekolah yang sudah aktif tetap jalan.
- Akun gratis ngrok hanya boleh **1 tunnel aktif** pada satu waktu dan memiliki batas kuota
  bulanan; untuk aktivasi & cek lisensi pemakaiannya sangat kecil sehingga cukup.

## Nanti pindah ke domain sendiri (Cloudflare)

1. Ikuti [`TUTORIAL_CLOUDFLARE.md`](TUTORIAL_CLOUDFLARE.md) langkah 1–8.
2. Hapus file `vendor\ngrok_domain.txt` → `jalankan_server_lisensi.bat` otomatis memakai
   Cloudflare Tunnel.
3. Ganti `DEFAULT_SERVER_URL` ke `https://lisensi.domainanda.com` dan build ulang untuk
   penjualan berikutnya.
4. Sekolah lama: lisensinya **tetap berlaku** walau alamat berubah. Agar cek online & perpanjangan
   otomatis kembali berjalan, admin sekolah cukup mengulang **Aktivasi online** dengan **kode yang
   sama** + alamat server baru (perangkat yang sama tidak dihitung sebagai aktivasi baru).
   Selama masa transisi Anda juga bisa menjalankan ngrok dan Cloudflare bersamaan
   (`ngrok http --url=DOMAIN-NGROK 8500` di jendela terpisah).

## Masalah umum

| Gejala | Penyebab & solusi |
|---|---|
| `'ngrok' is not recognized` / jendela ngrok tidak muncul | `ngrok.exe` belum ada di folder aplikasi (langkah 2). |
| ngrok: `ERR_NGROK_4018` / *authentication failed* | Authtoken belum disimpan — ulangi langkah 3. |
| ngrok: `ERR_NGROK_108` / *already online* | Masih ada ngrok lain yang berjalan (akun gratis = 1 tunnel). Tutup jendela ngrok lama. |
| ngrok: domain tidak valid / *not reserved* | Isi `vendor\ngrok_domain.txt` salah ketik atau berisi `https://`. Tulis domain saja. |
| Browser: `ERR_NGROK_3200` / *endpoint offline* | Jendela ngrok tertutup. Jalankan ulang `jalankan_server_lisensi.bat`. |
| Browser: `ERR_NGROK_8012` / *connection refused* | ngrok jalan tetapi server lisensi mati. Pastikan jendela server lisensi terbuka. |
| Sekolah: "Tidak dapat menghubungi server aktivasi" | Cek langkah 8 dari jaringan lain; pastikan alamat diawali `https://`. |
