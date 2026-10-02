# Firmware perangkat tap RFID / scan QR (ESP32 + RC522 + modul QR opsional)

Perangkat mandiri untuk gerbang / musala: siswa menempelkan kartu, hasil tampil di LCD,
bunyi buzzer, dan data langsung masuk ke aplikasi Presensi (lewat internet / WiFi sekolah).

## Belanja (± Rp150–200 rb per perangkat)

| Komponen | Keterangan |
|---|---|
| ESP32 DevKit V1 (30/38 pin) | otak perangkat, ada WiFi |
| Modul RFID **RC522** 13,56 MHz | pembaca kartu MIFARE (kartu 125 kHz **tidak** terbaca) |
| LCD 16×2 + modul **I2C** (PCF8574) | tampilan nama & status |
| Buzzer aktif 5V, LED hijau & merah + 2 resistor 220 Ω | tanda berhasil / gagal |
| Kabel jumper female-female, adaptor USB 5V 2A + kabel micro-USB/USB-C | daya |
| Casing / kotak plastik | opsional |
| Kartu **MIFARE Classic 1K** (13,56 MHz) | kartu siswa |

## Sambungan kabel

| Modul | Pin modul | Pin ESP32 |
|---|---|---|
| RC522 | SDA (SS) | GPIO 5 |
| | SCK | GPIO 18 |
| | MOSI | GPIO 23 |
| | MISO | GPIO 19 |
| | RST | GPIO 4 |
| | 3.3V | **3V3** (jangan ke 5V) |
| | GND | GND |
| LCD I2C | SDA | GPIO 21 |
| | SCL | GPIO 22 |
| | VCC | VIN / 5V |
| | GND | GND |
| Buzzer | + | GPIO 25 (− ke GND) |
| LED hijau | kaki panjang (via 220 Ω) | GPIO 26 |
| LED merah | kaki panjang (via 220 Ω) | GPIO 27 |

## Opsional: modul scanner QR (gerbang jauh tanpa PC)

Tambahkan modul scanner QR UART, misalnya **GM65** atau **GM861** (kata kunci: *GM65 barcode scanner module*,
±Rp150–250 rb). Perangkat lalu bisa membaca **kartu RFID dan QR kartu pelajar** sekaligus.

| Modul QR | Pin ESP32 |
|---|---|
| TX | GPIO 16 |
| RX | GPIO 17 |
| VCC | VIN / 5V |
| GND | GND |

- Atur modul ke **mode keluaran Serial/UART 9600 baud** dengan akhiran **CR** (bawaan GM65). Kalau perlu
  diubah, pindai barcode pengaturan di manual modul.
- Firmware sudah menyalakan pembacaan QR (`PAKAI_QR 1`).
- Gerbang perangkat diatur di aplikasi: **Perangkat ESP32 → Edit → Gerbang**. Nama gerbang ini tampil
  di Layar Gerbang dan rekap.

## Memasang firmware (sekali per perangkat)

1. Pasang **Arduino IDE** (arduino.cc/en/software).
2. *File → Preferences → Additional boards manager URLs*, isi:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. *Tools → Board → Boards Manager* → cari **esp32** (Espressif Systems) → Install.
4. *Tools → Manage Libraries* → install **MFRC522** (GithubCommunity) dan
   **LiquidCrystal I2C** (Frank de Brabander).
5. Buka `firmware/esp32_rfid/esp32_rfid.ino`, pilih board **ESP32 Dev Module** dan port COM
   ESP32, klik **Upload** (→). Bila gagal "Connecting...", tahan tombol **BOOT** saat upload dimulai.
6. Bila LCD menyala tanpa tulisan: putar potensiometer biru di modul I2C, atau ganti
   `LCD_ADDR` menjadi `0x3F` lalu upload ulang.

## Menyetel perangkat

1. Di aplikasi: **Sistem → Perangkat RFID → Tambah perangkat** (pilih mode: Otomatis masuk/pulang,
   Masuk saja, Pulang saja, atau Ibadah) → klik **Isian**.
2. Nyalakan perangkat. Pertama kali (atau tahan tombol **BOOT** 5 detik saat menyala) LCD menampilkan
   `MODE SETELAN 192.168.4.1`.
3. Sambungkan HP ke WiFi **PRESENSI-SETUP** (password `presensi123`), buka **http://192.168.4.1**,
   isi nama & password WiFi sekolah, **alamat server** (alamat publik sekolah, mis.
   `https://smpn1.presensiku.biz.id`), **kode perangkat**, dan **rahasia** → Simpan.
4. Perangkat memulai ulang, tersambung ke server, lalu LCD menampilkan nama sekolah dan
   `Tap kartu Anda`. Titik hijau di menu Perangkat RFID menandakan perangkat online.

## Cara kerja & keamanan

- Setiap permintaan ditandatangani **HMAC-SHA256** dengan rahasia perangkat + waktu + nonce sekali
  pakai; server menolak rahasia salah, permintaan ganda (replay), dan jam meleset > 5 menit
  (perangkat otomatis menyesuaikan jam dari server).
- **Internet putus:** tap disimpan di memori ESP32 (sampai 1.000 tap), LCD menampilkan
  `TERSIMPAN Offline (n)`, lalu dikirim otomatis dengan **jam tap asli** saat internet kembali.
- Kartu yang belum terdaftar muncul di menu **Kartu RFID → Kartu baru yang di-tap** untuk dipasang
  ke siswa.
- Jam perangkat dari NTP (internet); zona waktu sekolah diatur di aplikasi (Pengaturan).

## Uji tanpa alat

`tools/simulasi_perangkat.py` meniru perangkat dengan protokol yang sama:

```bash
python tools/simulasi_perangkat.py --server https://smpn1.presensiku.biz.id \
    --kode ESP-XXXXXX --rahasia <rahasia> tap A1B2C3D4
```

> Catatan: firmware ini belum dikompilasi dengan toolchain ESP32 sungguhan di lingkungan
> pengembang; bila Arduino IDE menampilkan error kompilasi, kirimkan pesan errornya.
