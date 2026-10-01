# Panduan Pemula — Dari VPS Baru sampai presensiku.biz.id/smpn1 Online

Ikuti **berurutan**, satu tahap selesai baru lanjut. Perkiraan waktu total ±1 jam.

**Yang Anda butuhkan:**
- laptop Windows 10/11;
- email dari Rumahweb berisi data VPS;
- akun Cloudflare (domain `presensiku.biz.id` sudah aktif di sana).

**Cara membaca panduan ini:**
- Kotak abu-abu = perintah. **Salin persis**, lalu tempel.
- `IP-VPS` = ganti dengan angka IP VPS Anda, mis. `103.123.45.67`.
- Di **PowerShell**, menempel teks = **klik kanan** (bukan Ctrl+V).
- Setelah menempel, tekan **Enter**, lalu tunggu sampai muncul tanda siap lagi (`#` atau `>`).

---

## TAHAP 0 — Cari IP dan password VPS
1. Buka email dari Rumahweb dengan judul seperti **"VPS Information"** / **"Informasi Layanan VPS"**.
2. Catat:
   - **IP Address**, mis. `103.123.45.67`;
   - **Username**: `root`;
   - **Password**: deretan huruf/angka acak.
3. Tidak menemukan email? Masuk ke **clientzone.rumahweb.com → Layanan → VPS Anda**. IP dan
   password ada di halaman detail layanan.

> Password VPS **rahasia**. Jangan kirim ke siapa pun, termasuk ke chat.

## TAHAP 1 — Masuk ke VPS untuk pertama kali
1. Di laptop, tekan tombol **Windows**, ketik `powershell`, lalu klik **Windows PowerShell**.
   Muncul jendela biru/hitam.
2. Ketik (ganti IP):
   ```
   ssh root@IP-VPS
   ```
3. Bila muncul `Are you sure you want to continue connecting (yes/no)?`, ketik `yes` lalu Enter.
4. Muncul `root@...'s password:`. Ketik atau tempel password dari email (klik kanan).
   **Tulisan tidak akan muncul sama sekali — itu normal.** Tekan Enter.
5. Berhasil bila muncul tulisan seperti:
   ```
   root@server1:~#
   ```
   Mulai sekarang, perintah yang diketik di sini dijalankan **di VPS**.

**Bila gagal:**

| Pesan | Artinya |
|---|---|
| `Permission denied` | Password salah. Ulangi pelan-pelan, atau salin ulang dari email. |
| `Connection timed out` | IP salah, atau VPS belum aktif. Cek di clientzone. |
| `ssh is not recognized` | Windows terlalu lama. Pasang "OpenSSH Client" di *Settings → Apps → Optional features*. |

## TAHAP 2 — Ganti password dan perbarui VPS
Masih di VPS (`root@server1:~#`):

1. Ganti password root:
   ```
   passwd
   ```
   Ketik password baru (minimal 16 karakter), Enter, ketik lagi, Enter. Tulisan tetap tidak
   tampil. Catat di tempat aman.
2. Perbarui sistem (±3–5 menit):
   ```
   apt update && apt upgrade -y
   ```
   Bila muncul layar ungu/biru bertanya sesuatu, tekan **Enter** saja (pilihan bawaan).
3. Nyalakan ulang VPS:
   ```
   reboot
   ```
   Koneksi akan terputus — itu normal. **Tunggu 1 menit.**

## TAHAP 3 — Buat "kunci" supaya tidak bisa dibobol
Penjahat di internet terus mencoba menebak password VPS. Kita ganti password dengan **kunci
digital** yang tersimpan di laptop Anda.

1. Di jendela PowerShell yang sama (sekarang posisinya di **laptop**, tanda `PS C:\Users\...>`),
   jalankan:
   ```
   ssh-keygen -t ed25519
   ```
   Tekan **Enter 3 kali**. Selesai bila muncul gambar kotak acak (`randomart`).
2. Kirim kunci ke VPS. Salin **satu baris panjang** ini (ganti `IP-VPS`):
   ```
   type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@IP-VPS "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
   ```
   Masukkan **password root yang baru** (Tahap 2), lalu Enter.
3. Uji kunci:
   ```
   ssh root@IP-VPS
   ```
   ✅ **Langsung masuk tanpa ditanya password** = kunci berhasil.
   ❌ Masih ditanya password = ulangi langkah 2.

## TAHAP 4 — Kunci pintu password
**Kerjakan hanya bila Tahap 3 berhasil.** Anda sedang di VPS (`root@server1:~#`).

1. Tempel **seluruh 5 baris ini sekaligus**, lalu Enter:
   ```
   cat > /etc/ssh/sshd_config.d/00-presensi.conf <<'EOF'
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PermitRootLogin prohibit-password
   EOF
   ```
2. Terapkan:
   ```
   sshd -t && systemctl restart ssh
   ```
3. **JANGAN tutup jendela ini.** Buka jendela PowerShell **baru**, lalu ketik `ssh root@IP-VPS`.
   - ✅ **Masuk tanpa password** → selesai, VPS aman. Jendela lama boleh ditutup.
   - ❌ **Gagal** → kembali ke jendela lama, jalankan perintah di bawah, lalu ulangi Tahap 3:
     ```
     rm /etc/ssh/sshd_config.d/00-presensi.conf && systemctl restart ssh
     ```
4. **Cadangkan kunci:** salin folder `C:\Users\NAMA-ANDA\.ssh` ke flashdisk.
   - Laptop rusak/hilang? Masuk ke VPS lewat **clientzone Rumahweb → VPS → Console/VNC**.
   - **Jangan pernah membagikan file `id_ed25519` (yang tanpa `.pub`).**

## TAHAP 5 — Pasang aplikasi Presensi
Di VPS, tempel satu baris ini, lalu Enter:
```
curl -fsSL https://raw.githubusercontent.com/saifularif00328-cmd/presensi/claude/aplikasi-sesuai-prd-bppvd6/deploy/install_vps.sh | bash
```
- Tunggu **±10 menit**. Banyak tulisan bergulir — biarkan saja.
- Selesai bila muncul kotak **`SELESAI. Langkah berikutnya:`**.

Skrip ini sekaligus memasang pengaman:
- firewall;
- pemblokir penebak password (fail2ban);
- update keamanan otomatis;
- backup harian pukul 03.00.

## TAHAP 6 — Sambungkan ke Cloudflare (sekali saja)
Tanpa dashboard Zero Trust, jadi **tidak perlu kartu kredit/PayPal**.

1. Di VPS jalankan:
   ```
   cloudflared tunnel login
   ```
   Muncul tautan panjang `https://dash.cloudflare.com/argotunnel?...`.
2. Salin tautan itu:
   - blok dengan mouse dari `https` sampai akhir (boleh beberapa baris);
   - tekan **Enter** (di PowerShell, Enter = salin);
   - tempel di browser yang sudah login Cloudflare.
3. Klik domain **presensiku.biz.id**, lalu klik **Authorize**. Di VPS muncul
   `You have successfully logged in` dan perintah selesai sendiri.
4. Di VPS jalankan:
   ```
   bash /opt/presensi/deploy/tunnel_vps.sh
   ```
   Selesai bila muncul `cloudflared: aktif` dan kotak **SELESAI**.
5. Tunggu 1–2 menit, lalu buka **https://presensiku.biz.id**. ✅ Muncul halaman **"Kode sekolah"**.

> File `/root/.cloudflared/cert.pem` dan `/etc/cloudflared/*.json` adalah kunci tunnel —
> jangan dibagikan.

## TAHAP 7 — Tambah sekolah pertama
Di VPS:
```
presensi-sekolah tambah smpn1 --nama "SMP Negeri 1 Contoh" --hari 14 --maks-siswa 1000
```
Penjelasan:
- `smpn1` = kode alamat (huruf kecil/angka/strip, tanpa spasi);
- `--hari 14` = masa uji coba 14 hari;
- `--maks-siswa` = batas jumlah siswa.

Lalu:
1. Buka **https://presensiku.biz.id/smpn1**.
2. Login `admin` / `admin123`. Anda **wajib mengganti password** — buat yang kuat.
3. Isi **Pengaturan** (nama sekolah, logo, jam masuk), lalu data kelas dan siswa.

Saat sekolah membayar, perpanjang langganan:
```
presensi-sekolah perpanjang smpn1 --hari 365
```

## TAHAP 8 — Pengaman akun (5 menit)
- **Cloudflare**
  - *Profile → Authentication → Two-Factor Authentication* → aktifkan (pakai Google
    Authenticator).
  - Di domain: **SSL/TLS → Edge Certificates → Always Use HTTPS** = On.
  - **Security → Bots → Bot Fight Mode** = On.
- Aktifkan **2FA** juga di **Rumahweb**, **DomaiNesia**, **GitHub**, dan email Anda.

---

## Perintah sehari-hari (masuk dulu: `ssh root@IP-VPS`)

| Perintah | Fungsi |
|---|---|
| `presensi-sekolah daftar` | Lihat semua sekolah & masa langganan |
| `presensi-sekolah status` | Cek RAM/disk. **RAM > 80% terus** → upgrade ke Paket M |
| `presensi-sekolah perpanjang smpn1 --hari 365` | Perpanjang langganan |
| `presensi-sekolah nonaktif smpn1` | Belum bayar → mode baca-saja |
| `presensi-sekolah backup --semua` | Backup sekarang |
| `exit` | Keluar dari VPS |

## Bila ada masalah

| Gejala | Coba |
|---|---|
| Halaman Cloudflare **Error 1033** | `systemctl restart cloudflared` |
| **502 / "Server sedang dimulai ulang"** | `systemctl restart presensi@smpn1` (tunggu 30 detik) |
| `presensiku.biz.id/smpn1` **404** | Kode salah, cek `presensi-sekolah daftar` |
| Lupa password admin sekolah | Kirim pesan ke saya; akan dibuatkan perintah reset |
| Tidak bisa SSH sama sekali | clientzone Rumahweb → VPS → **Console/VNC** |

Saat meminta bantuan, kirim **screenshot pesan error**. **Jangan pernah mengirim password atau
file kunci.**
