# Factory Label System
**Sistem Input Output Produksi + QR Label Printer**

Menggantikan proses Excel yang lambat dan error-prone dengan sistem web ringan berbasis lokal.
Data disimpan otomatis ke SQLite + CSV setiap kali label dicetak — tanpa copy-paste manual.

---

## Fitur
- **Form input** berbasis web (tablet/PC di lantai produksi)
- **QR code** dibuat otomatis dari data order
- **Label PNG** digenerate dan dikirim langsung ke printer
- **CSV** ditambahkan otomatis setiap submit (no manual copy-paste)
- **SQLite DB** — bisa disambung langsung ke Metabase
- **History page** dengan filter tanggal, shift, divisi
- **Bulk reprint** via command line
- **Export CSV** kapan saja dari browser

---

## Struktur File

```
factory-label-system/
├── app.py               # Flask app utama (server + API)
├── printer_utils.py     # Utility cetak: CUPS, ZPL, Windows
├── csv_to_sql.py        # Import/export CSV ↔ SQL
├── requirements.txt     # Python dependencies
├── templates/
│   ├── index.html       # Form input utama
│   └── history.html     # Halaman riwayat output
├── data/
│   ├── production.db    # SQLite database (auto-created)
│   └── production_output.csv  # CSV log (auto-created)
└── labels_output/       # Label PNG tersimpan disini
    └── HDPE-20250412-A1B2.png
```

---

## Instalasi

### 1. Pastikan Python 3.10+ terinstall
```bash
python --version
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Jalankan server
```bash
python app.py
```

### 4. Buka di browser
```
http://localhost:5000
```

Untuk akses dari tablet atau PC lain di jaringan yang sama:
```
http://[IP-PC-SERVER]:5000
```
Ganti [IP-PC-SERVER] dengan IP address PC yang menjalankan server (cek dengan `ipconfig` di Windows atau `ip a` di Linux).

---

## Konfigurasi Printer

Edit bagian `CONFIGURATION` di `printer_utils.py`:

```python
PRINTER_TYPE = "cups"            # cups | zpl | windows | manual
CUPS_PRINTER = "Thermal_Label"  # nama printer di CUPS
ZPL_HOST     = "192.168.1.100"  # IP printer Zebra
ZPL_PORT     = 9100
```

### Pilihan printer:
| Mode      | Keterangan |
|-----------|------------|
| `cups`    | Linux/Mac, printer USB/network via CUPS |
| `zpl`     | Zebra printer via TCP/IP langsung |
| `windows` | Windows, membuka dialog print bawaan |
| `manual`  | Buka file PNG, print manual dari viewer |

---

## Koneksi ke Metabase

Metabase bisa connect langsung ke SQLite database:

1. Di Metabase → **Add Database**
2. Pilih: **SQLite**
3. Path file: `/path/to/factory-label-system/data/production.db`
4. Klik **Connect**

Table yang tersedia: `production_output`

Atau kalau pakai PostgreSQL/MySQL, gunakan `csv_to_sql.py` untuk generate INSERT statements:
```bash
python csv_to_sql.py --engine postgres > import.sql
# lalu jalankan import.sql di database Anda
```

---

## Command Line Tools

### Cetak ulang label
```bash
# Cetak satu label berdasarkan Order ID
python printer_utils.py --print HD01-20250412-A3B2

# Preview semua label hari ini tanpa print
python printer_utils.py --reprint --dry-run

# Reprint semua Shift 1 tanggal tertentu
python printer_utils.py --reprint --date 2025-04-12 --shift "Shift 1"

# List printer yang tersedia (CUPS)
python printer_utils.py --list
```

### Import/export CSV
```bash
# Validasi CSV saja
python csv_to_sql.py --check

# Import CSV ke SQLite
python csv_to_sql.py

# Generate SQL untuk PostgreSQL
python csv_to_sql.py --engine postgres
```

---

## Ukuran Label

Default: **100mm × 60mm** @ 203 DPI (standar thermal printer HDPE/plastik).

Untuk ganti ukuran, edit di `app.py`:
```python
LABEL_WIDTH_MM  = 100
LABEL_HEIGHT_MM = 60
DPI             = 203   # 203 atau 300 sesuai printer
```

---

## Format Order ID

Order ID di-generate otomatis:
```
HDKA-20250412-A3B2
│     │         └── 4 karakter random
│     └── tanggal YYYYMMDD
└── kode divisi (inisial kata)
```

---

## API Endpoints

| Method | URL | Keterangan |
|--------|-----|------------|
| GET    | `/` | Form input utama |
| GET    | `/history` | Halaman riwayat |
| POST   | `/api/submit` | Submit order (JSON) |
| GET    | `/api/recent` | 20 record terbaru (JSON) |
| GET    | `/api/print/<order_id>` | Tampilkan label PNG |
| GET    | `/api/download_label/<order_id>` | Download label PNG |
| GET    | `/api/download_csv` | Download semua data CSV |
| GET    | `/api/products/<division>` | Daftar produk per divisi |

---

## Troubleshooting

**Server tidak bisa diakses dari tablet?**
- Pastikan firewall mengizinkan port 5000
- Windows: `netsh advfirewall firewall add rule name="FactoryOS" dir=in action=allow protocol=TCP localport=5000`

**Label tidak tercetak?**
- Cek nama printer: `lpstat -p` (Linux) atau Device Manager (Windows)
- Set `PRINTER_TYPE = "manual"` untuk buka file PNG manual dulu

**Metabase tidak bisa baca SQLite?**
- Pastikan path file absolute dan bisa dibaca oleh user yang menjalankan Metabase
- Alternatif: gunakan CSV import di Metabase (upload `production_output.csv`)
