import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogavalpotong ADD COLUMN karung REAL;")
    print("✔ kolom karung berhasil ditambahkan")
except Exception as e:
    print("⚠ karung:", e)

conn.commit()
conn.close()