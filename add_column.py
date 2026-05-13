import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogsisapack ADD COLUMN team REAL;")
    print("✔ kolom team berhasil ditambahkan")
except Exception as e:
    print("⚠ team:", e)

conn.commit()
conn.close()