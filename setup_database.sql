DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_administrator') THEN
        CREATE ROLE role_administrator;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_checker') THEN
        CREATE ROLE role_checker;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_adminwip') THEN
        CREATE ROLE role_adminwip;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_staff') THEN
        CREATE ROLE role_staff;
    END IF;
    -- Role dipakai aplikasi (login DB), bukan role manusia
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'production_user') THEN
        CREATE ROLE production_user LOGIN PASSWORD '372026production_';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA production TO role_administrator, role_checker, role_adminwip, role_staff;

-- administrator: full akses
GRANT role_administrator TO production_user;

-- ─── SET PATH ────────────────────────────────────────────────
SET search_path TO production;

CREATE TABLE IF NOT EXISTS katalogmixing (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_mix TEXT, checker TEXT,
    berat_kg REAL, berat_bersih REAL, karung REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS kataloghd (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
    mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS katalogpotong (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
    mesin REAL, berat_kg REAL, keranjang REAL, berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS katalogsisapotong (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
    mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS katalogpacking (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
    mesin REAL, berat_bersih REAL, created_at TEXT, code TEXT, team TEXT
);

CREATE TABLE IF NOT EXISTS katalogsisapack (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_sp TEXT, checker TEXT,
    mesin REAL, berat_bersih REAL, sisa REAL, created_at TEXT, code TEXT, team TEXT
);

CREATE TABLE IF NOT EXISTS katalogavalmixing (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, operator_amix TEXT, checker TEXT, mesin REAL, karung REAL,
    berat_kg REAL, berat_bersih REAL, jenis TEXT, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS katalogavalhd (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
    mesin REAL, jenis_hd TEXT, kategori_hd TEXT, karung REAL, berat_kg REAL,
    berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS katalogavalpotong (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
    mesin REAL, jenis_cu TEXT, kategori_cu TEXT, karung REAL, berat_kg REAL,
    berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS katalogavalpacking (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
    mesin REAL, jenis_pa TEXT, kategori_pa TEXT, berat_bersih REAL,
    created_at TEXT, code TEXT, team TEXT
);

CREATE TABLE IF NOT EXISTS katalogavalqc (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_qc TEXT, checker TEXT,
    mesin REAL, kategori_qc TEXT, berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS summaryspk (
    spk TEXT, so TEXT, tanggal TEXT, customer TEXT, product TEXT, warna TEXT,
    aval TEXT, uk TEXT, lembar TEXT, pack TEXT, kg TEXT, berat_lembar TEXT,
    berat_pack TEXT, tebal TEXT, order_ball TEXT, qty TEXT, checker TEXT,
    satuan TEXT, blongsong TEXT, etiket TEXT, mixing TEXT
);

-- ─── SCAN PEMAKAIAN per divisi ──────────────────────────────
CREATE TABLE IF NOT EXISTS scanmixing (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scanhd (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scanpotong (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scanpacking (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
);

-- ─── SCAN TRANSFER per divisi ───────────────────────────────
CREATE TABLE IF NOT EXISTS scantransfermixing (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scantransferhd (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scantransferpotong (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scantransferpacking (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
);

-- ─── SCAN SALAH per divisi ──────────────────────────────────
CREATE TABLE IF NOT EXISTS scansalahmixing (
    id SERIAL PRIMARY KEY,
    create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT,
    scanned_by TEXT, code TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS scansalahhd (
    id SERIAL PRIMARY KEY,
    create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT,
    scanned_by TEXT, code TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS scansalahpotong (
    id SERIAL PRIMARY KEY,
    create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT,
    scanned_by TEXT, code TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS scansalahpacking (
    id SERIAL PRIMARY KEY,
    create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT,
    scanned_by TEXT, code TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS scansalahqc (
    id SERIAL PRIMARY KEY,
    create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT,
    scanned_by TEXT, code TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS scan_retur (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT,
    berat_bersih TEXT, keterangan TEXT
);

-- ─── TABEL GABUNGAN ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scan_salah (
    id SERIAL PRIMARY KEY,
    create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT,
    scanned_by TEXT, code TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS scan_pemakaian (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
);

CREATE TABLE IF NOT EXISTS scan_transfer (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
);

-- ─── MUTASI ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mutasimixing (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, code_scan TEXT, code_baru TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    berat_awal REAL, berat_bersih REAL, operator TEXT, checker TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS mutasihd (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, code_scan TEXT, code_baru TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    berat_awal REAL, berat_bersih REAL, operator TEXT, checker TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS mutasipotong (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, code_scan TEXT, code_baru TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    berat_awal REAL, berat_bersih REAL, operator TEXT, checker TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS mutasipacking (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, code_scan TEXT, code_baru TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    berat_awal REAL, berat_bersih REAL, operator TEXT, checker TEXT, keterangan TEXT
);

CREATE TABLE IF NOT EXISTS mutasisisapack (
    id SERIAL PRIMARY KEY,
    create_at TEXT, tanggal TEXT, shift TEXT, code_scan TEXT, code_baru TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    berat_awal REAL, berat_bersih REAL, operator TEXT, checker TEXT, keterangan TEXT
);

-- ─── KARANTINA ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS karantinamixing (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_mix TEXT, checker TEXT,
    berat_kg REAL, berat_bersih REAL, karung REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS karantinahd (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
    mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS karantinapotong (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
    mesin REAL, berat_kg REAL, keranjang REAL, berat_bersih REAL, created_at TEXT, code TEXT
);

CREATE TABLE IF NOT EXISTS karantinapacking (
    id SERIAL PRIMARY KEY,
    order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
    spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
    mesin REAL, berat_bersih REAL, created_at TEXT, code TEXT, team TEXT
);

CREATE INDEX IF NOT EXISTS idx_kataloghd_code ON kataloghd (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_katalogmixing_code ON katalogmixing (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_katalogpotong_code ON katalogpotong (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_katalogpacking_code ON katalogpacking (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_katalogsisapack_code ON katalogsisapack (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_kataloghd_spk ON kataloghd (spk);
CREATE INDEX IF NOT EXISTS idx_katalogmixing_spk ON katalogmixing (spk);
CREATE INDEX IF NOT EXISTS idx_katalogpotong_spk ON katalogpotong (spk);
CREATE INDEX IF NOT EXISTS idx_scansalahmixing_code ON scansalahmixing (code);
CREATE INDEX IF NOT EXISTS idx_scansalahhd_code ON scansalahhd (code);
CREATE INDEX IF NOT EXISTS idx_scantransferhd_code ON scantransferhd (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_scantransferpotong_code ON scantransferpotong (UPPER(code));

-- ─── GRANT ke semua tabel yang baru dibuat ───────────────────
GRANT ALL ON ALL TABLES IN SCHEMA production TO role_administrator;
GRANT ALL ON ALL SEQUENCES IN SCHEMA production TO role_administrator;

-- checker: bisa insert/select tabel input produksi, tidak bisa DELETE data mutasi/retur
GRANT SELECT, INSERT, UPDATE ON
    katalogmixing, kataloghd, katalogpotong, katalogsisapotong, katalogpacking,
    katalogsisapack, katalogavalmixing, katalogavalhd, katalogavalpotong,
    katalogavalpacking, katalogavalqc, karantinamixing, karantinahd,
    karantinapotong, karantinapacking
    TO role_checker;
GRANT SELECT ON summaryspk TO role_checker;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA production TO role_checker;

-- adminwip: akses scan_pemakaian, scan_transfer, scan_salah, mutasi, retur
GRANT SELECT, INSERT, UPDATE, DELETE ON
    scanmixing, scanhd, scanpotong, scanpacking,
    scantransfermixing, scantransferhd, scantransferpotong, scantransferpacking,
    scansalahmixing, scansalahhd, scansalahpotong, scansalahpacking, scansalahqc,
    scan_retur, scan_salah, scan_pemakaian, scan_transfer,
    mutasimixing, mutasihd, mutasipotong, mutasipacking, mutasisisapack,
    summaryspk
    TO role_adminwip;
GRANT SELECT ON
    katalogmixing, kataloghd, katalogpotong, katalogsisapotong, katalogpacking,
    katalogsisapack
    TO role_adminwip;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA production TO role_adminwip;

-- staff: read-only, untuk laporan/stok
GRANT SELECT ON ALL TABLES IN SCHEMA production TO role_staff;

-- Default privileges: supaya tabel baru di masa depan otomatis ke-grant
ALTER DEFAULT PRIVILEGES IN SCHEMA production
    GRANT ALL ON TABLES TO role_administrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA production
    GRANT ALL ON SEQUENCES TO role_administrator;

-- ─── search_path default untuk production_user ────────────────
ALTER ROLE production_user SET search_path = production, public;
