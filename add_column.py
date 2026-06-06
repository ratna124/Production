import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE SummarySPK ADD COLUMN order_ball REAL;")
    print("✔ kolom order_ball berhasil ditambahkan")
except Exception as e:
    print("⚠ order_ball:", e)

conn.commit()
conn.close()