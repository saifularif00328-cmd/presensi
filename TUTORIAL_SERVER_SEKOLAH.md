# Tutorial Tahap 1 — Server di Komputer Sekolah + Cloudflare Tunnel

Untuk 1–3 sekolah pertama (biaya server Rp0). Aplikasi, database MySQL (MariaDB), dan koneksi
Cloudflare berjalan di **satu komputer Windows di sekolah**. Portal orang tua bisa dibuka dari
mana saja di alamat tetap, mis. **`https://smpn1.presensiku.biz.id`**. Saat nanti pindah ke VPS,
alamat itu **tidak berubah**.

```
HP orang tua / siswa ─┐                                   ┌─ PC Windows sekolah (menyala terus) ─┐
ESP32 di gerbang ─────┼─▶ Cloudflare ─▶ tunnel ──────────▶│ cloudflared → Presensi :5000 → MariaDB │
PC piket (WiFi sekolah) ── http://IP-server:5000 ────────▶│                                        │
                                                          └────────────────────────────────────────┘
```

---

## A. Sekali saja — disiapkan vendor (Anda)

### A1. Domain di Cloudflare
Sudah selesai: `presensiku.biz.id` aktif di Cloudflare (paket Free).

### A2. Buat installer
Di laptop vendor (Windows):
1. Pasang **Inno Setup 6** (gratis): https://jrsoftware.org/isdl.php
2. Jalankan `build_exe.bat` (menghasilkan `dist\PresensiSiswa\`).
3. Buka PowerShell di folder aplikasi, jalankan sekali:
   `powershell -ExecutionPolicy Bypass -File installer\siapkan_bundel.ps1`
   (mengunduh MariaDB, cloudflared, dan WinSW ke `installer\bundel\`).
4. Buka `installer\presensi.iss` di Inno Setup → **Build → Compile**.
   Hasil: **`installer\Output\PasangPresensi-2.0.0.exe`** — file inilah yang dibawa ke sekolah.

---

## B. Untuk setiap sekolah baru

### B1. Buat tunnel sekolah di Cloudflare (± 3 menit)
1. Buka https://one.dash.cloudflare.com → **Networks → Tunnels** → **Create a tunnel**.
2. Pilih **Cloudflared** → nama tunnel: `smpn1` → **Save tunnel**.
3. Di halaman *Install and run connectors* pilih **Windows**. Salin **token** (teks panjang setelah
   `cloudflared.exe service install ...`). Simpan untuk langkah B3.
4. **Next** → tab **Public hostname** → **Add a public hostname**:
   - Subdomain: `smpn1` · Domain: `presensiku.biz.id`
   - Service: **HTTP** · URL: **`localhost:5000`**
   - **Save hostname**.

### B2. Pasang di komputer sekolah (± 5 menit)
Syarat komputer: Windows 10/11 64-bit, RAM ≥ 4 GB, tersambung internet & jaringan sekolah.
1. Jalankan **`PasangPresensi-2.0.0.exe`** → *Next* sampai selesai (butuh akses Administrator).
   Installer otomatis:
   - memasang database MariaDB (password acak, hanya bisa diakses dari komputer itu),
   - menjalankan aplikasi sebagai **layanan Windows** (otomatis jalan saat komputer menyala,
     tanpa perlu login, dan dihidupkan lagi bila berhenti),
   - membuka port 5000 untuk jaringan sekolah,
   - mengatur komputer agar **tidak sleep** dan Windows Update tidak restart di jam sekolah.
2. Browser terbuka di `http://localhost:5000` → login **admin / admin123** → wajib ganti password.

### B3. Hubungkan ke internet
1. Di aplikasi: **Sistem → Akses Online**.
2. Tempel **token** dari langkah B1 → **Hubungkan**. Status berubah menjadi *Terhubung*.
3. Isi **Alamat publik sekolah**: `https://smpn1.presensiku.biz.id` → **Simpan alamat**.
4. Uji dari HP (pakai data seluler): buka `https://smpn1.presensiku.biz.id/portal/masuk`.

### B4. Pengaturan awal sekolah
- **Pengaturan**: nama sekolah, logo, **zona waktu** (WIB/WITA/WIT), hari sekolah, portal aktif.
- **Aturan Jam**, **Kalender Libur**, **Data Kelas**, **Data Siswa** (import Excel).
- **Notifikasi WA**: token Fonnte sekolah.
- **Kartu RFID** & **Perangkat RFID**: lihat [`TUTORIAL_RFID.md`](TUTORIAL_RFID.md).
- **Portal & PIN Siswa**: cetak PIN siswa; bagikan [`TUTORIAL_PORTAL.md`](TUTORIAL_PORTAL.md) ke orang tua.
- **Langganan & Lisensi**: masukkan kode aktivasi (tanpa kode = uji coba 14 hari).

---

## C. Agar portal bisa dibuka 24 jam
- Biarkan komputer server **menyala** (mini-PC hemat listrik ideal) dan pasang **UPS**.
- Di BIOS, aktifkan **Restore on AC Power Loss = Power On** agar komputer menyala sendiri setelah
  listrik padam (menu BIOS biasanya dibuka dengan F2/Del saat komputer baru menyala).
- Jangan matikan layanan *Presensi Siswa Digital*, *PresensiDB*, dan *cloudflared* di
  `services.msc`.
- Pantau dari mana saja (gratis): daftar di https://uptimerobot.com → *Add New Monitor* → HTTP(s)
  → `https://smpn1.presensiku.biz.id/portal/masuk` → Anda mendapat email bila server sekolah mati.

## D. Backup
- Otomatis setiap hari ke `C:\PresensiSiswa\data\backup\` (14 hari terakhir).
- Menu **Pengaturan → Backup** mengunduh ZIP lengkap (database + foto). Simpan salinan di flashdisk /
  Google Drive seminggu sekali.
- File ZIP yang sama dipakai untuk **pindah ke VPS** ([`TUTORIAL_VPS.md`](TUTORIAL_VPS.md)).

## E. Masalah umum

| Gejala | Solusi |
|---|---|
| `https://smpn1...` menampilkan error Cloudflare 1033 | Tunnel mati: cek internet sekolah & layanan *cloudflared* di `services.msc`, atau ulangi langkah B3. |
| Error 502 | Aplikasi mati: jalankan ulang layanan *Presensi Siswa Digital* di `services.msc`. |
| PC piket tidak bisa membuka `http://IP-server:5000` | Pastikan satu jaringan; firewall port 5000 (installer sudah membukanya untuk jaringan *Private*). Ubah jaringan WiFi ke *Private* di pengaturan Windows. |
| Lupa password admin | Hubungi vendor (reset lewat database). |
