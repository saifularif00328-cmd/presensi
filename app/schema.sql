-- Skema database Presensi Siswa Digital (MySQL 8 / MariaDB 10.6+)
-- Semua tabel InnoDB + utf8mb4. Aman dijalankan ulang (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS settings (
    kunci  VARCHAR(100) PRIMARY KEY,
    nilai  MEDIUMTEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== DATA MASTER =====================
CREATE TABLE IF NOT EXISTS tahun_ajaran (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    nama            VARCHAR(20) NOT NULL,           -- mis. 2026/2027
    semester        VARCHAR(10) NOT NULL,           -- Ganjil / Genap
    tanggal_mulai   DATE NOT NULL,
    tanggal_selesai DATE NOT NULL,
    aktif           TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS guru (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    nip      VARCHAR(40),
    nama     VARCHAR(150) NOT NULL,
    jabatan  VARCHAR(100),                          -- Guru Mapel, Guru Piket, Guru BK, Staf TU, ...
    no_hp    VARCHAR(30),
    aktif    TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS kelas (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    nama          VARCHAR(50) NOT NULL UNIQUE,
    jenjang       VARCHAR(20),                      -- mis. 7, 8, 9 / X, XI, XII
    wali_guru_id  INT NULL,
    FOREIGN KEY (wali_guru_id) REFERENCES guru(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS siswa (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    nis         VARCHAR(30),
    nisn        VARCHAR(30),
    nama        VARCHAR(150) NOT NULL,
    jk          VARCHAR(1),                         -- L / P
    kelas_id    INT NULL,
    foto        VARCHAR(255),
    wa_ayah     VARCHAR(30),
    wa_ibu      VARCHAR(30),
    wa_wali     VARCHAR(30),
    qr_token    VARCHAR(32) NOT NULL UNIQUE,        -- ID unik di dalam QR (diganti saat kartu dicetak ulang)
    aktif       TINYINT NOT NULL DEFAULT 1,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_siswa_kelas (kelas_id),
    INDEX idx_siswa_nis (nis),
    FOREIGN KEY (kelas_id) REFERENCES kelas(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== SISTEM (dirujuk tabel lain) =====================
CREATE TABLE IF NOT EXISTS users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(64) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    nama           VARCHAR(150) NOT NULL,
    role           VARCHAR(20) NOT NULL,            -- admin / piket / bk
    guru_id        INT NULL,
    aktif          TINYINT NOT NULL DEFAULT 1,
    wajib_ganti    TINYINT NOT NULL DEFAULT 0,      -- 1 = harus ganti password saat login berikutnya
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guru_id) REFERENCES guru(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Percobaan login gagal (kunci = "akun:<username>" / "ip:<alamat>") untuk kunci sementara
CREATE TABLE IF NOT EXISTS login_gagal (
    kunci            VARCHAR(191) PRIMARY KEY,
    jumlah           INT NOT NULL DEFAULT 0,
    pertama          DATETIME NOT NULL,
    terkunci_sampai  DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== PRESENSI =====================
CREATE TABLE IF NOT EXISTS aturan_jam (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    nama                VARCHAR(100) NOT NULL,
    jenjang             VARCHAR(20),                -- NULL = semua jenjang
    kelas_id            INT NULL,                   -- NULL = semua kelas
    jam_masuk           VARCHAR(8) NOT NULL,        -- HH:MM
    batas_telat         VARCHAR(8) NOT NULL,        -- scan masuk setelah jam ini = Telat
    batas_pulang_cepat  VARCHAR(8) NOT NULL,        -- mulai jam ini scan (mode otomatis) dihitung absen pulang
    jam_pulang          VARCHAR(8) NOT NULL,        -- scan pulang sebelum jam ini = Pulang Cepat
    jam_tutup           VARCHAR(8) NOT NULL,        -- sekolah tutup: tandai Belum Pulang & Alpha
    FOREIGN KEY (kelas_id) REFERENCES kelas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS presensi (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id      INT NOT NULL,
    kelas_id      INT NULL,                         -- snapshot kelas saat presensi (untuk arsip)
    tanggal       DATE NOT NULL,
    jam_masuk     VARCHAR(8),
    status_masuk  VARCHAR(20),                      -- Hadir / Telat
    jam_pulang    VARCHAR(8),
    status_pulang VARCHAR(20),                      -- Tepat Waktu / Pulang Cepat / Belum Pulang
    keterangan    VARCHAR(1) NOT NULL DEFAULT 'H',  -- H / I / S / A / D
    sumber        VARCHAR(20) NOT NULL DEFAULT 'scan', -- scan / manual / izin / otomatis
    catatan       TEXT,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_presensi (siswa_id, tanggal),
    INDEX idx_presensi_tanggal (tanggal),
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Log setiap scan (untuk live feed monitor)
CREATE TABLE IF NOT EXISTS scan_log (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id   INT NULL,
    waktu      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    jenis      VARCHAR(20) NOT NULL,                -- masuk / pulang / ibadah / peringatan / gagal
    status     VARCHAR(50),
    pesan      TEXT,
    metode     VARCHAR(20),                         -- kamera / scanner / rfid / webcam / manual
    INDEX idx_scan_log_waktu (waktu),
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Penanda proses tutup harian (Belum Pulang / Alpha) agar idempoten
CREATE TABLE IF NOT EXISTS tutup_harian (
    tanggal   DATE NOT NULL,
    kelas_id  INT NOT NULL,
    waktu     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tanggal, kelas_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== PERIZINAN =====================
CREATE TABLE IF NOT EXISTS izin (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id         INT NOT NULL,
    jenis            VARCHAR(20) NOT NULL,          -- Izin / Sakit / Dispensasi
    tanggal_mulai    DATE NOT NULL,
    tanggal_selesai  DATE NOT NULL,
    alasan           TEXT,
    lampiran         VARCHAR(255),
    status           VARCHAR(20) NOT NULL DEFAULT 'Menunggu',  -- Menunggu / Disetujui / Ditolak
    diajukan_oleh    INT NULL,
    diproses_oleh    INT NULL,
    catatan_proses   TEXT,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at     DATETIME NULL,
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,
    FOREIGN KEY (diajukan_oleh) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (diproses_oleh) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS izin_keluar (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id     INT NOT NULL,
    tanggal      DATE NOT NULL,
    jam_keluar   VARCHAR(8) NOT NULL,
    jam_kembali  VARCHAR(8),
    alasan       TEXT NOT NULL,
    pencatat_id  INT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,
    FOREIGN KEY (pencatat_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pengajuan_kartu (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id    INT NOT NULL,
    alasan      VARCHAR(50) NOT NULL,               -- Hilang / Rusak / Lainnya
    keterangan  TEXT,
    status      VARCHAR(20) NOT NULL DEFAULT 'Diproses', -- Diproses / Selesai
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    selesai_at  DATETIME NULL,
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== IBADAH =====================
CREATE TABLE IF NOT EXISTS ibadah (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    nama         VARCHAR(100) NOT NULL,
    jam_mulai    VARCHAR(8) NOT NULL,
    jam_selesai  VARCHAR(8) NOT NULL,
    hari         VARCHAR(20) NOT NULL DEFAULT '1,2,3,4,5', -- ISO weekday, 1 = Senin
    jk           VARCHAR(1),                        -- NULL = semua, L / P
    aktif        TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS presensi_ibadah (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id   INT NOT NULL,
    ibadah_id  INT NOT NULL,
    tanggal    DATE NOT NULL,
    jam        VARCHAR(8) NOT NULL,
    UNIQUE KEY uq_presensi_ibadah (siswa_id, ibadah_id, tanggal),
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,
    FOREIGN KEY (ibadah_id) REFERENCES ibadah(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== KEDISIPLINAN =====================
CREATE TABLE IF NOT EXISTS tata_tertib (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    judul   VARCHAR(200) NOT NULL,
    isi     TEXT,
    urutan  INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jenis_pelanggaran (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    nama         VARCHAR(200) NOT NULL,
    kategori     VARCHAR(20),                       -- Ringan / Sedang / Berat
    poin         INT NOT NULL DEFAULT 0,
    notif_aktif  TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pelanggaran (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id      INT NOT NULL,
    jenis_id      INT NULL,
    tanggal       DATE NOT NULL,
    poin          INT NOT NULL DEFAULT 0,
    keterangan    TEXT,
    tindak_lanjut TEXT,
    pencatat_id   INT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,
    FOREIGN KEY (jenis_id) REFERENCES jenis_pelanggaran(id) ON DELETE SET NULL,
    FOREIGN KEY (pencatat_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== SISTEM =====================
CREATE TABLE IF NOT EXISTS libur (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    tanggal     DATE NOT NULL UNIQUE,
    keterangan  VARCHAR(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS info (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    judul       VARCHAR(200) NOT NULL,
    isi         TEXT NOT NULL,
    penting     TINYINT NOT NULL DEFAULT 0,
    aktif       TINYINT NOT NULL DEFAULT 1,
    pembuat_id  INT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pembuat_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Daftar cabang/sekolah lain untuk dashboard gabungan
CREATE TABLE IF NOT EXISTS cabang (
    id     INT AUTO_INCREMENT PRIMARY KEY,
    nama   VARCHAR(150) NOT NULL,
    url    VARCHAR(255) NOT NULL,
    token  VARCHAR(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================== NOTIFIKASI WA =====================
CREATE TABLE IF NOT EXISTS notif_queue (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    siswa_id    INT NULL,
    jenis       VARCHAR(20) NOT NULL,               -- masuk / pulang / alpha / izin / pelanggaran / tes
    nomor       VARCHAR(30) NOT NULL,
    pesan       TEXT NOT NULL,
    status      VARCHAR(30) NOT NULL DEFAULT 'Menunggu Koneksi', -- Menunggu Koneksi / Terkirim / Gagal
    percobaan   INT NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at     DATETIME NULL,
    INDEX idx_notif_status (status),
    FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
