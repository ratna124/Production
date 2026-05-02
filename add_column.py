import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogavalqc ADD COLUMN uk REAL;")
    print("✔ kolom uk berhasil ditambahkan")
except Exception as e:
    print("⚠ uk:", e)

conn.commit()
conn.close()