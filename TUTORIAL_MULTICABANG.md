# Tutorial: Dashboard Multi-Cabang

Fitur **Multi-Cabang** mengumpulkan ringkasan presensi **hari ini** dari beberapa sekolah atau
cabang ke **satu layar**. Cocok untuk yayasan yang membawahi beberapa sekolah (SD, SMP, SMA)
atau sekolah dengan beberapa kampus.

```
                ┌──────────────────────────────┐
                │  SERVER PUSAT (Enterprise)   │
                │  Menu Sistem → Multi-Cabang  │
                └──────┬───────────┬───────────┘
          URL + token  │           │  URL + token
                       ▼           ▼
          ┌──────────────┐   ┌──────────────┐
          │  Cabang A    │   │  Cabang B    │   ← masing-masing menjalankan
          │  (tier apa   │   │  (tier apa   │     aplikasi Presensi sendiri
          │   saja)      │   │   saja)      │     dengan database sendiri
          └──────────────┘   └──────────────┘
```

## Yang perlu diketahui dulu

| Hal | Keterangan |
|---|---|
| Lisensi | Hanya **server pusat** yang wajib **Enterprise**. Server cabang boleh tier apa saja, termasuk Basic. |
| Data yang dikirim | Hanya angka ringkasan hari ini: jumlah siswa, Hadir, Telat, Izin, Sakit, Alpha, Dispensasi, Belum absen, % hadir. **Tidak ada nama atau data pribadi siswa.** |
| Arah koneksi | Pusat yang **mengambil** data dari cabang saat halaman dibuka. Cabang tidak perlu mengatur apa-apa selain membagikan URL + token. |
| Pembaruan | Angka diambil saat halaman Multi-Cabang dibuka. Tekan **F5** untuk memperbarui. |
| Data tetap terpisah | Tiap cabang tetap mengelola siswa, kartu, presensi, dan WA-nya sendiri. Pusat hanya melihat ringkasan. |
| Alpha | Siswa baru dihitung **Alpha** setelah *jam tutup* di cabang tersebut. Sebelum itu masih terhitung **Belum**. |

---

## Langkah 1 — Siapkan aplikasi di setiap cabang

Di komputer server **setiap cabang**:

1. Pasang dan jalankan aplikasi Presensi seperti biasa (`jalankan.bat` atau `PresensiSiswa.exe`).
2. Buka **Pengaturan**, isi **Nama sekolah** sesuai cabang (mis. *SMP Al-Hikmah Kampus 2*).
   Nama inilah yang tampil di dashboard pusat.
3. Isi data kelas dan siswa seperti biasa.

## Langkah 2 — Catat URL dan token setiap cabang

Token dibuat otomatis oleh setiap aplikasi. Cara melihatnya:

- **Jika cabang berlisensi Enterprise:** buka menu **Sistem → Multi-Cabang**. Di kotak
  **Token API server ini** tertulis *URL server ini* dan *Token API*.
- **Jika cabang berlisensi Basic/Pro** (menu Multi-Cabang tidak tampil): buka Command Prompt
  di folder aplikasi cabang, lalu jalankan:
  ```bat
  venv\Scripts\python -c "from app import create_app; from app.db import get_setting; a=create_app(start_jobs=False); a.app_context().push(); print(get_setting('cabang_api_token'))"
  ```
  Untuk versi `.exe`, token dapat dibaca dari database `data\presensi.db` dengan
  [DB Browser for SQLite](https://sqlitebrowser.org): tabel `settings`, baris `cabang_api_token`.

Catat untuk setiap cabang:

| Cabang | URL server | Token |
|---|---|---|
| Kampus 2 | `http://192.168.1.20:5000` | `k3Jd…` |
| Kampus 3 | `http://100.101.102.103:5000` | `Q9pa…` |

> 🔒 **Rahasiakan token.** Siapa pun yang memegang URL + token dapat melihat ringkasan presensi
> harian cabang tersebut. Kirim lewat pesan pribadi, jangan di grup.

URL yang dipakai tergantung **lokasi** cabang terhadap pusat. Pilih skenario A atau B di bawah.

---

## Skenario A — Pusat dan cabang dalam SATU jaringan (satu gedung/WiFi/LAN)

### A1. Pakai IP lokal

URL cabang = `http://<IP-komputer-cabang>:5000`. IP-nya:
- tertulis di jendela hitam saat aplikasi dijalankan (`HP / perangkat lain (WiFi sama): http://192.168.x.x:5000`), atau
- tertulis di halaman **Multi-Cabang** cabang tersebut (*URL server ini*).

Uji dari komputer pusat: buka `http://192.168.x.x:5000` di browser. Jika halaman login cabang
tampil, koneksinya sudah benar.

### A2. Izinkan lewat Firewall Windows (di komputer cabang)

Saat aplikasi pertama kali dijalankan, Windows biasanya menampilkan jendela **Windows Defender
Firewall** → centang **Private networks** → **Allow access**.

Jika jendela itu terlewat dan pusat tidak bisa membuka URL cabang, buka Command Prompt
**Run as administrator** di komputer cabang, lalu jalankan:
```bat
netsh advfirewall firewall add rule name="Presensi Siswa 5000" dir=in action=allow protocol=TCP localport=5000
```

### A3. Kunci IP agar tidak berubah

IP lokal bisa berganti setelah router restart, dan dashboard pusat akan menampilkan
*Tidak terhubung*. Solusinya: di pengaturan router, gunakan **DHCP Reservation / Static IP**
untuk komputer cabang. Menu ini biasanya ada di halaman admin router, mis. `192.168.1.1`.

---

## Skenario B — Cabang di LOKASI BERBEDA (lewat internet)

Server cabang ada di jaringan sekolahnya sendiri, jadi tidak bisa langsung dihubungi dari luar.
Pilih salah satu cara berikut.

### B1. Tailscale (disarankan: gratis, aman, tanpa domain)

Tailscale membuat "jaringan lokal virtual" terenkripsi antarkomputer, di mana pun lokasinya.

1. Buat akun di **https://tailscale.com** (bisa dengan akun Google/Microsoft).
2. Pasang **Tailscale** di komputer **pusat** dan di komputer server **setiap cabang**
   (unduh di https://tailscale.com/download → Windows). Login dengan **akun yang sama**.
3. Setiap komputer mendapat IP tetap berawalan `100.` Lihat IP-nya dengan mengklik ikon
   Tailscale di taskbar, atau di https://login.tailscale.com/admin/machines.
4. URL cabang = `http://100.x.y.z:5000`.
5. Jika tidak bisa dibuka dari pusat, jalankan perintah firewall di langkah **A2** pada komputer
   cabang.

Kelebihan: gratis untuk pemakaian kecil (puluhan perangkat), lalu lintas terenkripsi, IP tidak
berubah, dan aplikasi cabang **tidak terbuka ke internet umum**.

### B2. ngrok (jika sudah terbiasa)

1. Di komputer cabang: pasang ngrok (lihat [`license_server/TUTORIAL_NGROK.md`](license_server/TUTORIAL_NGROK.md)
   langkah 1–4), lalu jalankan:
   ```bat
   ngrok http --url=DOMAIN-CABANG.ngrok-free.app 5000
   ```
2. URL cabang = `https://DOMAIN-CABANG.ngrok-free.app`.

Catatan:
- Akun ngrok gratis hanya boleh 1 tunnel aktif, jadi **setiap cabang memakai akun ngrok sendiri**.
  Akun ngrok Anda sendiri sudah dipakai server lisensi.
- Jendela ngrok harus tetap terbuka di komputer cabang.
- Dengan cara ini **halaman login cabang terbuka ke internet**. Wajib ganti password `admin`
  dengan password yang kuat.

### B3. Cloudflare Tunnel (setelah punya domain)

Sama seperti [`license_server/TUTORIAL_CLOUDFLARE.md`](license_server/TUTORIAL_CLOUDFLARE.md),
tetapi `service` diarahkan ke `http://localhost:5000` dan setiap cabang memakai subdomain sendiri,
mis. `https://kampus2.domainanda.com`. Peringatan soal halaman login pada B2 juga berlaku di sini.

---

## Langkah 3 — Daftarkan cabang di server pusat

Di komputer **pusat** (lisensi Enterprise):

1. Login sebagai **admin** → menu **Sistem → Multi-Cabang**.
2. Di kotak **Tambah cabang**, isi:
   - **Nama**: nama cabang (mis. *Kampus 2*)
   - **URL server cabang**: dari langkah 2, diawali `http://` atau `https://`, **tanpa** garis
     miring di akhir
   - **Token API cabang**: dari langkah 2
3. Klik **Tambah**. Ulangi untuk setiap cabang.

## Langkah 4 — Membaca dashboard

Tabel **Ringkasan hari ini** menampilkan satu baris per sekolah:

| Kolom | Arti |
|---|---|
| **Siswa** | Jumlah siswa aktif |
| **H** | Hadir (termasuk yang telat) |
| **Telat** | Hadir tetapi melewati batas telat |
| **I / S / D** | Izin / Sakit / Dispensasi yang disetujui |
| **A** | Alpha (dihitung setelah jam tutup) |
| **Belum** | Belum ada catatan presensi hari ini |
| **% Hadir** | (Hadir + Dispensasi) ÷ jumlah siswa |

Baris pertama bertanda **(server ini)** adalah sekolah tempat server pusat berjalan.
Tekan **F5** kapan saja untuk mengambil angka terbaru. Cabang yang tidak dipakai lagi dihapus
dengan tombol **Hapus** di ujung barisnya.

---

## Masalah umum

Jika sebuah cabang gagal dihubungi, barisnya berlabel **Tidak terhubung** disertai keterangan:

| Keterangan | Penyebab & solusi |
|---|---|
| **token salah** | Token yang dimasukkan tidak cocok. Salin ulang token dari cabang (langkah 2), hapus baris cabang, lalu tambahkan lagi. |
| **tidak ada jawaban (server cabang mati / beda jaringan)** | Aplikasi di komputer cabang belum dijalankan, komputer cabang mati, firewall memblokir (langkah A2), atau Tailscale belum menyala di salah satu komputer. |
| **tidak dapat terhubung (server cabang mati / URL salah)** | Periksa IP/alamat dan port `:5000`. Uji dengan membuka URL tersebut di browser komputer pusat. |
| **alamat tersebut bukan server Presensi (periksa URL)** | URL mengarah ke halaman lain, mis. salah port atau jendela ngrok cabang tertutup. |
| **HTTP 404 (periksa URL)** | URL berisi jalur tambahan. Cukup `http://IP:5000`, tanpa `/login` atau garis miring di akhir. |
| Menu Multi-Cabang tidak tampil di pusat | Lisensi server pusat belum **Enterprise**. Cek di menu **Lisensi**. |
| Angka Alpha 0 padahal banyak yang tidak datang | Normal sebelum *jam tutup* cabang tersebut. Siswa masih terhitung **Belum**. |
