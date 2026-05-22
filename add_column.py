import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogpacking ADD COLUMN meja REAL;")
    print("✔ kolom meja berhasil ditambahkan")
except Exception as e:
    print("⚠ meja:", e)

conn.commit()
conn.close()