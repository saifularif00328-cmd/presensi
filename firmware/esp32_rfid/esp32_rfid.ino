/*
  Presensi Siswa Digital — perangkat tap RFID (ESP32 + RC522 + LCD 16x2 I2C)
  ---------------------------------------------------------------------------
  - Tap kartu MIFARE 13,56 MHz -> dikirim ke server lewat HTTPS (ditandatangani HMAC-SHA256)
  - Hasil tampil di LCD + bunyi buzzer + LED hijau/merah
  - Internet putus: tap disimpan di memori (LittleFS) dan dikirim otomatis dengan jam tap asli
  - Setelan pertama kali (atau tahan tombol BOOT 5 detik saat menyala):
      sambungkan HP ke WiFi "PRESENSI-SETUP" (password: presensi123), buka http://192.168.4.1

  Library (Arduino IDE > Tools > Manage Libraries):
    - "MFRC522" by GithubCommunity
    - "LiquidCrystal I2C" by Frank de Brabander
  Board: "ESP32 Dev Module" (paket board esp32 by Espressif Systems, versi 2.x atau 3.x)

  Sambungan kabel:
    RC522  SDA(SS)->GPIO5  SCK->GPIO18  MOSI->GPIO23  MISO->GPIO19  RST->GPIO4  3.3V->3V3  GND->GND
    LCD    SDA->GPIO21  SCL->GPIO22  VCC->5V(VIN)  GND->GND   (alamat I2C 0x27, atau 0x3F)
    Buzzer (+)->GPIO25   LED hijau->GPIO26 (via resistor 220 ohm)   LED merah->GPIO27 (220 ohm)
*/
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>
#include <LittleFS.h>
#include <SPI.h>
#include <Wire.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>
#include <time.h>
#include "mbedtls/md.h"

#define VERSI        "1.0.0"
#define PIN_SS       5
#define PIN_RST      4
#define PIN_BUZZER   25
#define PIN_LED_OK   26
#define PIN_LED_ERR  27
#define PIN_SETEL    0      // tombol BOOT
#define LCD_ADDR     0x27   // ganti 0x3F bila LCD tidak tampil
#define ANTREAN_FILE "/antrean.txt"
#define MAKS_ANTREAN 1000

MFRC522 rfid(PIN_SS, PIN_RST);
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);
Preferences pref;
WebServer web(80);

String cfgSsid, cfgPass, cfgServer, cfgKode, cfgRahasia;
long offsetJam = 0;               // koreksi jam dari server (detik)
String uidTerakhir;
unsigned long msTerakhir = 0, msPing = 0, msKirimAntrean = 0, msLayarDiam = 0;
bool layarDiam = true;

// ------------------------------------------------------------------ LCD, buzzer, LED
void tampil(const String &b1, const String &b2) {
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(b1.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(b2.substring(0, 16));
}

void bunyi(const String &nada) {
  int led = (nada == "ok") ? PIN_LED_OK : PIN_LED_ERR;
  digitalWrite(led, HIGH);
  if (nada == "ok") {                       // satu bip pendek
    tone(PIN_BUZZER, 2200, 120); delay(150);
  } else if (nada == "warn") {              // dua bip
    tone(PIN_BUZZER, 1600, 100); delay(160); tone(PIN_BUZZER, 1600, 100); delay(160);
  } else {                                  // bip panjang rendah
    tone(PIN_BUZZER, 600, 450); delay(480);
  }
  digitalWrite(led, LOW);
}

void layarSiap() {
  tampil("Tap kartu Anda", WiFi.status() == WL_CONNECTED ? "Online" : "Offline - disimpan");
  layarDiam = true;
}

// ------------------------------------------------------------------ waktu (NTP)
bool jamValid() { return time(nullptr) > 1700000000; }
long sekarang() { return (long)time(nullptr) + offsetJam; }

// ------------------------------------------------------------------ HMAC-SHA256 (hex)
String hmacHex(const String &kunci, const String &pesan) {
  byte out[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char *)kunci.c_str(), kunci.length());
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)pesan.c_str(), pesan.length());
  mbedtls_md_hmac_finish(&ctx, out);
  mbedtls_md_free(&ctx);
  String hex;
  char b[3];
  for (int i = 0; i < 32; i++) { sprintf(b, "%02x", out[i]); hex += b; }
  return hex;
}

String nonceBaru() {
  char b[17];
  sprintf(b, "%08x%08x", (unsigned)esp_random(), (unsigned)esp_random());
  return String(b);
}

// Ambil nilai string/angka sederhana dari JSON respons server (tanpa library tambahan)
String jsonAmbil(const String &json, const String &kunci) {
  int i = json.indexOf("\"" + kunci + "\"");
  if (i < 0) return "";
  i = json.indexOf(':', i);
  if (i < 0) return "";
  i++;
  while (i < (int)json.length() && json[i] == ' ') i++;
  if (i < (int)json.length() && json[i] == '"') {
    String v;
    for (int j = i + 1; j < (int)json.length(); j++) {
      char c = json[j];
      if (c == '\\' && j + 1 < (int)json.length()) { v += json[++j]; continue; }
      if (c == '"') break;
      v += c;
    }
    return v;
  }
  int j = i;
  while (j < (int)json.length() && json[j] != ',' && json[j] != '}') j++;
  String v = json.substring(i, j);
  v.trim();
  return v;
}

// ------------------------------------------------------------------ kirim ke server
// Mengembalikan kode HTTP (<= 0 = gagal jaringan). Respons disimpan di `respons`.
int kirim(const String &path, const String &body, String &respons) {
  if (WiFi.status() != WL_CONNECTED || !jamValid()) return -1;
  String waktu = String(sekarang());
  String nonce = nonceBaru();
  String tanda = hmacHex(cfgRahasia, cfgKode + "\n" + waktu + "\n" + nonce + "\n" + body);
  String url = cfgServer + path;
  HTTPClient http;
  WiFiClientSecure tls;
  WiFiClient polos;
  if (url.startsWith("https://")) {
    // Keaslian permintaan dijamin tanda tangan HMAC; sertifikat server tidak diperiksa
    // agar perangkat tidak perlu diperbarui saat sertifikat berganti.
    tls.setInsecure();
    http.begin(tls, url);
  } else {
    http.begin(polos, url);
  }
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Perangkat", cfgKode);
  http.addHeader("X-Waktu", waktu);
  http.addHeader("X-Nonce", nonce);
  http.addHeader("X-Tanda", tanda);
  http.addHeader("X-Versi", VERSI);
  int kode = http.POST(body);
  respons = kode > 0 ? http.getString() : "";
  http.end();
  // jam perangkat meleset: sesuaikan dengan jam server lalu coba sekali lagi
  if (kode == 401 && jsonAmbil(respons, "error") == "waktu") {
    long st = jsonAmbil(respons, "server_time").toInt();
    if (st > 0) offsetJam = st - (long)time(nullptr);
  }
  return kode;
}

// ------------------------------------------------------------------ antrean offline
int jumlahAntrean() {
  File f = LittleFS.open(ANTREAN_FILE, "r");
  if (!f) return 0;
  int n = 0;
  while (f.available()) { if (f.read() == '\n') n++; }
  f.close();
  return n;
}

void simpanAntrean(const String &uid, long ts) {
  if (jumlahAntrean() >= MAKS_ANTREAN) return;
  File f = LittleFS.open(ANTREAN_FILE, "a");
  if (!f) return;
  f.printf("%s,%ld\n", uid.c_str(), ts);
  f.close();
}

// Kirim antrean satu per satu; berhenti saat jaringan gagal lagi.
void kirimAntrean() {
  if (!LittleFS.exists(ANTREAN_FILE)) return;
  File f = LittleFS.open(ANTREAN_FILE, "r");
  if (!f) return;
  String sisa;
  bool putus = false;
  while (f.available()) {
    String baris = f.readStringUntil('\n');
    baris.trim();
    if (!baris.length()) continue;
    if (putus) { sisa += baris + "\n"; continue; }
    int k = baris.indexOf(',');
    String body = "{\"uid\":\"" + baris.substring(0, k) + "\",\"ts\":" + baris.substring(k + 1) + "}";
    String resp;
    int kode = kirim("/api/perangkat/tap", body, resp);
    if (kode <= 0 || kode == 401 || kode == 402 || kode >= 500) {
      // gagal jaringan / jam belum cocok / langganan habis / server bermasalah: simpan, coba lagi nanti
      putus = true;
      sisa += baris + "\n";
    }
    // kode lain (200 tercatat, 409 ganda, dll.): sudah dijawab server -> hapus dari antrean
  }
  f.close();
  if (sisa.length()) {
    File w = LittleFS.open(ANTREAN_FILE, "w");
    w.print(sisa);
    w.close();
  } else {
    LittleFS.remove(ANTREAN_FILE);
  }
}

// ------------------------------------------------------------------ proses tap
void prosesTap(const String &uid) {
  long ts = jamValid() ? sekarang() : 0;
  tampil("Memproses...", uid);
  String resp;
  String body = "{\"uid\":\"" + uid + "\",\"ts\":" + String(ts) + "}";
  int kode = kirim("/api/perangkat/tap", body, resp);
  if (kode == 401 && jsonAmbil(resp, "error") == "waktu") kode = kirim("/api/perangkat/tap", body, resp);
  if (kode == 200 || kode == 402 || (kode >= 400 && kode < 500 && resp.length())) {
    tampil(jsonAmbil(resp, "baris1"), jsonAmbil(resp, "baris2"));
    String nada = jsonAmbil(resp, "nada");
    bunyi(nada.length() ? nada : (kode == 200 ? "ok" : "err"));
  } else {
    simpanAntrean(uid, ts);
    tampil("TERSIMPAN", "Offline (" + String(jumlahAntrean()) + ")");
    bunyi("ok");
  }
  msLayarDiam = millis();
  layarDiam = false;
}

// ------------------------------------------------------------------ halaman setelan (AP)
String escHtml(const String &s) {
  String o = s;
  o.replace("&", "&amp;"); o.replace("\"", "&quot;"); o.replace("<", "&lt;");
  return o;
}

void halamanSetelan() {
  String h = F("<!doctype html><meta name=viewport content='width=device-width'>"
               "<title>Setelan Perangkat Presensi</title><style>body{font-family:sans-serif;"
               "max-width:420px;margin:24px auto;padding:0 16px}input{width:100%;padding:8px;"
               "margin:4px 0 12px;box-sizing:border-box}button{padding:10px 18px}</style>"
               "<h2>Setelan Perangkat Presensi</h2><form method=post action=/simpan>");
  h += "<label>Nama WiFi sekolah</label><input name=ssid value=\"" + escHtml(cfgSsid) + "\">";
  h += "<label>Password WiFi</label><input name=pass type=password value=\"" + escHtml(cfgPass) + "\">";
  h += "<label>Alamat server (https://sekolah.presensiku.biz.id)</label><input name=server value=\"" + escHtml(cfgServer) + "\">";
  h += "<label>Kode perangkat</label><input name=kode value=\"" + escHtml(cfgKode) + "\">";
  h += "<label>Rahasia</label><input name=rahasia value=\"" + escHtml(cfgRahasia) + "\">";
  h += F("<button>Simpan &amp; mulai ulang</button></form>"
         "<p>Kode perangkat &amp; rahasia ada di aplikasi: Sistem &rarr; Perangkat RFID &rarr; Isian.</p>");
  web.send(200, "text/html", h);
}

void simpanSetelan() {
  pref.begin("presensi", false);
  pref.putString("ssid", web.arg("ssid"));
  pref.putString("pass", web.arg("pass"));
  String srv = web.arg("server");
  srv.trim();
  while (srv.endsWith("/")) srv.remove(srv.length() - 1);
  pref.putString("server", srv);
  pref.putString("kode", web.arg("kode"));
  pref.putString("rahasia", web.arg("rahasia"));
  pref.end();
  web.send(200, "text/html", "<meta name=viewport content='width=device-width'>"
                             "<h3>Tersimpan. Perangkat memulai ulang...</h3>");
  delay(1500);
  ESP.restart();
}

void modeSetelan() {
  WiFi.mode(WIFI_AP);
  WiFi.softAP("PRESENSI-SETUP", "presensi123");
  tampil("MODE SETELAN", "192.168.4.1");
  web.on("/", HTTP_GET, halamanSetelan);
  web.on("/simpan", HTTP_POST, simpanSetelan);
  web.begin();
  while (true) { web.handleClient(); delay(2); }
}

// ------------------------------------------------------------------ setup & loop
void muatSetelan() {
  pref.begin("presensi", true);
  cfgSsid = pref.getString("ssid", "");
  cfgPass = pref.getString("pass", "");
  cfgServer = pref.getString("server", "");
  cfgKode = pref.getString("kode", "");
  cfgRahasia = pref.getString("rahasia", "");
  pref.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_OK, OUTPUT);
  pinMode(PIN_LED_ERR, OUTPUT);
  pinMode(PIN_SETEL, INPUT_PULLUP);
  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  tampil("Presensi RFID", "Versi " VERSI);
  LittleFS.begin(true);
  SPI.begin();
  rfid.PCD_Init();
  muatSetelan();

  // tahan tombol BOOT 5 detik saat menyala = masuk mode setelan
  unsigned long t0 = millis();
  bool tahan = digitalRead(PIN_SETEL) == LOW;
  while (tahan && millis() - t0 < 5000) { tahan = digitalRead(PIN_SETEL) == LOW; delay(50); }
  if (tahan || cfgSsid == "" || cfgServer == "" || cfgKode == "" || cfgRahasia == "") modeSetelan();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(cfgSsid.c_str(), cfgPass.c_str());
  tampil("Menghubungkan", cfgSsid);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
  // jam dari NTP (UTC); zona waktu sekolah diurus server
  configTime(0, 0, "pool.ntp.org", "time.google.com", "id.pool.ntp.org");
  for (int i = 0; i < 40 && !jamValid(); i++) delay(250);
  String resp;
  if (kirim("/api/perangkat/ping", "{}", resp) == 200) {
    tampil(jsonAmbil(resp, "baris1"), jsonAmbil(resp, "baris2"));
    bunyi("ok");
    delay(1500);
  } else if (resp.length()) {
    tampil("Server menolak", jsonAmbil(resp, "pesan"));
    bunyi("err");
    delay(3000);
  }
  layarSiap();
}

void loop() {
  unsigned long ms = millis();
  if (!layarDiam && ms - msLayarDiam > 3500) layarSiap();

  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String uid;
    char b[3];
    for (byte i = 0; i < rfid.uid.size; i++) { sprintf(b, "%02X", rfid.uid.uidByte[i]); uid += b; }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    if (uid != uidTerakhir || ms - msTerakhir > 3000) {   // abaikan tap ganda < 3 detik
      uidTerakhir = uid;
      msTerakhir = ms;
      prosesTap(uid);
    }
  }

  if (ms - msKirimAntrean > 15000) {
    msKirimAntrean = ms;
    if (WiFi.status() == WL_CONNECTED) kirimAntrean();
  }
  if (ms - msPing > 60000 && layarDiam) {                 // detak jantung ke server
    msPing = ms;
    String resp;
    kirim("/api/perangkat/ping", "{}", resp);
    layarSiap();
  }
  delay(20);
}
