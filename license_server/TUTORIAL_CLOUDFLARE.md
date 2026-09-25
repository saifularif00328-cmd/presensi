# Tutorial: Server Lisensi Online dengan Cloudflare Tunnel (dari nol)

Hasil akhir: server lisensi di laptop Anda bisa dihubungi sekolah lewat alamat tetap
**`https://lisensi.domainanda.com`**, tanpa setting router dan tanpa IP publik.

```
Aplikasi sekolah ──internet──▶ Cloudflare ──tunnel terenkripsi──▶ laptop Anda (localhost:8500)
```

Yang dibutuhkan:
- Laptop Windows (tempat server lisensi) + koneksi internet
- Sebuah **domain** (±Rp 20.000–200.000/tahun)
- Akun **Cloudflare** (gratis)

Perkiraan waktu: 30–60 menit (+ menunggu aktivasi domain, bisa beberapa jam).

---

## Langkah 1 — Beli domain

Pilih salah satu:

| Pilihan | Contoh | Catatan |
|---|---|---|
| **.com / .net** lewat Cloudflare Registrar | `presensiku.com` | Paling mudah (langkah 3 otomatis selesai). Bayar pakai kartu kredit/debit internasional atau PayPal, ±US$10/tahun. Beli di dashboard Cloudflare → **Domain Registration → Register Domains** (setelah langkah 2). |
| **.my.id / .web.id / .id** lewat registrar Indonesia | `presensiku.my.id` | Murah & bisa bayar transfer/e-wallet (Niagahoster/Hostinger, DomaiNesia, Rumahweb, dll.). Domain `.id` biasanya perlu verifikasi KTP. |
| .com lewat registrar lain | Niagahoster, Namecheap, dll. | Sama seperti baris kedua. |

> Satu domain cukup untuk selamanya. Server lisensi memakai *subdomain* `lisensi.`, sehingga
> domain utamanya tetap bisa dipakai untuk website Anda.

## Langkah 2 — Buat akun Cloudflare

1. Buka **https://dash.cloudflare.com/sign-up**, daftar dengan email & password.
2. Buka email Anda dan klik tautan verifikasi dari Cloudflare.

## Langkah 3 — Hubungkan domain ke Cloudflare

*(Lewati bila membeli domain lewat Cloudflare Registrar — sudah otomatis.)*

1. Di dashboard Cloudflare klik **Add a domain** (atau *Add site*).
2. Ketik domain Anda (mis. `presensiku.my.id`) → **Continue**.
3. Pilih paket **Free** → **Continue**. Biarkan Cloudflare memindai DNS → **Continue**.
4. Cloudflare menampilkan **2 nameserver**, contohnya:
   ```
   ada.ns.cloudflare.com
   bob.ns.cloudflare.com
   ```
5. Login ke panel registrar tempat Anda membeli domain → menu **Nameserver / DNS domain** →
   ganti semua nameserver lama dengan 2 nameserver dari Cloudflare → simpan.
6. Kembali ke Cloudflare, klik **Check nameservers**. Tunggu sampai status domain **Active**
   (dapat email "…is now active on Cloudflare"). Biasanya 5 menit – 24 jam.

⚠️ Jangan lanjut ke langkah 5 sebelum status domain **Active**.

## Langkah 4 — Pasang `cloudflared` di laptop

1. Klik Start, ketik **cmd**, klik kanan **Command Prompt → Run as administrator**.
2. Jalankan:
   ```bat
   winget install --id Cloudflare.cloudflared
   ```
   Jika `winget` tidak dikenal: unduh file **`cloudflared-windows-amd64.msi`** dari
   https://github.com/cloudflare/cloudflared/releases/latest lalu instal (Next → Finish).
3. **Tutup** Command Prompt, buka lagi (biasa, tidak perlu administrator), cek:
   ```bat
   cloudflared --version
   ```
   Harus muncul versi, mis. `cloudflared version 2025.x.x`.

## Langkah 5 — Login cloudflared ke akun Cloudflare

```bat
cloudflared tunnel login
```

Browser terbuka → login Cloudflare → **pilih domain Anda** → klik **Authorize**.
Setelah tampil "Success", kembali ke Command Prompt. File sertifikat tersimpan di
`C:\Users\<nama-anda>\.cloudflared\cert.pem`.

## Langkah 6 — Buat tunnel

```bat
cloudflared tunnel create lisensi-presensi
```

Catat **Tunnel ID** yang tampil (deretan huruf-angka panjang, mis.
`6ff42ae2-765d-4adf-8112-31c55c1551ef`). Dibuat juga file kredensial
`C:\Users\<nama-anda>\.cloudflared\<TUNNEL-ID>.json` — **rahasiakan** file ini.

## Langkah 7 — Arahkan subdomain ke tunnel

```bat
cloudflared tunnel route dns lisensi-presensi lisensi.domainanda.com
```

(ganti `domainanda.com` dengan domain Anda). Cloudflare otomatis membuat catatan DNS untuk
`lisensi.domainanda.com`.

## Langkah 8 — Buat file konfigurasi tunnel

1. Buka Notepad, salin isi berikut, **ganti 3 bagian bertanda `<...>`**:
   ```yaml
   tunnel: <TUNNEL-ID>
   credentials-file: C:\Users\<nama-anda>\.cloudflared\<TUNNEL-ID>.json

   ingress:
     - hostname: lisensi.domainanda.com
       service: http://localhost:8500
     - service: http_status:404
   ```
2. **File → Save As** → buka folder `C:\Users\<nama-anda>\.cloudflared\` →
   *Save as type*: **All Files** → nama file: **`config.yml`** → Save.
   (Pastikan tidak menjadi `config.yml.txt`.)

   Tips: folder `.cloudflared` bisa dibuka dengan mengetik `%USERPROFILE%\.cloudflared` di
   address bar File Explorer.

## Langkah 9 — Siapkan & jalankan server lisensi

Di folder aplikasi:

1. (Sekali saja) buat kunci vendor — **backup `vendor\private_key.pem` ke flashdisk**:
   ```bat
   venv\Scripts\python tools\vendor_init.py
   ```
2. Klik dua kali **`jalankan_server_lisensi.bat`**. Karena `config.yml` sudah ada, file ini
   otomatis membuka 2 jendela: server lisensi **dan** Cloudflare Tunnel.
3. Browser membuka `http://localhost:8501` (halaman admin) → buat password admin.

Jendela "Cloudflare Tunnel" yang sehat menampilkan baris `Registered tunnel connection`.

## Langkah 10 — Uji dari luar

Dari HP (pakai **data seluler**, bukan WiFi rumah) buka:

- `https://lisensi.domainanda.com/api/check` → muncul teks singkat / *Method Not Allowed*
  → **berhasil**, server bisa dihubungi dari internet.
- `https://lisensi.domainanda.com/` → muncul **Not Found** → **benar**. Halaman admin
  sengaja hanya bisa dibuka dari laptop Anda (`http://localhost:8501`), agar tidak bisa
  diserang dari internet. Tunnel hanya meneruskan port 8500 (API aktivasi).

## Langkah 11 — Pasang alamat server di aplikasi

1. Buka `app\license.py` dengan Notepad, cari baris:
   ```python
   DEFAULT_SERVER_URL = os.environ.get("PRESENSI_LICENSE_SERVER", "")
   ```
   ubah menjadi:
   ```python
   DEFAULT_SERVER_URL = os.environ.get("PRESENSI_LICENSE_SERVER", "https://lisensi.domainanda.com")
   ```
2. Simpan, lalu build aplikasi (`build_exe.bat`) untuk dibagikan ke sekolah.

## Langkah 12 — Terbitkan lisensi pertama

1. Di `http://localhost:8501` → **Buat lisensi baru** (nama sekolah, tier, masa berlaku).
2. Kirim **kode aktivasi** (mis. `K7QX-M2LP-AD9R`) ke sekolah.
3. Sekolah membuka **Akun → Lisensi → Aktivasi online**, memasukkan kode → **Aktifkan**.
   Kolom alamat server sudah terisi otomatis dari langkah 11.
4. Di halaman admin, sekolah tersebut muncul di **Perangkat teraktivasi**. Selesai!

---

## Pemakaian sehari-hari

- Cukup klik dua kali **`jalankan_server_lisensi.bat`** saat ingin melayani aktivasi.
- Laptop **tidak harus menyala terus**: sekolah yang sudah aktif tetap berjalan. Selama server
  mati, hanya aktivasi baru & pengecekan status yang tertunda (dicoba lagi otomatis tiap 6 jam).
- Backup berkala: `vendor\private_key.pem` (sekali) dan `license_server\data\lisensi.db` (daftar
  lisensi & kode aktivasi).

## Masalah umum

| Gejala | Penyebab & solusi |
|---|---|
| `'cloudflared' is not recognized` | Tutup lalu buka lagi Command Prompt setelah instalasi, atau restart laptop. |
| Error **1033** saat membuka alamat | Tunnel tidak berjalan. Pastikan jendela "Cloudflare Tunnel" terbuka & menampilkan `Registered tunnel connection`. |
| Error **502 Bad Gateway** | Tunnel jalan tetapi server lisensi mati. Jalankan `jalankan_server_lisensi.bat`. |
| Alamat tidak ditemukan (DNS) | Domain belum **Active** di Cloudflare (langkah 3) atau langkah 7 belum dijalankan. Tunggu / ulangi. |
| `failed to parse config` | Salah ketik di `config.yml` — spasi/indentasi harus persis seperti contoh (pakai spasi, bukan Tab). |
| Jendela tunnel tidak muncul otomatis | `config.yml` tidak di `%USERPROFILE%\.cloudflared\` atau tersimpan sebagai `config.yml.txt`. |
| Sekolah: "Tidak dapat menghubungi server aktivasi" | Cek langkah 10 dari jaringan lain. Pastikan alamat diawali `https://`. |
