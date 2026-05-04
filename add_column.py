import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogavalpotong ADD COLUMN berat_kg REAL;")
    print("✔ kolom berat_kg berhasil ditambahkan")
except Exception as e:
    print("⚠ berat_kg:", e)

conn.commit()
conn.close()