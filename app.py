from flask import Flask, render_template, request, jsonify, redirect, send_file, session
import qrcode
from PIL import Image, ImageDraw, ImageFont
import csv, os, sqlite3, json, io, base64, uuid, functools
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path



app = Flask(__name__)

# ─── CONFIG ─────────────────────────────────────────────────
app.secret_key = "GarindraPlastik@2026#Produksi!"
app.permanent_session_lifetime = timedelta(minutes=45)

# ─── PATHS ──────────────────────────────────────────────────
APP_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(APP_DIR, "data", "production.db")

LABELS_DIR   = r"Z:\Checker\Production\labels_output"
MAPPING_CSV  = r"Z:\Checker\Production\Mapping.csv"
SPK_CSV      = r"Z:\Checker\Summary SPK.csv"
USER_EXCEL   = r"Z:\Checker\Production\other\other.xlsx"
USER_SHEET   = "User"

# Katalog produksi (dipakai save_record + recent + lookup)
CSV_MIXING      = r"Z:\Checker\Production\Database\katalogmixing.csv"
CSV_HD          = r"Z:\Checker\Production\Database\kataloghd.csv"
CSV_POTONG      = r"Z:\Checker\Production\Database\katalogpotong.csv"
CSV_PACKING     = r"Z:\Checker\Production\Database\katalogpacking.csv"
CSV_SISA_PACK   = r"Z:\Checker\Production\Database\katalogsisapack.csv"
CSV_AVAL_MIXING = r"Z:\Checker\Production\Database\katalogavalmixing.csv"
CSV_AVAL_HD = r"Z:\Checker\Production\Database\katalogavalhd.csv"
CSV_AVAL_POTONG = r"Z:\Checker\Production\Database\katalogavalpotong.csv"
CSV_AVAL_PACKING = r"Z:\Checker\Production\Database\katalogavalpacking.csv"
CSV_AVAL_QC = r"Z:\Checker\Production\Database\katalogavalqc.csv"

# Katalog map untuk lookup kode (scan salah)
CATALOG_MAP = {
    "MIXING":      CSV_MIXING,
    "HD":          CSV_HD,
    "POTONG":      CSV_POTONG,
    "PACKING":     CSV_PACKING,
    "SISA_PACK":   CSV_SISA_PACK,
    "AVAL_MIXING": CSV_AVAL_MIXING,
    "AVAL_HD": CSV_AVAL_HD,
    "AVAL_POTONG": CSV_AVAL_POTONG,
    "AVAL_PACKING": CSV_AVAL_PACKING,
    "AVAL_QC": CSV_AVAL_QC,
}

# CSV scan salah
SCAN_DIR  = Path(r"Z:\Checker\Production\Database\scan_salah")
CSV_SCAN_FILES = {
    "scansalahhd.csv":      SCAN_DIR / "scansalahhd.csv",
    "scansalahmixing.csv":  SCAN_DIR / "scansalahmixing.csv",
    "scansalahpotong.csv":  SCAN_DIR / "scansalahpotong.csv",
    "scansalahpacking.csv": SCAN_DIR / "scansalahpacking.csv",
    "scansalahqc.csv":      SCAN_DIR / "scansalahqc.csv",
}

# Prefix kode → (file csv, catalog untuk lookup, label divisi)
PREFIX_CONFIG = {
    "HD":  ("scansalahhd.csv",      "HD",          "HD"),
    "AHP": ("scansalahhd.csv",      "AVAL_HD",     "HD — Prong"),
    "AHD": ("scansalahhd.csv",      "AVAL_HD",     "HD — Daun"),
    "AHS": ("scansalahhd.csv",      "AVAL_HD",     "HD — Sapuan"),
    "MI":  ("scansalahmixing.csv",  "MIXING",      "Mixing"),
    "AMS": ("scansalahmixing.csv",  "AVAL_MIXING", "Aval Mixing"),
    "CU":  ("scansalahpotong.csv",  "POTONG",      "Potong"),
    "ACP": ("scansalahpotong.csv",  "AVAL_POTONG", "Aval Potong — Plong"),
    "ACM": ("scansalahpotong.csv",  "AVAL_POTONG", "Aval Potong — Mesin"),
    "ACS": ("scansalahpotong.csv",  "AVAL_POTONG", "Aval Potong — Silet/Sapuan"),
    "ACH": ("scansalahpotong.csv",  "AVAL_POTONG", "Aval Potong — Mutasi"),
    "ACR": ("scansalahpotong.csv",  "AVAL_POTONG", "Aval Potong — Reject"),
    "PA":  ("scansalahpacking.csv", "PACKING",     "Packing"),
    "PS":  ("scansalahpacking.csv", "SISA_PACK",   "Sisa Pack"),
    "APP": ("scansalahpacking.csv", "AVAL_PACKING","Aval Packing — Plastik"),
    "APR": ("scansalahpacking.csv", "AVAL_PACKING","Aval Packing — Rafia"),
    "APB": ("scansalahpacking.csv", "AVAL_PACKING","Aval Packing — Blongsong"),
    "APC": ("scansalahpacking.csv", "AVAL_PACKING","Aval Packing — Mutasi"),
    "AQC": ("scansalahqc.csv",      "AVAL_QC",     "QC"),
}

CSV_SCAN_COLUMNS = ["create_at", "divisi", "prefix", "divisi_label", "spk", "customer", "produk", "uk", "checker", "scanned_by", "code"]

import re

def get_prefix_from_code(code: str):
    """
    Ekstrak prefix dari kode barcode.
    Coba 3 karakter dulu, lalu 2 karakter.
    Return (prefix, csv_filename, catalog_key, divisi_label) atau None.
    """
    code = code.strip().upper()
    m = re.match(r'^([A-Z]+)', code)
    if not m:
        return None, None, None, None
    raw = m.group(1)
    # Coba 3 karakter dulu, lalu 2
    for length in [3, 2]:
        p = raw[:length]
        if p in PREFIX_CONFIG:
            csv_file, catalog_key, label = PREFIX_CONFIG[p]
            return p, csv_file, catalog_key, label
    return None, None, None, None



# ─── SESSION TIMEOUT ────────────────────────────────────────
@app.before_request
def check_session_timeout():
    if request.endpoint in ("login_page", "login_post", "logout", "check_session", "static"):
        return
    if not session.get("logged_in"):
        return

    last_active = session.get("last_active")
    now = datetime.now()

    if last_active:
        last_active = datetime.fromisoformat(last_active)
        if now - last_active > timedelta(minutes=45):
            session.clear()
            if request.is_json:
                return jsonify(success=False, message="SESSION_EXPIRED")
            return redirect("/login")

    session["last_active"] = now.isoformat()


# ─── AUTH HELPERS ────────────────────────────────────────────
def load_users():
    df = pd.read_excel(USER_EXCEL, sheet_name=USER_SHEET, engine="openpyxl")
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["username", "password"])
    df["username"] = df["username"].astype(str).str.strip()
    df["password"] = df["password"].astype(str).str.strip()
    return df


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        if session.get("role") != "administrator":
            return redirect("/mixing")
        return f(*args, **kwargs)
    return decorated


# ─── QR & LABEL ─────────────────────────────────────────────
def generate_qr(code):
    qr = qrcode.make(code)
    return qr.convert("RGB")


def generate_label_image(order_id, data):
    img  = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(img)

    qr = generate_qr(data["code"]).resize((180, 180))
    img.paste(qr, (10, 30))

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()

    x, y, gap = 210, 20, 22

    operator = (
        data.get("operator_mix") or data.get("operator_hd") or
        data.get("operator_cu")  or data.get("operator_pa")  or
        data.get("operator_sp")  or data.get("operator_amix") or
        data.get("operator_hd")  or data.get("operator_hd") or
        data.get("operator_qc")  or data.get("operator_qc")
    )

    text_data = [
        data.get("customer"),
        data.get("spk"),
        data.get("produk"),
        data.get("uk"),
        operator,
        f"{data.get('berat_bersih')} kg",
        f"{data.get('karung', '')} kg",
        data.get("divisi"),
        data.get("tanggal"),
        data.get("shift"),
        data.get("checker"),
        data.get("created_at"),
    ]

    for i, t in enumerate(text_data):
        draw.text((x, y + i * gap), str(t or ""), fill="black", font=font)

    return img


# ─── CODE GENERATOR ─────────────────────────────────────────
def generate_code(data):
    now = datetime.now()

    # Mapping divisi normal
    div_map = {
        "MIXING":      "MI",
        "HD":          "HD",
        "POTONG":      "CU",
        "PACKING":     "PA",
        "SISA_PACK":   "PS",
        "AVAL_MIXING": "AMS",
        "AVAL_QC": "AQC",
    }

    divisi = str(data.get("divisi", "")).strip().upper()

    # Khusus AVAL_HD: kode tergantung jenis_hd
    if divisi == "AVAL_HD":
        jenis_map = {
            "Prong":  "AHP",
            "Daun":   "AHD",
            "Sapuan": "AHS",
        }
        jenis = str(data.get("jenis_hd", "")).strip()
        div = jenis_map.get(jenis, "AHX")  
    else:
        div = div_map.get(divisi, "XX")
    if divisi == "AVAL_POTONG":
        jenis_map = {
            "Plong": "ACP",
            "Mesin": "ACM",
            "Silet": "ACS",
            "Mutasi": "ACH",
            "Reject": "ACR",
            "Sapuan": "ACS",
        }
        jenis = str(data.get("jenis_cu", "")).strip()
        div = jenis_map.get(jenis, "ACX")  # 
    else:
        div = div_map.get(divisi, "XX")
        
    if divisi == "AVAL_PACKING":
        jenis_map = {
            "Plastik": "APP",
            "Rafia": "APR",
            "Blongsong": "APB",
            "Mutasi": "APC",
        }
        jenis = str(data.get("jenis_pa", "")).strip()
        div = jenis_map.get(jenis, "APX")  # 
    else:
        div = div_map.get(divisi, "XX")
        
    tanggal = now.strftime("%d-%m-%Y")
    spk     = str(data.get("spk", "")).strip()
    shift   = str(data.get("shift", "")).strip()
    try:
        berat = "{:.2f}".format(float(data.get("berat_bersih") or 0))
    except:
        berat = "0.00"
    waktu = now.strftime("%H%M%S")
    return f"{div}{tanggal}{spk}{shift}{berat}{waktu}"


# ─── SPK LOOKUP ─────────────────────────────────────────────
def load_spk_data():
    df = pd.read_csv(SPK_CSV, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df[["No. SPK", "CUSTOMER", "PRODUCT", "UK"]]


# ─── DB INIT ────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        operator_mix TEXT, checker TEXT,
        berat_bersih REAL, karung REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS kataloghd (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        operator_hd TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        operator_cu TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, keranjang REAL, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        operator_pa TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogsisapack (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        operator_sp TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, sisa REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_amix TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, jenis REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalHD (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_hd TEXT, checker TEXT,
        mesin REAL, jenis_hd TEXT, kategori_hd TEXT, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_cu TEXT, checker TEXT,
        mesin REAL, jenis_cu TEXT, kategori_cu TEXT, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_pa TEXT, checker TEXT,
        mesin REAL, jenis_pa TEXT, kategori_pa TEXT, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalqc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_qc TEXT, checker TEXT,
        mesin REAL, kategori_qc TEXT, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")

    conn.commit()
    conn.close()


# ─── CSV INIT ───────────────────────────────────────────────
CSV_HEADERS = [
    "tanggal","shift","divisi",
    "spk","customer","produk","uk",
    "operator_mix","checker",
    "berat_bersih","karung",
    "created_at","code"
]

def init_csv(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()

def ensure_csv_scan(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_SCAN_COLUMNS)
            writer.writeheader()


# ─── SAVE RECORD ────────────────────────────────────────────
def save_record(data):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    div  = (data.get("divisi") or "").strip().upper()

    if div == "HD":
        c.execute("""
        INSERT INTO kataloghd (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_hd, checker, mesin, berat_kg, bobin, berat_bersih,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_hd, :checker, :mesin, :berat_kg, :bobin, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_HD
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_hd","checker","mesin","berat_kg","bobin","berat_bersih","created_at","code"]

    elif div == "POTONG":
        c.execute("""
        INSERT INTO katalogpotong (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_cu, checker, mesin, berat_kg, keranjang, berat_bersih,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_cu, :checker, :mesin, :berat_kg, :keranjang, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_POTONG
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_cu","checker","mesin","berat_kg","keranjang","berat_bersih","created_at","code"]

    elif div == "PACKING":
        c.execute("""
        INSERT INTO katalogpacking (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_pa, checker, mesin, berat_bersih,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_pa, :checker, :mesin, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_PACKING
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_pa","checker","mesin","berat_bersih","created_at","code"]

    elif div == "SISA_PACK":
        c.execute("""
        INSERT INTO katalogsisapack (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_sp, checker, mesin, berat_bersih, sisa,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_sp, :checker, :mesin, :berat_bersih, :sisa,
            :created_at, :code
        )""", data)
        csv_path = CSV_SISA_PACK
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_sp","checker","mesin","berat_bersih","sisa","created_at","code"]

    elif div == "AVAL_MIXING":
        c.execute("""
        INSERT INTO katalogavalmixing (
            tanggal, shift, divisi, spk,
            operator_amix, checker, mesin, berat_bersih, jenis,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_amix, :checker, :mesin, :berat_bersih, :jenis,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_MIXING
        headers  = ["tanggal","shift","divisi","spk",
                    "operator_amix","checker","mesin","berat_bersih","jenis","created_at","code"]

    elif div == "AVAL_HD":
        c.execute("""
        INSERT INTO katalogavalhd (
            tanggal, shift, divisi, spk,
            operator_hd, checker, mesin, jenis_hd, kategori_hd, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_hd, :checker, :mesin, :jenis_hd, :kategori_hd, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_HD
        headers  = ["tanggal","shift","divisi","spk",
                    "operator_hd","checker","mesin","jenis_hd","kategori_hd","berat_bersih","created_at","code"]

    elif div == "AVAL_POTONG":
        c.execute("""
        INSERT INTO katalogavalpotong (
            tanggal, shift, divisi, spk,
            operator_cu, checker, mesin, jenis_cu, kategori_cu, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_cu, :checker, :mesin, :jenis_cu, :kategori_cu, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_POTONG
        headers  = ["tanggal","shift","divisi","spk",
                    "operator_cu","checker","mesin","jenis_cu","kategori_cu","berat_bersih","created_at","code"]
  
    elif div == "AVAL_PACKING":
        c.execute("""
        INSERT INTO katalogavalpacking (
            tanggal, shift, divisi, spk,
            operator_pa, checker, mesin, jenis_pa, kategori_pa, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_pa, :checker, :mesin, :jenis_pa, :kategori_pa, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_PACKING
        headers  = ["tanggal","shift","divisi","spk",
                    "operator_pa","checker","mesin","jenis_pa","kategori_pa","berat_bersih","created_at","code"]

    elif div == "AVAL_QC":
        c.execute("""
        INSERT INTO katalogavalqc (
            tanggal, shift, divisi, spk,
            operator_qc, checker, mesin, kategori_qc, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_qc, :checker, :mesin, :kategori_qc, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_QC
        headers  = ["tanggal","shift","divisi","spk",
                    "operator_qc","checker","mesin","kategori_qc","berat_bersih","created_at","code"]


    elif div == "MIXING":
        c.execute("""
        INSERT INTO katalogmixing (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_mix, checker, berat_bersih, karung,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_mix, :checker, :berat_bersih, :karung,
            :created_at, :code
        )""", data)
        csv_path = CSV_MIXING
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_mix","checker","berat_bersih","karung","created_at","code"]

    else:
        conn.close()
        raise ValueError(f"Divisi tidak dikenali: {div}")

    conn.commit()
    conn.close()

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow({k: data.get(k, "") for k in headers})


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

# ─── AUTH ───────────────────────────────────────────────────
@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET"])
def login_page():
    if session.get("logged_in"):
        return redirect("/mixing")
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login_post():
    data     = request.get_json()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    try:
        users = load_users()
        match = users[
            (users["username"] == username) &
            (users["password"] == password)
        ]
        if not match.empty:
            session.permanent    = True
            session["logged_in"] = True
            session["username"]  = username
            session["name"]      = str(match.iloc[0].get("name", username))
            session["role"]      = str(match.iloc[0].get("role", "user"))
            session["last_active"] = datetime.now().isoformat()
            return jsonify(success=True, redirect="/mixing")
        else:
            return jsonify(success=False, message="Username atau password salah.")
    except FileNotFoundError:
        return jsonify(success=False, message="File data user tidak ditemukan.")
    except Exception as e:
        return jsonify(success=False, message=f"Error: {str(e)}")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/check_session")
def check_session():
    if session.get("logged_in"):
        return jsonify(active=True)
    return jsonify(active=False)


# ─── PAGES ──────────────────────────────────────────────────
@app.route("/mixing")
@login_required
def mixing():
    return render_template("index.html", active_page="mixing", current_user=session.get("name"))

@app.route("/hd")
@login_required
def hd():
    return render_template("hd.html", active_page="hd", current_user=session.get("name"))

@app.route("/potong")
@login_required
def potong():
    return render_template("potong.html", active_page="potong", current_user=session.get("name"))

@app.route("/packing")
@login_required
def packing():
    return render_template("packing.html", active_page="packing", current_user=session.get("name"))

@app.route("/sisa_pack")
@login_required
def sisa_pack():
    return render_template("sisa_pack.html", active_page="sisa_pack", current_user=session.get("name"))

@app.route("/aval_mixing")
@login_required
def aval_mixing():
    return render_template("aval_mixing.html", active_page="aval_mixing", current_user=session.get("name"))

@app.route("/aval_hd")
@login_required
def aval_hd():
    return render_template("aval_hd.html", active_page="aval_hd", current_user=session.get("name"))

@app.route("/aval_potong")
@login_required
def aval_potong():
    return render_template("aval_potong.html", active_page="aval_potong", current_user=session.get("name"))

@app.route("/aval_packing")
@login_required
def aval_packing():
    return render_template("aval_packing.html", active_page="aval_packing", current_user=session.get("name"))

@app.route("/aval_qc")
@login_required
def aval_qc():
    return render_template("aval_qc.html", active_page="aval_qc", current_user=session.get("name"))

@app.route("/scan_salah")
@admin_required
def scan_salah():
    return render_template("scan_salah.html", active_page="scan_salah", current_user=session.get("name"))


# ─── API: OPERATORS ─────────────────────────────────────────
@app.route("/api/operators/<divisi>")
@login_required
def get_operators(divisi):
    try:
        df = pd.read_csv(MAPPING_CSV, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()
        df["divisi"] = df["divisi"].astype(str).str.strip().str.upper()
        filtered  = df[df["divisi"] == divisi.strip().upper()]
        operators = filtered["operator"].dropna().str.strip().tolist()
        return jsonify(operators)
    except Exception as e:
        return jsonify([])


# ─── API: SPK LOOKUP ────────────────────────────────────────
@app.route("/get-spk/<spk>")
@login_required
def get_spk(spk):
    df  = load_spk_data()
    row = df[df["No. SPK"].astype(str) == str(spk)]
    if not row.empty:
        r = row.iloc[0]
        return jsonify({"customer": r["CUSTOMER"], "product": r["PRODUCT"], "uk": r["UK"]})
    return jsonify({})


# ─── API: CODE LOOKUP (scan salah) ──────────────────────────
@app.route("/api/lookup_code", methods=["POST"])
@login_required
def lookup_code():
    try:
        data = request.get_json()
        code = (data.get("code") or "").strip()

        if not code:
            return jsonify(found=False, error="Kode kosong")

        # Auto-detect prefix
        prefix, csv_file, catalog_key, divisi_label = get_prefix_from_code(code)

        if not prefix or catalog_key not in CATALOG_MAP:
            return jsonify(
                found=False,
                error=f"Prefix kode tidak dikenal",
                prefix=prefix or "",
                divisi_label="Unknown",
                csv_file=None
            )

        # Lookup di katalog yang sesuai
        catalog_path = CATALOG_MAP[catalog_key]
        if not os.path.exists(catalog_path):
            return jsonify(
                found=False,
                prefix=prefix,
                divisi_label=divisi_label,
                csv_file=csv_file,
                error="File katalog tidak ditemukan"
            )

        df = pd.read_csv(catalog_path, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()
        df["code"] = df["code"].astype(str).str.strip()

        match = df[df["code"] == code]

        if match.empty:
            return jsonify(
                found=False,
                prefix=prefix,
                divisi_label=divisi_label,
                csv_file=csv_file,
            )

        r = match.iloc[0]
        return jsonify(
            found        = True,
            prefix       = prefix,
            divisi_label = divisi_label,
            csv_file     = csv_file,
            spk          = str(r.get("spk", "")),
            customer     = str(r.get("customer", "")),
            produk       = str(r.get("produk", "")),
            uk           = str(r.get("uk", "")),
            checker      = str(r.get("checker", "")),
        )
    except Exception as e:
        return jsonify(found=False, error=str(e))


# ─── API: SAVE SCAN SALAH ───────────────────────────────────
@app.route("/save_csv", methods=["POST"])
@login_required
def save_csv():
    try:
        data    = request.get_json()
        records = data.get("records", [])

        if not records:
            return jsonify(success=False, error="Tidak ada data")

        # Kelompokkan per file CSV tujuan
        from collections import defaultdict
        groups = defaultdict(list)

        for rec in records:
            csv_file = rec.get("csv_file")
            if not csv_file or csv_file not in CSV_SCAN_FILES:
                # Fallback: deteksi ulang dari kode
                _, csv_file, _, _ = get_prefix_from_code(rec.get("code", ""))
            if not csv_file or csv_file not in CSV_SCAN_FILES:
                return jsonify(
                    success=False,
                    error=f"Kode '{rec.get('code')}' tidak bisa ditentukan CSV tujuannya"
                )
            groups[csv_file].append(rec)

        # Simpan per grup
        for csv_filename, recs in groups.items():
            path = CSV_SCAN_FILES[csv_filename]
            path.parent.mkdir(parents=True, exist_ok=True)
            file_exists = path.exists()

            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_SCAN_COLUMNS)
                if not file_exists:
                    writer.writeheader()
                for rec in recs:
                    writer.writerow({
                        "create_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "divisi":       rec.get("prefix", ""),
                        "prefix":       rec.get("prefix", ""),
                        "divisi_label": rec.get("divisi_label", ""),
                        "spk":          rec.get("spk", ""),
                        "customer":     rec.get("customer", ""),
                        "produk":       rec.get("produk", ""),
                        "uk":           rec.get("uk", ""),
                        "checker":      rec.get("checker", ""),
                        "scanned_by":   session.get("name", ""),
                        "code":         rec.get("code", ""),
                    })

        return jsonify(success=True, saved=len(records))

    except Exception as e:
        return jsonify(success=False, error=str(e))


# ─── API: SUBMIT PRODUKSI ───────────────────────────────────
@app.route("/api/submit", methods=["POST"])
@login_required
def submit():
    try:
        d        = request.json
        order_id = str(uuid.uuid4())[:8]
        code     = generate_code(d)
        div      = (d.get("divisi") or "").strip().upper()

        if div == "HD":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_hd": d.get("operator_hd"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "bobin": float(d.get("bobin") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "POTONG":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_cu": d.get("operator_cu"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "keranjang": float(d.get("keranjang") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "PACKING":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_pa": d.get("operator_pa"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "SISA_PACK":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_sp": d.get("operator_sp"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "sisa": float(d.get("sisa") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_MIXING":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),
                "operator_amix": d.get("operator_amix"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "jenis": d.get("jenis"),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_HD":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),
                "operator_hd": d.get("operator_hd"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "jenis_hd": d.get("jenis_hd"),
                "kategori_hd": d.get("kategori_hd"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_POTONG":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),
                "operator_cu": d.get("operator_cu"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "jenis_cu": d.get("jenis_cu"),
                "kategori_cu": d.get("kategori_cu"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_PACKING":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),
                "operator_pa": d.get("operator_pa"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "jenis_pa": d.get("jenis_pa"),
                "kategori_pa": d.get("kategori_pa"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_QC":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),
                "operator_qc": d.get("operator_qc"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "kategori_qc": d.get("kategori_qc"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "MIXING":
            record = {
                "order_id": order_id, "tanggal": d.get("tanggal","").split("T")[0],
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_mix": d.get("operator_mix"), "checker": d.get("checker"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "karung": float(d.get("karung") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        else:
            return jsonify({"success": False, "message": "Divisi tidak dikenali"})

        save_record(record)

        img = generate_label_image(order_id, record)
        os.makedirs(LABELS_DIR, exist_ok=True)
        img.save(os.path.join(LABELS_DIR, f"{order_id}.png"))

        return jsonify({
            "success": True,
            "order_id": order_id,
            "label_url": f"/label/{order_id}",
            "print_url": f"/label/{order_id}"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ─── API: LABEL VIEW ────────────────────────────────────────
@app.route("/label/<order_id>")
@login_required
def label(order_id):
    path = os.path.join(LABELS_DIR, f"{order_id}.png")
    return send_file(path, mimetype="image/png")


# ─── API: RECENT ────────────────────────────────────────────
@app.route("/api/recent/<divisi>")
@login_required
def recent(divisi):
    try:
        divisi = (divisi or "").strip().lower()
        path_map = {
            "mixing":    CSV_MIXING,
            "hd":        CSV_HD,
            "potong":    CSV_POTONG,
            "packing":   CSV_PACKING,
            "sisa_pack": CSV_SISA_PACK,
            "aval_mixing": CSV_AVAL_MIXING,
            "aval_hd": CSV_AVAL_HD,
            "aval_potong": CSV_AVAL_POTONG,
            "aval_packing": CSV_AVAL_PACKING,
            "aval_qc": CSV_AVAL_QC,
        }
        path = path_map.get(divisi)
        if not path:
            return jsonify({"success": False, "message": "Divisi tidak dikenali"})
        if not os.path.exists(path):
            return jsonify([])

        df = pd.read_csv(path, encoding="utf-8")
        df = df.fillna("").iloc[::-1]
        return jsonify(df.to_dict(orient="records"))

    except Exception as e:
        print("ERROR recent():", e)
        return jsonify([])


# ─── RUN ────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    init_csv(CSV_MIXING)
    init_csv(CSV_HD)
    init_csv(CSV_POTONG)
    init_csv(CSV_PACKING)
    init_csv(CSV_SISA_PACK)
    init_csv(CSV_AVAL_MIXING)
    init_csv(CSV_AVAL_HD)
    init_csv(CSV_AVAL_POTONG)
    init_csv(CSV_AVAL_PACKING)
    init_csv(CSV_AVAL_QC)
    print("=" * 55)
    print("  Factory Label System running at http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=True)