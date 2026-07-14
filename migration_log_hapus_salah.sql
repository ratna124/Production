-- Jalankan migration ini di database garindra, schema production
-- untuk menambahkan tabel log audit trail penghapusan scan salah.
--
-- Cara jalankan (pilih salah satu):
--   psql -U postgres -d garindra -f migration_log_hapus_salah.sql
--   atau lewat pgAdmin -> Query Tool -> paste isi file ini -> F5

SET search_path TO production;

CREATE TABLE IF NOT EXISTS log_hapus_salah (
    id SERIAL PRIMARY KEY,
    create_at        TEXT,   -- create_at asli dari row scan salah sebelum dihapus
    tanggal          TEXT,
    shift            TEXT,
    divisi           TEXT,
    prefix           TEXT,
    divisi_label     TEXT,
    spk              TEXT,
    customer         TEXT,
    produk           TEXT,
    uk               TEXT,
    checker          TEXT,
    scanned_by       TEXT,
    code             TEXT,
    mesin            TEXT,
    berat_bersih     TEXT,
    keterangan_asli  TEXT,   -- keterangan asli waktu scan salah dibuat
    deleted_by       TEXT,   -- nama admin/adminwip yang menghapus
    keterangan_hapus TEXT,   -- alasan hapus
    deleted_at       TEXT    -- waktu penghapusan
);

CREATE INDEX IF NOT EXISTS idx_log_hapus_salah_code ON log_hapus_salah (UPPER(code));

-- role_adminwip yang menghapus data, jadi butuh INSERT + SELECT ke tabel log ini
GRANT SELECT, INSERT ON log_hapus_salah TO role_adminwip;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA production TO role_adminwip;

-- (opsional) administrator & staff untuk keperluan audit/laporan
GRANT ALL ON log_hapus_salah TO role_administrator;
GRANT SELECT ON log_hapus_salah TO role_staff;

-- Catatan: DELETE ke scansalahmixing, scansalahhd, scansalahpotong,
-- scansalahpacking sudah di-grant ke role_adminwip di schema.sql lama,
-- jadi tidak perlu grant tambahan untuk operasi DELETE-nya.
