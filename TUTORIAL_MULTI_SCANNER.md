# Panduan Multi-Scanner — banyak scanner di satu PC dengan Presensiku Pos

Dengan **Presensiku Pos**, satu PC/laptop Windows di pos satpam atau piket bisa memakai **2, 3, atau
lebih scanner sekaligus**. Scan yang terjadi bersamaan **tidak saling tercampur**.

Yang didukung:
- scanner QR/barcode USB biasa (mode keyboard);
- reader RFID USB murah;
- scanner nirkabel 2,4 GHz;
- scanner mode COM.

Fitur utamanya:
- **Layar Gerbang:** satu monitor dibagi per gerbang, menampilkan foto, nama, dan status siswa,
  dengan suara yang bisa dinyalakan atau dimatikan.
- **Tetap jalan saat internet putus:** scan disimpan di PC, lalu dikirim otomatis begitu internet
  kembali (jam scan tetap sesuai jam asli).

```
Scanner 1 (Gerbang Depan) ─┐
Scanner 2 (Gerbang Depan) ─┼─ USB/hub ─► PC Pos (Presensiku Pos) ─► presensiku.biz.id/sekolah
Scanner 3 nirkabel (Belakang)┘                │
                                               └─► Layar Gerbang (monitor, panel per gerbang + suara)
ESP32 RFID/QR (gedung lain) ── WiFi ─────────────────────────────► server (tanpa PC)
```

---

## 1. Daftar belanja
Harga di bawah adalah perkiraan; cek ulang di marketplace.

| Kebutuhan | Kata kunci pencarian | Perkiraan | Catatan |
|---|---|---|---|
| Scanner QR untuk gerbang (disarankan) | **2D barcode scanner desktop / presentation / omnidirectional** | Rp350–700 rb | Siswa cukup menyodorkan kartu di bawahnya. **Wajib "2D"** (versi "1D/laser" tidak bisa membaca QR). |
| Scanner QR genggam | **2D barcode scanner USB** | Rp200–400 rb | Merek umum: Netum, Eyoyo, Blueprint, Panda |
| Scanner QR jarak jauh tanpa kabel | **2D wireless barcode scanner 2.4G** | Rp300–600 rb | Dongle dicolok ke PC. Jangkauan 30–100 m di area terbuka; dinding mengurangi jangkauan. |
| Reader kartu RFID | **RFID reader USB 13.56 MHz MIFARE** | Rp80–150 rb | Frekuensi **harus 13,56 MHz**, sama dengan kartu (125 kHz tidak cocok) |
| Banyak scanner di 1 PC | **USB hub dengan adaptor (powered)** | Rp80–150 rb | Hub tanpa adaptor sering kurang daya untuk 3+ scanner |
| Jarak 5–25 m | **Kabel USB extension aktif** 10/15/20 m | Rp100–250 rb | Pilih yang ada penguat (ada kotak kecil/IC di kabel) |
| Jarak 20–50 m | **USB extender RJ45 (lewat kabel LAN)** | Rp150–400 rb/pasang | + kabel LAN Cat6 |
| Gedung lain / sangat jauh | **ESP32 + RC522** atau **ESP32 + modul QR GM65/GM861** | Rp100–300 rb | Tanpa PC; lihat `firmware/README.md` |

**Contoh paket untuk 1 PC dan 3 gerbang (±Rp1–1,8 juta):**
- 2 scanner 2D desktop untuk gerbang dekat pos;
- 1 scanner 2D nirkabel (atau kabel extension aktif) untuk gerbang yang 20 m;
- 1 USB hub berdaya.

## 2. Setelan scanner (sekali, sebelum dipakai)
Kebanyakan scanner sudah siap pakai. Kalau perlu diubah, caranya dengan **memindai barcode
pengaturan** yang ada di buku manual scanner.

| Setelan | Nilai yang dibutuhkan |
|---|---|
| Mode antarmuka | **USB HID Keyboard** (bawaan), *atau* **USB Virtual COM / CDC** — keduanya didukung |
| Akhiran (suffix) | **Enter / CR** (bawaan hampir semua scanner) |
| Tata letak keyboard | **US English** |
| Jenis kode | **QR Code** aktif (scanner 2D) |

- Scanner **tanpa akhiran Enter** tetap bisa dipakai, karena Pos mengenali rangkaian ketikan yang
  sangat cepat. Tetapi Enter lebih andal.
- Reader RFID USB murah mengetik nomor kartu sebagai **angka desimal** atau **heksadesimal**. Aplikasi
  mengenali keduanya, jadi kartu yang sama tetap dikenali di ESP32.
- Scanner mode "Alt+Numpad" **tidak** didukung. Ubah ke mode keyboard biasa.

## 3. Di aplikasi sekolah (admin)
1. **Sistem → Perangkat Scan → Gerbang:** tambahkan gerbang, misalnya *Gerbang Depan* dan *Gerbang
   Belakang*. Untuk tiap gerbang pilih mode:
   - **Otomatis:** scan pertama = masuk, scan setelah jam pulang = pulang;
   - **Masuk saja** atau **Pulang saja**.
2. **Tambah PC Pos:** isi nama (mis. *PC Pos Satpam*) → **Buat kode pasang**. Catat **alamat server** dan
   **kode pasang**. Kodenya sekali pakai dan berlaku 30 menit.
3. Bila perlu, atur **Abaikan scan ganda dalam … detik** (bawaan 60). Siswa yang men-scan dua kali
   atau di dua gerbang dalam waktu itu tidak tercatat dobel.

## 4. Di PC pos (Windows 10/11)
1. Unduh **Presensiku Pos** (tautan di halaman *Perangkat Scan*:
   `https://presensiku.biz.id/unduh/presensiku-pos-setup.exe`) → jalankan → **Next** sampai selesai.
   - Bila muncul *"Windows protected your PC"*: klik **More info → Run anyway**. Ini terjadi karena
     aplikasinya baru dan belum bertanda tangan digital.
2. Layar **Pasang Presensiku Pos** terbuka otomatis. Isi alamat server sekolah
   (mis. `presensiku.biz.id/smpn1`) dan kode pasang → **Pasangkan**.
3. Colokkan semua scanner (lewat hub bila perlu).
4. **Scan satu kartu dengan tiap scanner.** Akan muncul *"Scanner baru terdeteksi — pasang di gerbang
   mana?"*. Klik gerbangnya. Scan tadi langsung diproses.
   - Bila yang muncul ternyata keyboard biasa, klik **Abaikan**.
5. Klik **▶ Mulai layar gerbang** (agar suara bisa diputar), lalu **⛶ Layar penuh**.

**Setelah terpasang:**
- Presensiku Pos **berjalan otomatis setiap Windows menyala**.
- Ikon **Layar Gerbang** di desktop membuka layarnya kembali.
- Pengaturan suara ada di bilah atas layar: **🔊 Suara** (semua), **Sebut nama / Bip saja**, dan 🔊 per
  gerbang di pojok tiap panel. Pilihan ini diingat di PC tersebut.

> **Penting:** ketikan scanner juga "terketik" di jendela yang sedang aktif. Karena itu jadikan PC pos
> **khusus untuk Layar Gerbang** (layar ini mengabaikan ketikan). Bila petugas sedang membuka Word,
> isi kartu bisa ikut tertulis di Word.

## 5. Arti tampilan Layar Gerbang
| Label | Arti |
|---|---|
| **HADIR** (hijau) | Absen masuk tepat waktu |
| **TELAT** / **PULANG CEPAT** (kuning) | Tercatat dengan status tersebut |
| **PULANG** (hijau) | Absen pulang |
| **SUDAH ABSEN** (kuning) | Sudah absen masuk/pulang sebelumnya |
| **SUDAH TERCATAT** (biru) | Scan ganda dalam beberapa detik — diabaikan |
| **TERSIMPAN** (hijau) | Internet putus — tersimpan di PC, dikirim otomatis nanti |
| **DITOLAK** (merah) | Kartu tidak dikenal / diblokir / QR bukan kartu sekolah ini |

Bilah atas menampilkan status koneksi:
- **Online**, atau **Offline · n scan tersimpan** saat internet putus;
- jumlah scan yang sedang dikirim.

## 6. Bila ada masalah
| Gejala | Coba |
|---|---|
| Scan tidak muncul sama sekali | Cabut-colok scanner. Pastikan scanner berbunyi "bip" (berarti membaca). Coba scan di Notepad: harus muncul tulisan lalu pindah baris. |
| Muncul "Scanner baru terdeteksi" lagi setelah pindah port USB | Wajar untuk scanner tanpa nomor seri. Pilih gerbangnya lagi, lalu hapus entri lama di *Perangkat Scan*. |
| Keyboard laptop ikut ditanya | Klik **Abaikan**. Ketikan manusia biasa tidak pernah ditanya; yang ditanya hanya ketikan secepat scanner. |
| Scanner COM tidak terbaca | Pastikan tidak dibuka program lain. Kecepatan bawaan 9600 baud. |
| "Offline" terus | Cek internet PC. Scan tetap aman tersimpan; status *n scan tersimpan* akan berkurang sendiri saat online. |
| "Pos ditolak server" | Admin menekan *Kode pasang baru* atau menonaktifkan Pos. Pasangkan ulang. |
| Suara tidak keluar | Klik **▶ Mulai layar gerbang**. Periksa tombol 🔊 dan volume Windows. Suara "sebut nama" memakai suara bahasa Indonesia Windows (Settings → Time & language → Speech). |
| Ganti PC | Instal di PC baru → admin klik **Kode pasang baru** → pasangkan → scan sekali per scanner untuk memilih gerbang. |

Catatan log ada di `C:\ProgramData\PresensikuPos\pos.log`.

## 7. Checklist uji coba di sekolah pilot
- [ ] Pos terpasang, Layar Gerbang tampil nama sekolah & semua gerbang
- [ ] Tiap scanner dipetakan ke gerbang yang benar
- [ ] 3 scanner discan **bersamaan** → 3 siswa tercatat benar di gerbangnya masing-masing (cek Monitor Live / Rekap kolom gerbang)
- [ ] Scan ganda (siswa sama dalam 60 detik di gerbang lain) → "SUDAH TERCATAT", tidak dobel di rekap
- [ ] Kartu RFID USB dan kartu yang sama di ESP32 dikenali sebagai siswa yang sama
- [ ] Cabut kabel internet → scan 5 kartu → tampil "TERSIMPAN" → colok lagi → dalam 1 menit tercatat di server dengan **jam asli**
- [ ] Matikan PC saat ada scan tersimpan → nyalakan → tetap terkirim
- [ ] Suara: matikan semua, matikan per gerbang, mode "Bip saja"
- [ ] Notifikasi WA orang tua terkirim untuk scan dari Pos
- [ ] Jarak 20 m (kabel extension aktif / nirkabel / ESP32) stabil selama 1 hari sekolah
- [ ] Keyboard laptop tidak mengganggu (ketikan biasa tidak tercatat sebagai scan)

---

### Untuk vendor: menerbitkan versi Pos baru
1. Buka GitHub → **Actions → Presensiku Pos (Windows)** → run terbaru → unduh artifact
   `presensiku-pos-setup`.
2. Kirim ke VPS: `scp presensiku-pos-setup.exe root@IP-VPS:/root/`
3. Di VPS: `presensi-sekolah pasang-pos /root/presensiku-pos-setup.exe --versi 1.0.0`.
   Pos lama akan menampilkan pemberitahuan "versi baru tersedia".
