import sqlite3
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "data", "production.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# ── SCAN PEMAKAIAN (per divisi) ──────────────────────────────
for tabel in ["scanmixing", "scanhd", "scanpotong", "scanpacking"]:
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS {tabel} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
    )""")
    print(f"✓ Tabel {tabel} siap")

# ── SCAN TRANSFER (per divisi) ───────────────────────────────
for tabel in ["scantransfermixing", "scantransferhd", "scantransferpotong", "scantransferpacking"]:
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS {tabel} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
    )""")
    print(f"✓ Tabel {tabel} siap")

# ── SCAN SALAH (per divisi) ──────────────────────────────────
for tabel in ["scansalahmixing", "scansalahhd", "scansalahpotong", "scansalahpacking", "scansalahqc"]:
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS {tabel} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")
    print(f"✓ Tabel {tabel} siap")

# ── SCAN RETUR ───────────────────────────────────────────────
c.execute("""
CREATE TABLE IF NOT EXISTS scan_retur (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
    divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT,
    checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT,
    berat_bersih TEXT, keterangan TEXT
)""")
print("✓ Tabel scan_retur siap")

conn.commit()
conn.close()

print("\n✅ Migrasi selesai. Semua tabel baru berhasil dibuat.")
print("   Data lama tidak tersentuh sama sekali.")