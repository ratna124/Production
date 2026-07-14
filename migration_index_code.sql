-- Migration: tambah index kolom code di tabel yang belum ada index-nya.
-- Aman dijalankan kapan saja, termasuk saat aplikasi sedang jalan/dipakai user lain:
-- CREATE INDEX (tanpa CONCURRENTLY) di PostgreSQL akan mengunci tabel untuk WRITE
-- (INSERT/UPDATE/DELETE) selama index dibuat, tapi tabelnya kecil/menengah biasanya
-- cuma butuh beberapa detik. Kalau mau nol downtime sama sekali, pakai versi
-- CONCURRENTLY di bagian bawah file ini (lihat catatan).
--
-- Cara jalankan:
--   psql -U postgres -d garindra -f migration_index_code.sql
--   atau lewat pgAdmin -> Query Tool -> paste isi file ini -> F5

SET search_path TO production;

-- ─── Scan Pemakaian ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_scanmixing_code  ON scanmixing  (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_scanhd_code       ON scanhd       (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_scanpotong_code   ON scanpotong   (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_scanpacking_code  ON scanpacking  (UPPER(code));

-- ─── Scan Salah (yang belum ada index-nya) ──────────────────
CREATE INDEX IF NOT EXISTS idx_scansalahpotong_code  ON scansalahpotong  (UPPER(code));
CREATE INDEX IF NOT EXISTS idx_scansalahpacking_code ON scansalahpacking (UPPER(code));

-- ============================================================
-- CATATAN: kalau tabelnya sudah besar (jutaan baris) dan kamu
-- tidak mau tabel ke-lock sama sekali walau cuma sebentar, jalankan
-- satu-satu (TIDAK BISA di dalam blok transaksi/psql -f biasa,
-- harus dieksekusi manual satu per satu di luar transaksi):
--
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scanmixing_code  ON scanmixing  (UPPER(code));
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scanhd_code       ON scanhd       (UPPER(code));
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scanpotong_code   ON scanpotong   (UPPER(code));
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scanpacking_code  ON scanpacking  (UPPER(code));
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scansalahpotong_code  ON scansalahpotong  (UPPER(code));
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scansalahpacking_code ON scansalahpacking (UPPER(code));
-- ============================================================
