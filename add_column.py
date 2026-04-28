import sqlite3

DB_PATH = r"C:\Coba\data\production.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute("ALTER TABLE katalogmixing ADD COLUMN operator_pa REAL;")
    print("✔ kolom operator_pa berhasil ditambahkan")
except Exception as e:
    print("⚠ operator_pa:", e)

conn.commit()
conn.close()