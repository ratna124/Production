import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogavalmixing ADD COLUMN mesin REAL;")
    print("✔ kolom mesin berhasil ditambahkan")
except Exception as e:
    print("⚠ mesin:", e)

conn.commit()
conn.close()