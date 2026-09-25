# Server Aktivasi Lisensi (khusus vendor)

Server kecil untuk **menerbitkan, memperpanjang, dan mencabut lisensi** aplikasi Presensi
Siswa Digital. Server ini dijalankan di laptop/PC Anda (vendor), **bukan** di sekolah.

```
 Laptop vendor                                   Komputer sekolah
 ┌──────────────────────────────┐   internet   ┌──────────────────────────────┐
 │ server lisensi :8500         │◀────────────▶│ Aplikasi Presensi            │
 │  + kunci PRIVAT (rahasia)    │  (tunnel)    │  + kunci PUBLIK (cek saja)   │
 └──────────────────────────────┘              └──────────────────────────────┘
```

- Lisensi ditandatangani dengan **Ed25519**. Aplikasi sekolah hanya bisa *memeriksa*,
  tidak bisa *membuat* lisensi — walaupun `.exe` dibongkar.
- Aplikasi sekolah tetap **offline-first**: internet hanya dibutuhkan saat aktivasi. Setelah
  itu lisensi berlaku sampai tanggal kedaluwarsa walau offline. Saat online, aplikasi mengecek
  server tiap 6 jam → pencabutan dan perpanjangan/ganti tier diterima otomatis.
- Laptop Anda **tidak perlu menyala terus**. Bila server mati, sekolah yang sudah aktif tidak
  terpengaruh; hanya aktivasi baru yang menunggu server hidup.

## 1. Persiapan (sekali saja)

```bat
python tools\vendor_init.py
```

Menghasilkan:

| File | Keterangan |
|---|---|
| `vendor/private_key.pem` | **KUNCI PRIVAT — rahasiakan & backup ke flashdisk.** Sudah di-`.gitignore`. Jika hilang, Anda tidak bisa menerbitkan lisensi untuk aplikasi yang sudah tersebar. |
| `app/license_public.pem` | Kunci publik, ikut dibundel ke aplikasi sekolah. Build ulang `.exe` setelah file ini dibuat. |

Isi juga alamat server Anda di `app/license.py` (`DEFAULT_SERVER_URL = "https://..."`) sebelum
build, agar sekolah tidak perlu mengetik alamat server.

## 2. Menjalankan server

Klik dua kali **`jalankan_server_lisensi.bat`** (atau `python license_server/server.py`). Server membuka dua port:

| Port | Isi | Dibuka ke internet? |
|---|---|---|
| `8501` | **Halaman admin** — `http://localhost:8501` | Tidak, hanya laptop Anda |
| `8500` | API aktivasi untuk aplikasi sekolah | Ya, lewat tunnel |

Pertama kali membuka halaman admin Anda diminta membuat password.

Di halaman admin Anda bisa:
- **Buat lisensi** (nama sekolah, tier, masa berlaku, maks. perangkat) → muncul **kode aktivasi**
  seperti `K7QX-M2LP-AD9R` untuk dikirim ke sekolah.
- **Ubah tier / perpanjang** → diterima aplikasi sekolah otomatis saat online.
- **Cabut** lisensi (mis. belum bayar) → aplikasi turun ke Basic saat berikutnya online.
- **Lepas perangkat** → sekolah bisa memindahkan lisensi ke komputer baru.
- **Buat kode offline** untuk sekolah tanpa internet (cukup minta ID perangkatnya).

Data server tersimpan di `license_server/data/lisensi.db` (backup berkala).

## 3. Membuka server ke internet (tanpa setting router)

Koneksi rumah umumnya tidak punya IP publik, jadi gunakan *tunnel*:

### Opsi A — Cloudflare Tunnel (disarankan, gratis, alamat tetap)

📘 **Tutorial langkah demi langkah dari nol: [`TUTORIAL_CLOUDFLARE.md`](TUTORIAL_CLOUDFLARE.md)**
Butuh akun Cloudflare gratis dan sebuah domain (mis. `.my.id` / `.com`) yang DNS-nya di Cloudflare.

```bat
winget install --id Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create lisensi
cloudflared tunnel route dns lisensi lisensi.domainanda.com
cloudflared tunnel run --url http://localhost:8500 lisensi
```

Alamat server untuk sekolah: `https://lisensi.domainanda.com`.
Setelah itu cukup jalankan server + perintah terakhir setiap kali ingin melayani aktivasi.

### Opsi B — ngrok (tanpa domain sendiri)

📘 **Tutorial langkah demi langkah: [`TUTORIAL_NGROK.md`](TUTORIAL_NGROK.md)**
Daftar di ngrok.com → klaim 1 *static domain* gratis → lalu:
```bat
ngrok http --url=nama-anda.ngrok-free.app 8500
```
Alamat server: `https://nama-anda.ngrok-free.app`.

### Uji coba cepat (alamat berubah-ubah)
```bat
cloudflared tunnel --url http://localhost:8500
```
Menampilkan alamat acak `https://xxxx.trycloudflare.com` — alamat berganti setiap dijalankan,
jadi hanya untuk mencoba. Jika alamat server berganti, lisensi sekolah **tetap aktif**; hanya
cek online harian yang gagal sampai admin sekolah memperbarui alamat server di halaman Lisensi.

Keamanan: halaman admin berjalan di port terpisah (8501) yang tidak pernah dilewatkan ke tunnel; port publik 8500 hanya melayani API; admin dilindungi password; API aktivasi dibatasi 20 percobaan/menit per IP;
kode aktivasi acak 12 karakter (≈60 bit) sehingga tidak bisa ditebak.
