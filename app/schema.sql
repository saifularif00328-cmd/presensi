-- Skema database Presensi Siswa Digital (SQLite)

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ===================== DATA MASTER =====================
CREATE TABLE IF NOT EXISTS tahun_ajaran (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nama            TEXT NOT NULL,              -- mis. 2026/2027
    semester        TEXT NOT NULL,              -- Ganjil / Genap
    tanggal_mulai   TEXT NOT NULL,
    tanggal_selesai TEXT NOT NULL,
    aktif           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guru (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nip      TEXT,
    nama     TEXT NOT NULL,
    jabatan  TEXT,                              -- Guru Mapel, Guru Piket, Guru BK, Staf TU, ...
    no_hp    TEXT,
    aktif    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kelas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nama          TEXT NOT NULL UNIQUE,
    jenjang       TEXT,                         -- mis. 7, 8, 9 / X, XI, XII
    wali_guru_id  INTEGER REFERENCES guru(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS siswa (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nis         TEXT,
    nisn        TEXT,
    nama        TEXT NOT NULL,
    jk          TEXT,                           -- L / P
    kelas_id    INTEGER REFERENCES kelas(id) ON DELETE SET NULL,
    foto        TEXT,
    wa_ayah     TEXT,
    wa_ibu      TEXT,
    wa_wali     TEXT,
    qr_token    TEXT NOT NULL UNIQUE,           -- ID unik di dalam QR (diganti saat kartu dicetak ulang)
    aktif       INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_siswa_kelas ON siswa(kelas_id);

-- ===================== PRESENSI =====================
CREATE TABLE IF NOT EXISTS aturan_jam (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nama                TEXT NOT NULL,
    jenjang             TEXT,                   -- NULL = semua jenjang
    kelas_id            INTEGER REFERENCES kelas(id) ON DELETE CASCADE,  -- NULL = semua kelas
    jam_masuk           TEXT NOT NULL,          -- HH:MM
    batas_telat         TEXT NOT NULL,          -- scan masuk setelah jam ini = Telat
    batas_pulang_cepat  TEXT NOT NULL,          -- mulai jam ini scan (mode otomatis) dihitung absen pulang
    jam_pulang          TEXT NOT NULL,          -- scan pulang sebelum jam ini = Pulang Cepat
    jam_tutup           TEXT NOT NULL           -- sekolah tutup: tandai Belum Pulang & Alpha
);

CREATE TABLE IF NOT EXISTS presensi (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id      INTEGER NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    kelas_id      INTEGER,                      -- snapshot kelas saat presensi (untuk arsip)
    tanggal       TEXT NOT NULL,                -- YYYY-MM-DD
    jam_masuk     TEXT,
    status_masuk  TEXT,                         -- Hadir / Telat
    jam_pulang    TEXT,
    status_pulang TEXT,                         -- Tepat Waktu / Pulang Cepat / Belum Pulang
    keterangan    TEXT NOT NULL DEFAULT 'H',    -- H / I / S / A / D
    sumber        TEXT NOT NULL DEFAULT 'scan', -- scan / manual / izin / otomatis
    catatan       TEXT,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (siswa_id, tanggal)
);
CREATE INDEX IF NOT EXISTS idx_presensi_tanggal ON presensi(tanggal);

-- Log setiap scan (untuk live feed monitor)
CREATE TABLE IF NOT EXISTS scan_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id   INTEGER REFERENCES siswa(id) ON DELETE CASCADE,
    waktu      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    jenis      TEXT NOT NULL,                   -- masuk / pulang / ibadah / peringatan / gagal
    status     TEXT,
    pesan      TEXT,
    metode     TEXT                             -- kamera / scanner / webcam / manual
);
CREATE INDEX IF NOT EXISTS idx_scan_log_waktu ON scan_log(waktu);

-- Penanda proses tutup harian (Belum Pulang / Alpha) agar idempoten
CREATE TABLE IF NOT EXISTS tutup_harian (
    tanggal   TEXT NOT NULL,
    kelas_id  INTEGER NOT NULL,
    waktu     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (tanggal, kelas_id)
);

-- ===================== PERIZINAN =====================
CREATE TABLE IF NOT EXISTS izin (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id         INTEGER NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    jenis            TEXT NOT NULL,             -- Izin / Sakit / Dispensasi
    tanggal_mulai    TEXT NOT NULL,
    tanggal_selesai  TEXT NOT NULL,
    alasan           TEXT,
    lampiran         TEXT,
    status           TEXT NOT NULL DEFAULT 'Menunggu',  -- Menunggu / Disetujui / Ditolak
    diajukan_oleh    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    diproses_oleh    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    catatan_proses   TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    processed_at     TEXT
);

CREATE TABLE IF NOT EXISTS izin_keluar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id     INTEGER NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    tanggal      TEXT NOT NULL,
    jam_keluar   TEXT NOT NULL,
    jam_kembali  TEXT,
    alasan       TEXT NOT NULL,
    pencatat_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS pengajuan_kartu (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id    INTEGER NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    alasan      TEXT NOT NULL,                  -- Hilang / Rusak / Lainnya
    keterangan  TEXT,
    status      TEXT NOT NULL DEFAULT 'Diproses', -- Diproses / Selesai
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    selesai_at  TEXT
);

-- ===================== IBADAH =====================
CREATE TABLE IF NOT EXISTS ibadah (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nama         TEXT NOT NULL,
    jam_mulai    TEXT NOT NULL,
    jam_selesai  TEXT NOT NULL,
    hari         TEXT NOT NULL DEFAULT '1,2,3,4,5', -- ISO weekday, 1 = Senin
    jk           TEXT,                          -- NULL = semua, L / P
    aktif        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS presensi_ibadah (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id   INTEGER NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    ibadah_id  INTEGER NOT NULL REFERENCES ibadah(id) ON DELETE CASCADE,
    tanggal    TEXT NOT NULL,
    jam        TEXT NOT NULL,
    UNIQUE (siswa_id, ibadah_id, tanggal)
);

-- ===================== KEDISIPLINAN =====================
CREATE TABLE IF NOT EXISTS tata_tertib (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    judul   TEXT NOT NULL,
    isi     TEXT,
    urutan  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jenis_pelanggaran (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nama         TEXT NOT NULL,
    kategori     TEXT,                          -- Ringan / Sedang / Berat
    poin         INTEGER NOT NULL DEFAULT 0,
    notif_aktif  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pelanggaran (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id      INTEGER NOT NULL REFERENCES siswa(id) ON DELETE CASCADE,
    jenis_id      INTEGER REFERENCES jenis_pelanggaran(id) ON DELETE SET NULL,
    tanggal       TEXT NOT NULL,
    poin          INTEGER NOT NULL DEFAULT 0,
    keterangan    TEXT,
    tindak_lanjut TEXT,
    pencatat_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ===================== SISTEM =====================
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    nama           TEXT NOT NULL,
    role           TEXT NOT NULL,               -- admin / piket / bk
    guru_id        INTEGER REFERENCES guru(id) ON DELETE SET NULL,
    aktif          INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS libur (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tanggal     TEXT NOT NULL UNIQUE,
    keterangan  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS info (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    judul       TEXT NOT NULL,
    isi         TEXT NOT NULL,
    penting     INTEGER NOT NULL DEFAULT 0,
    aktif       INTEGER NOT NULL DEFAULT 1,
    pembuat_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Enterprise: daftar cabang/sekolah lain untuk dashboard gabungan
CREATE TABLE IF NOT EXISTS cabang (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nama   TEXT NOT NULL,
    url    TEXT NOT NULL,
    token  TEXT NOT NULL
);

-- ===================== NOTIFIKASI WA =====================
CREATE TABLE IF NOT EXISTS notif_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id    INTEGER REFERENCES siswa(id) ON DELETE SET NULL,
    jenis       TEXT NOT NULL,                  -- masuk / pulang / alpha / izin / pelanggaran / tes
    nomor       TEXT NOT NULL,
    pesan       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Menunggu Koneksi', -- Menunggu Koneksi / Terkirim / Gagal
    percobaan   INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_notif_status ON notif_queue(status);
