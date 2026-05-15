from flask import Flask, render_template, request, jsonify, redirect, send_file, session
import qrcode
from PIL import Image, ImageDraw, ImageFont
import csv, os, sqlite3, json, io, base64, uuid, functools
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import time
record_cache = {}  # {order_id: (record, timestamp)}

def cleanup_cache():
    now = time.time()
    expired = [k for k, (_, t) in record_cache.items() if now - t > 3600]
    for k in expired:
        del record_cache[k]

app = Flask(__name__)

# ─── CONFIG ─────────────────────────────────────────────────
app.secret_key = "GarindraPlastik@2026#Produksi!"
app.permanent_session_lifetime = timedelta(minutes=5)

# ─── PATHS ──────────────────────────────────────────────────
APP_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(APP_DIR, "data", "production.db")

MAPPING_CSV  = r"Z:\Checker\Production\Mapping.csv"
SPK_CSV      = r"Z:\Checker\Summary SPK.csv"
USER_EXCEL   = r"Z:\Checker\Production\other\other.xlsx"
USER_SHEET   = "User"

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

# Katalog map (scan salah)
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

SCAN_DIR  = Path(r"Z:\Checker\Production\Database\scan_salah")
CSV_SCAN_FILES = {
    "scansalahhd.csv":      SCAN_DIR / "scansalahhd.csv",
    "scansalahmixing.csv":  SCAN_DIR / "scansalahmixing.csv",
    "scansalahpotong.csv":  SCAN_DIR / "scansalahpotong.csv",
    "scansalahpacking.csv": SCAN_DIR / "scansalahpacking.csv",
    "scansalahqc.csv":      SCAN_DIR / "scansalahqc.csv",
}

SCAN_PDIR  = Path(r"Z:\Checker\Production\Database\scan_pemakaian")
CSV_SCAN_PFILES = {
    "scanhd.csv":      SCAN_PDIR / "scanhd.csv",
    "scanmixing.csv":  SCAN_PDIR / "scanmixing.csv",
    "scanpotong.csv":  SCAN_PDIR / "scanpotong.csv",
    "scanpacking.csv": SCAN_PDIR / "scanpacking.csv",
}

PEMAKAIAN_MAP = {
    "HD": "scanhd.csv",
    "MI": "scanmixing.csv",
    "CU": "scanpotong.csv",
    "PA": "scanpacking.csv",
    "PS": "scanpacking.csv",
}

# Prefix kode Aval
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

CSV_PSCAN_COLUMNS = [
    "create_at", "tanggal", "shift",
    "divisi", "prefix", "divisi_label",
    "spk", "customer", "produk", "uk",
    "checker", "scanned_by", "code"
]

import re

def get_prefix_from_code(code: str):

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
        if now - last_active > timedelta(minutes=5):
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

def adminwip_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        if session.get("role") not in ("administrator", "adminwip"):
            return redirect("/scan_pemakaian")
        return f(*args, **kwargs)
    return decorated

def checker_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        if session.get("role") not in ("administrator", "checker"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def staff_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        if session.get("role") not in ("administrator", "staff"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def hasil_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")

        if session.get("role") not in ("administrator", "adminwip", "staff"):
            return redirect("/login")

        return f(*args, **kwargs)

    return decorated

FIELD_MAP = {
    "MIXING":       {"operator": "operator_mix", "wadah": "karung"},
    "HD":           {"operator": "operator_hd",  "wadah": "bobin"},
    "POTONG":       {"operator": "operator_cu",  "wadah": "keranjang"},
    "PACKING":      {"operator": "operator_pa",  "wadah": ""},
    "SISA_PACK":    {"operator": "operator_sp",  "wadah": "sisa"},
    "AVAL_MIXING":  {"operator": "operator_amix","wadah": "karung"},
    "AVAL_HD":      {"operator": "operator_hd",  "wadah": "karung"},
    "AVAL_POTONG":  {"operator": "operator_cu",  "wadah": "karung"},
    "AVAL_PACKING": {"operator": "operator_pa",  "wadah": ""},
    "AVAL_QC":      {"operator": "operator_qc",  "wadah": ""},
}

def generate_qr(code):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1,
    )
    qr.add_data(code)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

# ─── LABEL SIZE ─────────────────────────────────────────────
LABEL_W = 302  
LABEL_H = 200   
SCALE   = 4
LABEL_W_HI = LABEL_W * SCALE  
LABEL_H_HI = LABEL_H * SCALE  

def generate_label_image(order_id, data, source_route=None):
    img  = Image.new("RGB", (LABEL_W_HI, LABEL_H_HI), "white")
    draw = ImageDraw.Draw(img)

    font_paths = [
        r"C:\Windows\Fonts\calibrib.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
    ]
    
    TIKET_SEMENTARA_ROUTES = {
    "barcode_mixing", "barcode_hd", "barcode_potong", "barcode_packing",
    "barcode_sisa_pack", "barcode_aval_mixing", "barcode_aval_hd",
    "barcode_aval_potong", "barcode_aval_packing", "barcode_aval_qc"
}

    show_tiket_sementara = (source_route == "barcode")
    CELTIC_FONT_PATH = r"Z:\Checker\Production\Production\templates\celtic-astrologer\CelticAstrologer.ttf"  # sesuaikan namanya

    try:
        celtic_font = ImageFont.truetype(CELTIC_FONT_PATH, 18 * SCALE)
    except:
        for fp in font_paths:
            try:
                celtic_font = ImageFont.truetype(fp, 18 * SCALE)
                break
            except:
                continue

    font_sm = font_md = font_lg = None
    for fp in font_paths:
        try:
            font_sm = ImageFont.truetype(fp, 11 * SCALE)
            font_md = ImageFont.truetype(fp, int(14.3 * SCALE))
            font_lg = ImageFont.truetype(fp, 15 * SCALE)
            break
        except:
            continue

    if font_sm is None:
        font_sm = ImageFont.load_default()
        font_md = font_sm
        font_lg = font_sm

    divisi_raw      = str(data.get("divisi", "")).strip().upper()
    prefix, _, _, _ = get_prefix_from_code(data.get("code", ""))
    divisi_display  = prefix if prefix else divisi_raw

    config         = FIELD_MAP.get(divisi_raw, {})
    operator_field = config.get("operator", "")
    wadah_field    = config.get("wadah", "")

    operator = str(data.get(operator_field, "") or "")
    bobin    = str(data.get(wadah_field, "")    or
                   data.get("karung", "")        or
                   data.get("keranjang", "")     or
                   data.get("sisa", "")          or "")
    berat    = str(data.get("berat_bersih", "") or "")
    beratkg  = str(data.get("berat_kg", "")     or "")
    spk      = str(data.get("spk", "")          or "")
    uk       = str(data.get("uk", "")           or "")
    tanggal  = str(data.get("tanggal", "")      or "")
    mesin    = str(data.get("mesin", "")        or "")
    shift    = str(data.get("shift", "")        or "")
    checker  = str(data.get("checker", "")      or "")
    created  = str(data.get("created_at", "")   or "")
    customer = str(data.get("customer", "")     or "")
    produk   = str(data.get("produk", "")       or "")
    team = str(data.get("team", "") or "")

    if divisi_raw == "AVAL_MIXING":
        customer = "AVAL SAPUAN"
        produk   = "MIXING"

    CELTIC_MAP = {
    "0": "0", "1": "1", "2": "E", "3": "F", "4": "4",
    "5": "5", "6": "6", "7": "X", "8": "8", "9": "Y",
    "10": "U", "11": "V", "12": "S", "17": "z", "18": "m",
    "P": "b", "M": "v", "20": "T",
    }

    def to_celtic(val):
        s = str(val).strip()
        if s in CELTIC_MAP:
            return CELTIC_MAP[s]
        return "".join(CELTIC_MAP.get(c, c) for c in s)

    DIVISI_NO_MESIN = {"MIXING", "AVAL_MIXING", "AVAL_QC"}

    spk_str = str(spk).strip()
    spk_last2 = spk_str[-2:] if len(spk_str) >= 2 else spk_str

    if len(spk_last2) == 1:
        d1 = to_celtic(spk_last2)
        d2 = to_celtic(spk_last2)
    else:
        d1 = to_celtic(spk_last2[0])
        d2 = to_celtic(spk_last2[1])

    if divisi_raw in DIVISI_NO_MESIN:
        d3 = to_celtic(shift)
    else:
        d3 = to_celtic(str(mesin).strip()) if mesin else ""

    celtic_str = " ".join(filter(None, [d1, d2, d3]))

    padding_top = 7 * SCALE

    # QR
    qr_size = 85 * SCALE
    qr      = generate_qr(data["code"]).resize((qr_size, qr_size), Image.NEAREST)
    img.paste(qr, (0, padding_top))

    # Teks
    x   = (85 + 3) * SCALE
    gap = 17 * SCALE

    # Hitung n_rows dinamis
    row3    = bool(beratkg or bobin or berat)
    n_rows  = 4 + (1 if row3 else 0)
    total_h = (n_rows - 1) * gap + 13 * SCALE

    qr_center = padding_top + qr_size // 2
    y         = qr_center - total_h // 2

    CELTIC_FONT_PATH = r"Z:\Checker\Production\Production\templates\celtic-astrologer\CelticAstrologer.ttf"
    
    try:
        celtic_font = ImageFont.truetype(CELTIC_FONT_PATH, 18 * SCALE)
    except:
        celtic_font = font_md

    # Baris 1: Customer  Produk
    draw.text((x, y), f"{customer}    {produk}", fill=0, font=font_md)

  # Baris 2: SPK  UK  Operator  Mesin  Team
    y += gap

    mesin_text = f"M{mesin}" if mesin else ""
    team       = str(data.get("team", "") or "").strip()

    # hanya tampil di divisi tertentu
    SHOW_TEAM_DIVISI = {"PACKING", "SISA_PACK", "AVAL_PACKING"}

    parts2 = [spk, uk, operator, mesin_text]

    # tambahkan team setelah mesin kalau divisinya sesuai
    if divisi_raw in SHOW_TEAM_DIVISI and team:
        parts2.append(team)

    parts2 = [p for p in parts2 if str(p).strip()]
    line2 = "    ".join(parts2)

    draw.text((x, y), line2, fill=0, font=font_md)

    # TIKET SEMENTARA — sejajar baris 2, setelah teks baris 2
    if show_tiket_sementara:
        line2_bbox = draw.textbbox((0, 0), line2, font=font_md)
        line2_w    = line2_bbox[2] - line2_bbox[0]
        draw.text((x + line2_w + 8 * SCALE, y), "'TS'", fill=0, font=font_md)

    # Baris 3 — hanya kalau ada isinya
    if divisi_raw == "SISA_PACK":
        wadah_unit = "Pack"
    else:
        wadah_unit = "kg"

    if row3:
        y += gap
        parts3 = []
        if beratkg:
            parts3.append(f"{beratkg} kg")
        if bobin:
            parts3.append(f"{bobin} {wadah_unit}")
        if berat:
            parts3.append(f"{berat} kg")
        draw.text((x, y), "     ".join(parts3), fill=0, font=font_md)

    # Baris 4: Divisi  Tanggal  Shift  Checker
    y += gap
    draw.text((x, y), f"{divisi_display}  {tanggal} ({shift})   {checker}", fill=0, font=font_md)

    # Baris 5: created_at
    y += gap
    draw.text((x, y), created, fill=0, font=font_md)
        
    # Celtic — sejajar baris terakhir, rata kanan
    celtic_bbox = draw.textbbox((0, 0), celtic_str, font=celtic_font)
    celtic_w    = celtic_bbox[2] - celtic_bbox[0]
    celtic_x    = LABEL_W_HI - celtic_w - (4 * SCALE)
    celtic_y = y - (2 * SCALE)
    draw.text((celtic_x, celtic_y), celtic_str, fill=0, font=celtic_font)

    return img

@app.route("/label/<order_id>")
@login_required
def label(order_id):
    entry = record_cache.get(order_id)
    if not entry:
        return "Label tidak ditemukan atau sudah expired", 404

    record, _ = entry
    source_route = record.get("_source_route", "")  # ← ambil dari cache
    img = generate_label_image(order_id, record, source_route=source_route)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(600, 600))
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/label/print/<order_id>")
@login_required
def label_print(order_id):
    return f"""<!DOCTYPE html>
<html>
<head>
<title></title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    width: 80mm;
    background: white;
  }}
  .label {{
    width: 80mm;
    display: block;
  }}
  .label img {{
    width: 80mm;
    display: block;
  }}
  @media print {{
    @page {{
      margin: 0;
      size: 80mm auto;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      width: 80mm;
    }}
  }}
</style>
</head>
<body>
  <div class="label"><img src="/label/{order_id}"></div>
  <script>
    window.onload = function() {{
      var img = document.querySelector('img');
      function doPrint() {{
        window.print();
        setTimeout(function() {{
          window.print();
          setTimeout(function() {{
            window.close();
          }}, 1000);
        }}, 1500);
      }}
      if (img.complete) {{
        setTimeout(doPrint, 400);
      }} else {{
        img.onload = function() {{
          setTimeout(doPrint, 400);
        }};
      }}
    }};
  </script>
</body>
</html>"""

# ─── CODE GENERATOR ─────────────────────────────────────────
def generate_code(data):
    now = datetime.now()

    divisi = str(data.get("divisi", "")).strip().upper()

    # Default mapping
    div_map = {
        "MIXING": "MI",
        "HD": "HD",
        "POTONG": "CU",
        "PACKING": "PA",
        "SISA_PACK": "PS",
        "AVAL_MIXING": "AMS",
        "AVAL_QC": "AQC",
    }

    # Default dulu
    div = div_map.get(divisi, "XX")

    if divisi == "AVAL_HD":
        jenis_map = {
            "Prong": "AHP",
            "Daun": "AHD",
            "Sapuan": "AHS",
        }
        jenis = str(data.get("jenis_hd", "")).strip()
        div = jenis_map.get(jenis, "AHX")

    elif divisi == "AVAL_POTONG":
        jenis_map = {
            "Plong": "ACP",
            "Mesin": "ACM",
            "Silet": "ACS",
            "Mutasi": "ACH",
            "Reject": "ACR",
            "Sapuan": "ACS",
        }
        jenis = str(data.get("jenis_cu", "")).strip()
        div = jenis_map.get(jenis, "ACX")

    elif divisi == "AVAL_PACKING":
        jenis_map = {
            "Plastik": "APP",
            "Rafia": "APR",
            "Blongsong": "APB",
            "Mutasi": "APC",
        }
        jenis = str(data.get("jenis_pa", "")).strip()
        div = jenis_map.get(jenis, "APX")

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
    cols = ["No. SPK", "CUSTOMER", "PRODUCT", "UK"]
    if "JENIS AVAL" in df.columns:
        cols.append("JENIS AVAL")
    return df[cols]

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
        operator_mix TEXT, checker TEXT, berat_kg REAL,
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
        mesin REAL, berat_bersih REAL, created_at TEXT, code TEXT, team TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogsisapack (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        operator_sp TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, sisa REAL,
        created_at TEXT, code TEXT, team TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_amix TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, berat_bersih REAL, jenis REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalHD (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
        mesin REAL, jenis_hd TEXT, kategori_hd TEXT, berat_kg REAL, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
        mesin REAL, jenis_cu TEXT, kategori_cu TEXT, berat_kg REAL, berat_bersih REAL,
        created_at TEXT, code TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
        mesin REAL, jenis_pa TEXT, kategori_pa TEXT, berat_bersih REAL,
        created_at TEXT, code TEXT, team TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalqc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_qc TEXT, checker TEXT,
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
            created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_pa, :checker, :mesin, :berat_bersih,
            :created_at, :code, :team
        )""", data)
        csv_path = CSV_PACKING
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_pa","checker","mesin","berat_bersih","created_at","code","team"]

    elif div == "SISA_PACK":
        c.execute("""
        INSERT INTO katalogsisapack (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_sp, checker, mesin, berat_bersih, sisa,
            created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_sp, :checker, :mesin, :berat_bersih, :sisa,
            :created_at, :code, :team
        )""", data)
        csv_path = CSV_SISA_PACK
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_sp","checker","mesin","berat_bersih","sisa","created_at","code","team"]

    elif div == "AVAL_MIXING":
        c.execute("""
        INSERT INTO katalogavalmixing (
            tanggal, shift, divisi, spk,
            operator_amix, checker, mesin, karung, berat_kg, berat_bersih, jenis,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_amix, :checker, :mesin, :karung, :berat_kg, :berat_bersih, :jenis,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_MIXING
        headers  = ["tanggal","shift","divisi","spk",
                    "operator_amix","checker","mesin","karung","berat_kg","berat_bersih","jenis","created_at","code"]

    elif div == "AVAL_HD":
        c.execute("""
        INSERT INTO katalogavalhd (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_hd, checker, mesin, jenis_hd, kategori_hd, karung, berat_kg, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_hd, :checker, :mesin, :jenis_hd, :kategori_hd, :karung, :berat_kg, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_HD
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_hd","checker","mesin","jenis_hd","kategori_hd","karung","berat_kg","berat_bersih","created_at","code"]

    elif div == "AVAL_POTONG":
        c.execute("""
        INSERT INTO katalogavalpotong (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_cu, checker, mesin, jenis_cu, kategori_cu, karung, berat_kg, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_cu, :checker, :mesin, :jenis_cu, :kategori_cu, :karung, :berat_kg, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_POTONG
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_cu","checker","mesin","jenis_cu","kategori_cu","karung","berat_kg","berat_bersih","created_at","code"]
  
    elif div == "AVAL_PACKING":
        c.execute("""
        INSERT INTO katalogavalpacking (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_pa, checker, mesin, jenis_pa, kategori_pa, berat_bersih, 
            created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_pa, :checker, :mesin, :jenis_pa, :kategori_pa, :berat_bersih,
            :created_at, :code, :team
        )""", data)
        csv_path = CSV_AVAL_PACKING
        headers  = ["tanggal","shift","divisi","spk", "customer","produk","uk",
                    "operator_pa","checker","mesin","jenis_pa","kategori_pa","berat_bersih","created_at","code","team"]

    elif div == "AVAL_QC":
        c.execute("""
        INSERT INTO katalogavalqc (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_qc, checker, mesin, kategori_qc, berat_bersih, 
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_qc, :checker, :mesin, :kategori_qc, :berat_bersih,
            :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_QC
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_qc","checker","mesin","kategori_qc","berat_bersih","created_at","code"]


    elif div == "MIXING":
        c.execute("""
        INSERT INTO katalogmixing (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_mix, checker, berat_kg, berat_bersih, karung,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_mix, :checker, :berat_kg, :berat_bersih, :karung,
            :created_at, :code
        )""", data)
        csv_path = CSV_MIXING
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk",
                    "operator_mix","checker","berat_kg","berat_bersih","karung","created_at","code"]

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
        
import math

def safe_json(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [safe_json(i) for i in obj]
    return obj

# ROUTES
# ─── AUTH ───────────────────────────────────────────────────
@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET"])
def login_page():
    if session.get("logged_in"):
        return redirect("/mixing")
    return render_template("login.html")

@app.route("/check_session")
def check_session():
    if not session.get("logged_in"):
        return jsonify(active=False)
#
    last_active = session.get("last_active")

    if last_active:
        last_active = datetime.fromisoformat(last_active)

        if datetime.now() - last_active > timedelta(minutes=5):
            session.clear()
            return jsonify(active=False)

    return jsonify(active=True)

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
        if not match.empty:
            session.permanent      = True
            session["logged_in"]   = True
            session["username"]    = username
            session["name"]        = str(match.iloc[0].get("name", username))
            session["role"]        = str(match.iloc[0].get("role", "user"))
            session["last_active"] = datetime.now().isoformat()

            role = session["role"]
            redirect_map = {
                "administrator": "/mixing",
                "checker":       "/mixing",
                "adminwip":      "/scan_pemakaian",
                "staff":         "/hasil_produksi",
            }
            redirect_url = redirect_map.get(role, "/login")
            return jsonify(success=True, redirect=redirect_url)
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


# ─── PAGES ──────────────────────────────────────────────────
# CHECKER
@app.route("/mixing")
@login_required
@checker_required
def mixing():
    return render_template("index.html", active_page="mixing", current_user=session.get("name"))

@app.route("/hd")
@login_required
@checker_required
def hd():
    return render_template("hd.html", active_page="hd", current_user=session.get("name"))

@app.route("/potong")
@login_required
@checker_required
def potong():
    return render_template("potong.html", active_page="potong", current_user=session.get("name"))

@app.route("/packing")
@login_required
@checker_required
def packing():
    return render_template("packing.html", active_page="packing", current_user=session.get("name"))

@app.route("/sisa_pack")
@login_required
@checker_required
def sisa_pack():
    return render_template("sisa_pack.html", active_page="sisa_pack", current_user=session.get("name"))

@app.route("/aval_mixing")
@login_required
@checker_required
def aval_mixing():
    return render_template("aval_mixing.html", active_page="aval_mixing", current_user=session.get("name"))

@app.route("/aval_hd")
@login_required
@checker_required
def aval_hd():
    return render_template("aval_hd.html", active_page="aval_hd", current_user=session.get("name"))

@app.route("/aval_potong")
@login_required
@checker_required
def aval_potong():
    return render_template("aval_potong.html", active_page="aval_potong", current_user=session.get("name"))

@app.route("/aval_packing")
@login_required
@checker_required
def aval_packing():
    return render_template("aval_packing.html", active_page="aval_packing", current_user=session.get("name"))

@app.route("/aval_qc")
@login_required
@checker_required
def aval_qc():
    return render_template("aval_qc.html", active_page="aval_qc", current_user=session.get("name"))

# ADMIN WIP
@app.route("/scan_salah")
@adminwip_required
def scan_salah():
    return render_template("scan_salah.html", active_page="scan_salah", current_user=session.get("name"))

@app.route("/scan_pemakaian")
@adminwip_required
def scan_pemakaian():
    return render_template("scan_pemakaian.html", active_page="scan_pemakaian", current_user=session.get("name"))

@app.route("/barcode_mixing")
@adminwip_required
def barcode_mixing():
    return render_template("barcode_mixing.html", active_page="barcode_mixing", current_user=session.get("name"))

@app.route("/barcode_hd")
@adminwip_required
def barcode_hd():
    return render_template("barcode_hd.html", active_page="barcode_hd", current_user=session.get("name"))

@app.route("/barcode_potong")
@adminwip_required
def barcode_potong():
    return render_template("barcode_potong.html", active_page="barcode_potong", current_user=session.get("name"))

@app.route("/barcode_packing")
@adminwip_required
def barcode_packing():
    return render_template("barcode_packing.html", active_page="barcode_packing", current_user=session.get("name"))

@app.route("/barcode_sisa_pack")
@adminwip_required
def barcode_sisa_pack():
    return render_template("barcode_sisa_pack.html", active_page="barcode_sisa_pack", current_user=session.get("name"))

@app.route("/barcode_aval_mixing")
@adminwip_required
def barcode_aval_mixing():
    return render_template("barcode_aval_mixing.html", active_page="barcode_aval_mixing", current_user=session.get("name"))

@app.route("/barcode_aval_hd")
@adminwip_required
def barcode_aval_hd():
    return render_template("barcode_aval_hd.html", active_page="barcode_aval_hd", current_user=session.get("name"))

@app.route("/barcode_aval_potong")
@adminwip_required
def barcode_aval_potong():
    return render_template("barcode_aval_potong.html", active_page="barcode_aval_potong", current_user=session.get("name"))

@app.route("/barcode_aval_packing")
@adminwip_required
def barcode_aval_packing():
    return render_template("barcode_aval_packing.html", active_page="barcode_aval_packing", current_user=session.get("name"))

@app.route("/barcode_aval_qc")
@adminwip_required
def barcode_aval_qc():
    return render_template("barcode_aval_qc.html", active_page="barcode_aval_qc", current_user=session.get("name"))

@app.route("/stok_produksi")
@hasil_required
def stok_produksi():
    return render_template("stok_produksi.html", active_page="stok_produksi", current_user=session.get("name"))

@app.route("/hasil_produksi")
@hasil_required
def hasil_produksi():
    return render_template("hasil_produksi.html", active_page="hasil_produksi", current_user=session.get("name"))

@app.route("/hasil_produksi_hd")
@hasil_required
def hasil_produksi_hd():
    return render_template("hasil_produksi_hd.html", active_page="hasil_produksi_hd", current_user=session.get("name"))

@app.route("/hasil_produksi_mixing")
@hasil_required
def hasil_produksi_mixing():
    return render_template("hasil_produksi_mixing.html", active_page="hasil_produksi_mixing", current_user=session.get("name"))

@app.route("/hasil_produksi_potong")
@hasil_required
def hasil_produksi_potong():
    return render_template("hasil_produksi_potong.html", active_page="hasil_produksi_potong", current_user=session.get("name"))

@app.route("/hasil_produksi_packing")
@hasil_required
def hasil_produksi_packing():
    return render_template("hasil_produksi_packing.html", active_page="hasil_produksi_packing", current_user=session.get("name"))

# HASIL PRODUKSI
@app.route("/api/hasil_produksi")
@hasil_required
def api_hasil_produksi():
    try:
        # 1. Load master SPK
        df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig")
        df_spk.columns = df_spk.columns.str.strip()
        df_spk["No. SPK"] = df_spk["No. SPK"].astype(str).str.strip()
        raw_order = df_spk.iloc[:, 15].astype(str).str.strip()
        raw_order = raw_order.str.replace(r'[^\d,\.]', '', regex=True)
        raw_order = raw_order.str.replace('.', '', regex=False)
        raw_order = raw_order.str.replace(',', '.', regex=False)
        df_spk["order_qty"] = pd.to_numeric(raw_order, errors="coerce").fillna(0)
        df_spk = df_spk.tail(500)

        # 2. Helper: baca katalog
        def load_catalog_by_code(path, spk_col, berat_col):
            """Return dict: spk -> {code -> berat}"""
            result = {}
            if not os.path.exists(path):
                return result
            df = pd.read_csv(path, encoding="utf-8-sig")
            df.columns = df.columns.str.strip()
            col_spk   = df.columns[spk_col]
            col_berat = df.columns[berat_col]
            col_code  = df.columns[-1]
            code_candidates = [c for c in df.columns if c.lower() == "code"]
            col_code = code_candidates[0] if code_candidates else df.columns[-1]

            df[col_spk]   = df[col_spk].astype(str).str.strip()
            df[col_berat] = pd.to_numeric(df[col_berat], errors="coerce").fillna(0)
            df[col_code]  = df[col_code].astype(str).str.strip()

            for _, row in df.iterrows():
                spk   = row[col_spk]
                code  = row[col_code]
                berat = row[col_berat]
                if spk not in result:
                    result[spk] = {}
                result[spk][code] = berat
            return result

        # 3. Helper: baca scan_salah
        def load_salah_codes(path, spk_col, code_col):
            """Return dict: spk -> set of codes yang salah"""
            result = {}
            if not os.path.exists(path):
                return result
            df = pd.read_csv(path, encoding="utf-8-sig")
            df.columns = df.columns.str.strip()
            col_spk  = df.columns[spk_col]
            col_code = df.columns[code_col]
            df[col_spk]  = df[col_spk].astype(str).str.strip()
            df[col_code] = df[col_code].astype(str).str.strip()
            for _, row in df.iterrows():
                spk  = row[col_spk]
                code = row[col_code]
                if spk not in result:
                    result[spk] = set()
                result[spk].add(code)
            return result

        # 4. Helper: hitung total bersih = sum semua - sum yang salah
        def calc_net(catalog, salah, spk):
            """catalog = {spk: {code: berat}}, salah = {spk: set(codes)}"""
            all_codes   = catalog.get(spk, {})
            salah_codes = salah.get(spk, set())
            total_all   = sum(all_codes.values())
            total_salah = sum(v for k, v in all_codes.items() if k in salah_codes)
            return round(total_all - total_salah, 2), len(salah_codes) > 0

        # 5. Load katalog per divisi
        cat_mixing  = load_catalog_by_code(CSV_MIXING,    3, 10)
        cat_hd      = load_catalog_by_code(CSV_HD,        3, 12)
        cat_potong  = load_catalog_by_code(CSV_POTONG,    3, 12)
        cat_packing = load_catalog_by_code(CSV_PACKING,   3, 10)
        cat_sisa    = load_catalog_by_code(CSV_SISA_PACK, 3, 10)

        # 6. Load scan salah — SPK=E(4), code=K(10)
        salah_mixing  = load_salah_codes(SCAN_DIR / "scansalahmixing.csv",  4, 10)
        salah_hd      = load_salah_codes(SCAN_DIR / "scansalahhd.csv",      4, 10)
        salah_potong  = load_salah_codes(SCAN_DIR / "scansalahpotong.csv",  4, 10)
        salah_packing = load_salah_codes(SCAN_DIR / "scansalahpacking.csv", 4, 10)

        # 7. Gabungkan per SPK
        rows = []
        for _, r in df_spk.iterrows():
            spk = str(r["No. SPK"]).strip()

            mixing_net,  has_salah_mix  = calc_net(cat_mixing,  salah_mixing,  spk)
            hd_net,      has_salah_hd   = calc_net(cat_hd,      salah_hd,      spk)
            potong_net,  has_salah_pot  = calc_net(cat_potong,  salah_potong,  spk)
            packing_net, has_salah_pack = calc_net(cat_packing, salah_packing, spk)
            sisa_net,    has_salah_sisa = calc_net(cat_sisa,    salah_packing, spk)  # sisa pakai file packing

            rows.append({
                "spk":      spk,
                "customer": str(r.get("CUSTOMER", "") or ""),
                "produk":   str(r.get("PRODUCT",  "") or ""),
                "uk":       str(r.get("UK",        "") or ""),
                "order":    round(float(r.get("order_qty", 0) or 0), 2),
                "mixing":   mixing_net,
                "hd":       hd_net,
                "potong":   potong_net,
                "packing":  packing_net,
                "sisa":     sisa_net,
                "salah_mixing":  has_salah_mix,
                "salah_hd":      has_salah_hd,
                "salah_potong":  has_salah_pot,
                "salah_packing": has_salah_pack,
                "salah_sisa":    has_salah_sisa,
            })

        # 8. Filter query param
        f_spk      = request.args.get("spk",      "").strip().lower()
        f_customer = request.args.get("customer", "").strip().lower()
        f_produk   = request.args.get("produk",   "").strip().lower()

        if f_spk:      rows = [r for r in rows if f_spk      in r["spk"].lower()]
        if f_customer: rows = [r for r in rows if f_customer in r["customer"].lower()]
        if f_produk:   rows = [r for r in rows if f_produk   in r["produk"].lower()]

        rows.sort(key=lambda r: r["spk"])
        return jsonify({"rows": rows})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/api/hasil_produksi_hd")
@hasil_required
def api_hasil_produksi_hd():
    try:
        if not os.path.exists(CSV_HD):
            return jsonify({"rows": [], "newest_created": ""})

        df = pd.read_csv(CSV_HD, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()

        c_tanggal  = df.columns[0]
        c_shift    = df.columns[1]
        c_spk      = df.columns[3]
        c_customer = df.columns[4]
        c_produk   = df.columns[5]
        c_uk       = df.columns[6]
        c_mesin    = df.columns[9]
        c_berat    = df.columns[12]
        c_created  = df.columns[13]
        c_code     = df.columns[14]

        df[c_berat]   = pd.to_numeric(df[c_berat], errors="coerce").fillna(0)
        df[c_spk]     = df[c_spk].astype(str).str.strip()
        df[c_tanggal] = df[c_tanggal].astype(str).str.strip()
        df[c_shift]   = df[c_shift].astype(str).str.strip()
        df[c_mesin]   = df[c_mesin].astype(str).str.strip()
        df[c_code]    = df[c_code].astype(str).str.strip()
        df[c_created] = df[c_created].astype(str).str.strip()

        newest_created = df[c_created].dropna().iloc[-1] if len(df) > 0 else ""

        # ── Baca scansalahhd.csv → set kode salah ──
        bad_codes = set()
        scan_salah_path = SCAN_DIR / "scansalahhd.csv"
        if scan_salah_path.exists():
            ds = pd.read_csv(scan_salah_path, encoding="utf-8-sig")
            ds.columns = ds.columns.str.strip()
            code_candidates = [c for c in ds.columns if c.lower() == "code"]
            code_col = code_candidates[0] if code_candidates else ds.columns[-1]
            bad_codes = set(ds[code_col].astype(str).str.strip().dropna())

        df["_salah"] = df[c_code].isin(bad_codes)

        # ── Count SPK unik per (tanggal, shift) — hanya dari baris yang tidak salah ──
        # Sebuah SPK dianggap "valid" di (tanggal, shift) jika punya
        # minimal 1 baris tidak salah
        spk_valid = (
            df[~df["_salah"]]
            .groupby([c_tanggal, c_shift])[c_spk]
            .nunique()
            .to_dict()
        )  # key: (tanggal, shift) → jumlah SPK unik tidak salah

        # ── Filter request ──
        def flt(col, param):
            val = request.args.get(param, "").strip()

            if not val:
                return pd.Series(True, index=df.index)

    # FILTER TANGGAL
            if param == "tanggal":
                try:
            # input dari HTML: 2026-05-13
                    target = pd.to_datetime(val).normalize()

            # parse tanggal CSV
                    csv_dates = pd.to_datetime(
                        df[col].astype(str).str.strip(),
                        dayfirst=True,
                        errors="coerce"
                    ).dt.normalize()

                    return csv_dates == target

                except Exception as e:
                    print("ERROR FILTER TANGGAL:", e)
                    return pd.Series(False, index=df.index)

    # FILTER TEXT BIASA
            return df[col].astype(str).str.strip().str.contains(
                val,
                case=False,
                na=False
            )

        mask = (flt(c_tanggal, "tanggal") & flt(c_spk, "spk") &
                flt(c_customer, "customer") & flt(c_produk, "produk") &
                flt(c_mesin, "mesin") & flt(c_shift, "shift"))
        df = df[mask]

        # ── Group by (tanggal, spk, shift, mesin) ──
        grp_key = [c_tanggal, c_spk, c_shift, c_mesin]
        agg = df.groupby(grp_key, sort=False).apply(
            lambda g: pd.Series({
                "customer":     g[c_customer].iloc[0],
                "produk":       g[c_produk].iloc[0],
                "uk":           g[c_uk].iloc[0],
                "berat_bersih": round(g.loc[~g["_salah"], c_berat].sum(), 2),
                "total_roll":   int((~g["_salah"]).sum()),
                "has_salah":    bool(g["_salah"].any()),
            })
        ).reset_index()

        # ── Baca katalogavalhd.csv ──
        aval_daun    = {}
        aval_prong   = {}
        aval_sapuan  = {}

        if os.path.exists(CSV_AVAL_HD):
            da = pd.read_csv(CSV_AVAL_HD, encoding="utf-8-sig")
            da.columns = da.columns.str.strip()
            ca_tgl   = da.columns[0]
            ca_shift = da.columns[1]
            ca_spk   = da.columns[3]
            ca_mesin = da.columns[9]
            ca_jenis = da.columns[10]
            ca_berat = da.columns[14]

            da[ca_berat] = pd.to_numeric(da[ca_berat], errors="coerce").fillna(0)
            da[ca_spk]   = da[ca_spk].astype(str).str.strip()
            da[ca_tgl]   = da[ca_tgl].astype(str).str.strip()
            da[ca_shift] = da[ca_shift].astype(str).str.strip()
            da[ca_mesin] = da[ca_mesin].astype(str).str.strip()
            da[ca_jenis] = da[ca_jenis].astype(str).str.strip()

            aval_code_candidates = [c for c in da.columns if c.lower() == "code"]
            if aval_code_candidates:
                ca_code = aval_code_candidates[0]
                da[ca_code] = da[ca_code].astype(str).str.strip()
                da["_salah"] = da[ca_code].isin(bad_codes)
            else:
                da["_salah"] = False

            # Daun & Prong: group normal per (tanggal, spk, shift, mesin)
            def aval_sum(jenis_val):
                sub = da[
                    (da[ca_jenis].str.lower() == jenis_val.lower()) &
                    (~da["_salah"])
                ]
                return sub.groupby([ca_tgl, ca_spk, ca_shift, ca_mesin])[ca_berat].sum().to_dict()

            aval_daun  = aval_sum("daun")
            aval_prong = aval_sum("prong")

            # ── Sapuan: total per (tanggal, shift) lalu bagi count SPK tidak salah ──
            sub_sap = da[
                (da[ca_jenis].str.lower() == "sapuan") &
                (~da["_salah"])
            ]
            sapuan_per_tgl_shift = (
                sub_sap.groupby([ca_tgl, ca_shift])[ca_berat]
                .sum()
                .to_dict()
            )  # key: (tanggal, shift) → total berat sapuan

            # Bangun aval_sapuan per key (tanggal, spk, shift, mesin)
            for _, r in agg.iterrows():
                tgl   = str(r[c_tanggal])
                spk   = str(r[c_spk])
                shift = str(r[c_shift])
                mesin = str(r[c_mesin])
                key   = (tgl, spk, shift, mesin)

                total_sap = sapuan_per_tgl_shift.get((tgl, shift), 0)
                count_spk = spk_valid.get((tgl, shift), 1)
                aval_sapuan[key] = round(total_sap / count_spk, 2) if count_spk > 0 else 0

        # ── Bangun respons ──
        rows = []
        for _, r in agg.iterrows():
            key = (str(r[c_tanggal]), str(r[c_spk]), str(r[c_shift]), str(r[c_mesin]))
            rows.append({
                "tanggal":      r[c_tanggal],
                "mesin":        r[c_mesin],
                "spk":          r[c_spk],
                "customer":     r["customer"],
                "produk":       r["produk"],
                "uk":           r["uk"],
                "berat_bersih": float(r["berat_bersih"]),
                "total_roll":   int(r["total_roll"]),
                "shift":        r[c_shift],
                "afal_daun":    round(float(aval_daun.get(key, 0)), 2),
                "afal_prong":   round(float(aval_prong.get(key, 0)), 2),
                "afal_sapuan":  round(float(aval_sapuan.get(key, 0)), 2),
                "has_salah":    r["has_salah"],
            })

        from datetime import datetime
        def parse_tgl(t):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(t), fmt)
                except:
                    continue
            return datetime.min

        rows.sort(key=lambda r: parse_tgl(r["tanggal"]), reverse=True)
        return jsonify(safe_json({"rows": rows, "newest_created": newest_created}))

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500
    
@app.route("/api/hasil_produksi_mixing")
@hasil_required
def api_hasil_produksi_mixing():
    try:
        if not os.path.exists(CSV_MIXING):
            return jsonify({"rows": [], "newest_created": ""})

        df = pd.read_csv(CSV_MIXING, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()

        # Struktur katalogmixing: tanggal(0) shift(1) divisi(2) spk(3)
        # customer(4) produk(5) uk(6) operator_mix(7) checker(8)
        # berat_kg(9) berat_bersih(10) karung(11) created_at(12) code(13)
        c_tanggal  = df.columns[0]
        c_shift    = df.columns[1]
        c_spk      = df.columns[3]
        c_customer = df.columns[4]
        c_produk   = df.columns[5]
        c_uk       = df.columns[6]
        c_berat    = df.columns[10]
        c_created  = df.columns[12]
        c_code     = df.columns[13]

        df[c_berat]   = pd.to_numeric(df[c_berat], errors="coerce").fillna(0)
        df[c_spk]     = df[c_spk].astype(str).str.strip()
        df[c_tanggal] = df[c_tanggal].astype(str).str.strip()
        df[c_shift]   = df[c_shift].astype(str).str.strip()
        df[c_code]    = df[c_code].astype(str).str.strip()
        df[c_created] = df[c_created].astype(str).str.strip()

        newest_created = df[c_created].dropna().iloc[-1] if len(df) > 0 else ""

        # ── Baca scansalahmixing.csv → set kode salah ──
        bad_codes = set()
        scan_salah_path = SCAN_DIR / "scansalahmixing.csv"
        if scan_salah_path.exists():
            ds = pd.read_csv(scan_salah_path, encoding="utf-8-sig")
            ds.columns = ds.columns.str.strip()
            code_candidates = [c for c in ds.columns if c.lower() == "code"]
            code_col = code_candidates[0] if code_candidates else ds.columns[-1]
            bad_codes = set(ds[code_col].astype(str).str.strip().dropna())

        df["_salah"] = df[c_code].isin(bad_codes)

        # ── Count SPK unik per (tanggal, shift) — hanya dari baris tidak salah ──
        # Dihitung SEBELUM filter request agar tidak terpengaruh filter user
        spk_valid = (
            df[~df["_salah"]]
            .groupby([c_tanggal, c_shift])[c_spk]
            .nunique()
            .to_dict()
        )  # key: (tanggal, shift) → jumlah SPK unik tidak salah

# ── Filter request ──
        def flt(col, param):
            val = request.args.get(param, "").strip()

    # kosong = tampil semua
            if not val:
                return pd.Series(True, index=df.index)

    # ==========================
    # FILTER TANGGAL
    # ==========================
            if param == "tanggal":
                try:
            # dari input HTML date
                    target_date = pd.to_datetime(
                        val,
                        format="%Y-%m-%d",
                        errors="coerce"
                    )

            # parse semua format tanggal CSV
                    csv_dates = pd.to_datetime(
                        df[col].astype(str).str.strip(),
                        dayfirst=True,
                        errors="coerce"
                    )

            # debug terminal
                    print("TARGET:", target_date)
                    print("CSV SAMPLE:", df[col].head(10).tolist())
                    print("CSV PARSED:", csv_dates.head(10).tolist())

            # bandingkan hanya tanggalnya (tanpa jam)
                    return csv_dates.dt.date == target_date.date()

                except Exception as e:
                    print("ERROR FILTER:", e)
                    return pd.Series(False, index=df.index)

    # FILTER TEXT BIASA
            return (
                df[col]
                .astype(str)
                .str.strip()
                .str.contains(val, case=False, na=False)
            )

        mask = (flt(c_tanggal, "tanggal") & flt(c_spk, "spk") &
                flt(c_customer, "customer") & flt(c_produk, "produk") &
                flt(c_shift, "shift"))
        df = df[mask]

        # ── Group by (tanggal, spk, shift) ──
        grp_key = [c_tanggal, c_spk, c_shift]
        agg = df.groupby(grp_key, sort=False).apply(
            lambda g: pd.Series({
                "customer":     g[c_customer].iloc[0],
                "produk":       g[c_produk].iloc[0],
                "uk":           g[c_uk].iloc[0],
                "berat_bersih": round(g.loc[~g["_salah"], c_berat].sum(), 2),
                "total_karung": int((~g["_salah"]).sum()),
                "has_salah":    bool(g["_salah"].any()),
            })
        ).reset_index()

        # ── Baca katalogavalmixing.csv ──
        # Struktur: tanggal(0) shift(1) divisi(2) spk(3)
        # operator_amix(4) checker(5) mesin(6) karung(7) berat_kg(8)
        # berat_bersih(9) jenis(10) created_at(11) code(12)
        aval_sapuan = {}
        if os.path.exists(CSV_AVAL_MIXING):
            da = pd.read_csv(CSV_AVAL_MIXING, encoding="utf-8-sig")
            da.columns = da.columns.str.strip()
            ca_tgl   = da.columns[0]
            ca_shift = da.columns[1]
            ca_berat = da.columns[9]

            da[ca_berat] = pd.to_numeric(da[ca_berat], errors="coerce").fillna(0)
            da[ca_tgl]   = da[ca_tgl].astype(str).str.strip()
            da[ca_shift] = da[ca_shift].astype(str).str.strip()

            # Exclude kode aval yang salah
            aval_code_candidates = [c for c in da.columns if c.lower() == "code"]
            if aval_code_candidates:
                ca_code = aval_code_candidates[0]
                da[ca_code] = da[ca_code].astype(str).str.strip()
                da["_salah"] = da[ca_code].isin(bad_codes)
            else:
                da["_salah"] = False

            # Total sapuan per (tanggal, shift) — tidak digroup per spk
            sapuan_per_tgl_shift = (
                da[~da["_salah"]]
                .groupby([ca_tgl, ca_shift])[ca_berat]
                .sum()
                .to_dict()
            )  # key: (tanggal, shift) → total berat sapuan

            # Bangun aval_sapuan per key (tanggal, spk, shift)
            for _, r in agg.iterrows():
                tgl   = str(r[c_tanggal])
                spk   = str(r[c_spk])
                shift = str(r[c_shift])
                key   = (tgl, spk, shift)

                total_sap = sapuan_per_tgl_shift.get((tgl, shift), 0)
                count_spk = spk_valid.get((tgl, shift), 1)
                aval_sapuan[key] = round(total_sap / count_spk, 2) if count_spk > 0 else 0

        # ── Bangun respons ──
        rows = []
        for _, r in agg.iterrows():
            key = (str(r[c_tanggal]), str(r[c_spk]), str(r[c_shift]))
            rows.append({
                "tanggal":      r[c_tanggal],
                "spk":          r[c_spk],
                "customer":     r["customer"],
                "produk":       r["produk"],
                "uk":           r["uk"],
                "berat_bersih": float(r["berat_bersih"]),
                "total_karung": int(r["total_karung"]),
                "shift":        r[c_shift],
                "aval_mixing":  round(float(aval_sapuan.get(key, 0)), 2),
                "has_salah":    r["has_salah"],
            })

        from datetime import datetime
        def parse_tgl(t):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(t), fmt)
                except:
                    continue
            return datetime.min

        rows.sort(key=lambda r: parse_tgl(r["tanggal"]), reverse=True)
        return jsonify(safe_json({"rows": rows, "newest_created": newest_created}))

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500
    
@app.route("/api/hasil_produksi_potong")
@hasil_required
def api_hasil_produksi_potong():
    try:
        if not os.path.exists(CSV_POTONG):
            return jsonify({"rows": [], "newest_created": ""})

        df = pd.read_csv(CSV_POTONG, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()

        # Struktur katalogpotong: tanggal(0) shift(1) divisi(2) spk(3)
        # customer(4) produk(5) uk(6) operator_cu(7) checker(8)
        # mesin(9) berat_kg(10) keranjang(11) berat_bersih(12) created_at(13) code(14)
        c_tanggal  = df.columns[0]
        c_shift    = df.columns[1]
        c_spk      = df.columns[3]
        c_customer = df.columns[4]
        c_produk   = df.columns[5]
        c_uk       = df.columns[6]
        c_mesin    = df.columns[9]
        c_berat    = df.columns[12]
        c_created  = df.columns[13]
        c_code     = df.columns[14]

        df[c_berat]   = pd.to_numeric(df[c_berat], errors="coerce").fillna(0)
        df[c_spk]     = df[c_spk].astype(str).str.strip()
        df[c_tanggal] = df[c_tanggal].astype(str).str.strip()
        df[c_shift]   = df[c_shift].astype(str).str.strip()
        df[c_mesin]   = df[c_mesin].astype(str).str.strip()
        df[c_code]    = df[c_code].astype(str).str.strip()
        df[c_created] = df[c_created].astype(str).str.strip()

        newest_created = df[c_created].dropna().iloc[-1] if len(df) > 0 else ""

        # ── Baca scansalahpotong.csv → set kode salah ──
        bad_codes = set()
        scan_salah_path = SCAN_DIR / "scansalahpotong.csv"
        if scan_salah_path.exists():
            ds = pd.read_csv(scan_salah_path, encoding="utf-8-sig")
            ds.columns = ds.columns.str.strip()
            code_candidates = [c for c in ds.columns if c.lower() == "code"]
            code_col = code_candidates[0] if code_candidates else ds.columns[-1]
            bad_codes = set(ds[code_col].astype(str).str.strip().dropna())

        df["_salah"] = df[c_code].isin(bad_codes)

        # ── Count SPK unik per (tanggal, shift) — hanya baris tidak salah ──
        # Dihitung SEBELUM filter request
        spk_valid = (
            df[~df["_salah"]]
            .groupby([c_tanggal, c_shift])[c_spk]
            .nunique()
            .to_dict()
        )

        # ── Filter request ──
        def flt(col, param):
            val = request.args.get(param, "").strip()

            if not val:
                return pd.Series(True, index=df.index)

    # FILTER TANGGAL
            if param == "tanggal":
                try:
            # input dari HTML: 2026-05-13
                    target = pd.to_datetime(val).normalize()

            # parse tanggal CSV
                    csv_dates = pd.to_datetime(
                        df[col].astype(str).str.strip(),
                        dayfirst=True,
                        errors="coerce"
                    ).dt.normalize()

                    return csv_dates == target

                except Exception as e:
                    print("ERROR FILTER TANGGAL:", e)
                    return pd.Series(False, index=df.index)

    # FILTER TEXT BIASA
            return df[col].astype(str).str.strip().str.contains(
                val,
                case=False,
                na=False
            )

        mask = (flt(c_tanggal, "tanggal") & flt(c_spk, "spk") &
                flt(c_customer, "customer") & flt(c_produk, "produk") &
                flt(c_mesin, "mesin") & flt(c_shift, "shift"))
        df = df[mask]

        # ── Group by (tanggal, spk, shift, mesin) ──
        grp_key = [c_tanggal, c_spk, c_shift, c_mesin]
        agg = df.groupby(grp_key, sort=False).apply(
            lambda g: pd.Series({
                "customer":     g[c_customer].iloc[0],
                "produk":       g[c_produk].iloc[0],
                "uk":           g[c_uk].iloc[0],
                "berat_bersih": round(g.loc[~g["_salah"], c_berat].sum(), 2),
                "total_roll":   int((~g["_salah"]).sum()),
                "has_salah":    bool(g["_salah"].any()),
            })
        ).reset_index()

        # ── Baca katalogavalpotong.csv ──
        # Struktur: tanggal(0) shift(1) divisi(2) spk(3) customer(4) produk(5) uk(6)
        # operator_cu(7) checker(8) mesin(9) jenis_cu(10) kategori_cu(11)
        # karung(12) berat_kg(13) berat_bersih(14) created_at(15) code(16)
        aval_plong   = {}
        aval_mesin   = {}
        aval_silet   = {}
        aval_mutasi  = {}
        aval_reject  = {}
        aval_sapuan  = {}

        if os.path.exists(CSV_AVAL_POTONG):
            da = pd.read_csv(CSV_AVAL_POTONG, encoding="utf-8-sig")
            da.columns = da.columns.str.strip()
            ca_tgl   = da.columns[0]
            ca_shift = da.columns[1]
            ca_spk   = da.columns[3]
            ca_mesin = da.columns[9]
            ca_jenis = da.columns[10]
            ca_berat = da.columns[14]

            da[ca_berat] = pd.to_numeric(da[ca_berat], errors="coerce").fillna(0)
            da[ca_spk]   = da[ca_spk].astype(str).str.strip()
            da[ca_tgl]   = da[ca_tgl].astype(str).str.strip()
            da[ca_shift] = da[ca_shift].astype(str).str.strip()
            da[ca_mesin] = da[ca_mesin].astype(str).str.strip()
            da[ca_jenis] = da[ca_jenis].astype(str).str.strip()

            aval_code_candidates = [c for c in da.columns if c.lower() == "code"]
            if aval_code_candidates:
                ca_code = aval_code_candidates[0]
                da[ca_code] = da[ca_code].astype(str).str.strip()
                da["_salah"] = da[ca_code].isin(bad_codes)
            else:
                da["_salah"] = False

            # Plong, Mesin, Silet, Mutasi, Reject — match normal per (tanggal, spk, shift, mesin)
            def aval_sum(jenis_val):
                sub = da[
                    (da[ca_jenis].str.lower() == jenis_val.lower()) &
                    (~da["_salah"])
                ]
                return sub.groupby([ca_tgl, ca_spk, ca_shift, ca_mesin])[ca_berat].sum().to_dict()

            aval_plong  = aval_sum("plong")
            aval_mesin  = aval_sum("mesin")
            aval_silet  = aval_sum("silet")
            aval_mutasi = aval_sum("mutasi")
            aval_reject = aval_sum("reject")

            # Sapuan — total per (tanggal, shift) dibagi count SPK unik tidak salah
            sub_sap = da[
                (da[ca_jenis].str.lower() == "sapuan") &
                (~da["_salah"])
            ]
            sapuan_per_tgl_shift = (
                sub_sap.groupby([ca_tgl, ca_shift])[ca_berat]
                .sum()
                .to_dict()
            )

            for _, r in agg.iterrows():
                tgl   = str(r[c_tanggal])
                spk   = str(r[c_spk])
                shift = str(r[c_shift])
                mesin = str(r[c_mesin])
                key   = (tgl, spk, shift, mesin)

                total_sap = sapuan_per_tgl_shift.get((tgl, shift), 0)
                count_spk = spk_valid.get((tgl, shift), 1)
                aval_sapuan[key] = round(total_sap / count_spk, 2) if count_spk > 0 else 0

        # ── Bangun respons ──
        rows = []
        for _, r in agg.iterrows():
            key = (str(r[c_tanggal]), str(r[c_spk]), str(r[c_shift]), str(r[c_mesin]))
            rows.append({
                "tanggal":      r[c_tanggal],
                "mesin":        r[c_mesin],
                "spk":          r[c_spk],
                "customer":     r["customer"],
                "produk":       r["produk"],
                "uk":           r["uk"],
                "berat_bersih": float(r["berat_bersih"]),
                "total_roll":   int(r["total_roll"]),
                "shift":        r[c_shift],
                "afal_plong":   round(float(aval_plong.get(key, 0)), 2),
                "afal_mesin":   round(float(aval_mesin.get(key, 0)), 2),
                "afal_silet":   round(float(aval_silet.get(key, 0)), 2),
                "afal_mutasi":  round(float(aval_mutasi.get(key, 0)), 2),
                "afal_reject":  round(float(aval_reject.get(key, 0)), 2),
                "afal_sapuan":  round(float(aval_sapuan.get(key, 0)), 2),
                "has_salah":    r["has_salah"],
            })

        from datetime import datetime
        def parse_tgl(t):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(t), fmt)
                except:
                    continue
            return datetime.min

        rows.sort(key=lambda r: parse_tgl(r["tanggal"]), reverse=True)
        return jsonify(safe_json({"rows": rows, "newest_created": newest_created}))

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500
    
@app.route("/api/hasil_produksi_packing")
@hasil_required
def api_hasil_produksi_packing():
    try:
        if not os.path.exists(CSV_PACKING):
            return jsonify({"rows": [], "newest_created": ""})

        df = pd.read_csv(CSV_PACKING, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()

        # Struktur katalogpacking: tanggal(0) shift(1) divisi(2) spk(3)
        # customer(4) produk(5) uk(6) operator_pa(7) checker(8)
        # mesin(9) berat_bersih(10) created_at(11) code(12)
        c_tanggal  = df.columns[0]
        c_shift    = df.columns[1]
        c_spk      = df.columns[3]
        c_customer = df.columns[4]
        c_produk   = df.columns[5]
        c_uk       = df.columns[6]
        c_mesin    = df.columns[9]
        c_berat    = df.columns[10]
        c_created  = df.columns[11]
        c_code     = df.columns[12]

        df[c_berat]   = pd.to_numeric(df[c_berat], errors="coerce").fillna(0)
        df[c_spk]     = df[c_spk].astype(str).str.strip()
        df[c_tanggal] = df[c_tanggal].astype(str).str.strip()
        df[c_shift]   = df[c_shift].astype(str).str.strip()
        df[c_mesin]   = df[c_mesin].astype(str).str.strip()
        df[c_code]    = df[c_code].astype(str).str.strip()
        df[c_created] = df[c_created].astype(str).str.strip()

        newest_created = df[c_created].dropna().iloc[-1] if len(df) > 0 else ""

        # ── Baca scansalahpacking.csv → set kode salah ──
        bad_codes = set()
        scan_salah_path = SCAN_DIR / "scansalahpacking.csv"
        if scan_salah_path.exists():
            ds = pd.read_csv(scan_salah_path, encoding="utf-8-sig")
            ds.columns = ds.columns.str.strip()
            code_candidates = [c for c in ds.columns if c.lower() == "code"]
            code_col = code_candidates[0] if code_candidates else ds.columns[-1]
            bad_codes = set(ds[code_col].astype(str).str.strip().dropna())

        df["_salah"] = df[c_code].isin(bad_codes)

        # ── Filter request — SEBELUM spk_valid dihitung ──
        # spk_valid tidak diperlukan (tidak ada sapuan), tapi filter tetap sebelum group
        def flt(col, param):
            val = request.args.get(param, "").strip()

            if not val:
                return pd.Series(True, index=df.index)

    # FILTER TANGGAL
            if param == "tanggal":
                try:
            # input dari HTML: 2026-05-13
                    target = pd.to_datetime(val).normalize()

            # parse tanggal CSV
                    csv_dates = pd.to_datetime(
                        df[col].astype(str).str.strip(),
                        dayfirst=True,
                        errors="coerce"
                    ).dt.normalize()

                    return csv_dates == target

                except Exception as e:
                    print("ERROR FILTER TANGGAL:", e)
                    return pd.Series(False, index=df.index)

    # FILTER TEXT BIASA
            return df[col].astype(str).str.strip().str.contains(
                val,
                case=False,
                na=False
            )

        mask = (flt(c_tanggal, "tanggal") & flt(c_spk, "spk") &
                flt(c_customer, "customer") & flt(c_produk, "produk") &
                flt(c_mesin, "mesin") & flt(c_shift, "shift"))
        df = df[mask]

        # ── Group by (tanggal, spk, shift, mesin) ──
        grp_key = [c_tanggal, c_spk, c_shift, c_mesin]
        agg = df.groupby(grp_key, sort=False).apply(
            lambda g: pd.Series({
                "customer":     g[c_customer].iloc[0],
                "produk":       g[c_produk].iloc[0],
                "uk":           g[c_uk].iloc[0],
                "berat_bersih": round(g.loc[~g["_salah"], c_berat].sum(), 2),
                "total_karung": int((~g["_salah"]).sum()),
                "has_salah":    bool(g["_salah"].any()),
            })
        ).reset_index()

        # ── Baca katalogsisapack.csv ──
        # Struktur: tanggal(0) shift(1) divisi(2) spk(3) customer(4) produk(5) uk(6)
        # operator_sp(7) checker(8) mesin(9) berat_bersih(10) sisa(11) created_at(12) code(13)
        sisa_berat = {}  # key: (tanggal, spk, shift, mesin) → total berat_bersih sisa
        sisa_pack  = {}  # key: (tanggal, spk, shift, mesin) → total sisa (jumlah pack)

        if os.path.exists(CSV_SISA_PACK):
            ds = pd.read_csv(CSV_SISA_PACK, encoding="utf-8-sig")
            ds.columns = ds.columns.str.strip()
            cs_tgl   = ds.columns[0]
            cs_shift = ds.columns[1]
            cs_spk   = ds.columns[3]
            cs_mesin = ds.columns[9]
            cs_berat = ds.columns[10]
            cs_sisa  = ds.columns[11]
            cs_code  = ds.columns[12]

            ds[cs_berat] = pd.to_numeric(ds[cs_berat], errors="coerce").fillna(0)
            ds[cs_sisa]  = pd.to_numeric(ds[cs_sisa],  errors="coerce").fillna(0)
            ds[cs_spk]   = ds[cs_spk].astype(str).str.strip()
            ds[cs_tgl]   = ds[cs_tgl].astype(str).str.strip()
            ds[cs_shift] = ds[cs_shift].astype(str).str.strip()
            ds[cs_mesin] = ds[cs_mesin].astype(str).str.strip()

            # Exclude kode salah dari sisa pack (pakai bad_codes yang sama)
            sisa_code_candidates = [c for c in ds.columns if c.lower() == "code"]
            if sisa_code_candidates:
                cs_code = sisa_code_candidates[0]
                ds[cs_code]   = ds[cs_code].astype(str).str.strip()
                ds["_salah"]  = ds[cs_code].isin(bad_codes)
            else:
                ds["_salah"] = False

            ds_valid = ds[~ds["_salah"]]

            sisa_berat = (
                ds_valid.groupby([cs_tgl, cs_spk, cs_shift, cs_mesin])[cs_berat]
                .sum().to_dict()
            )
            sisa_pack = (
                ds_valid.groupby([cs_tgl, cs_spk, cs_shift, cs_mesin])[cs_sisa]
                .sum().to_dict()
            )

        # ── Baca katalogavalpacking.csv ──
        # Struktur: tanggal(0) shift(1) divisi(2) spk(3) customer(4) produk(5) uk(6)
        # operator_pa(7) checker(8) mesin(9) jenis_pa(10) kategori_pa(11)
        # berat_bersih(12) created_at(13) code(14)
        aval_plastik  = {}
        aval_rafia    = {}
        aval_blongsong = {}
        aval_mutasi   = {}

        if os.path.exists(CSV_AVAL_PACKING):
            da = pd.read_csv(CSV_AVAL_PACKING, encoding="utf-8-sig")
            da.columns = da.columns.str.strip()
            ca_tgl   = da.columns[0]
            ca_shift = da.columns[1]
            ca_spk   = da.columns[3]
            ca_mesin = da.columns[9]
            ca_jenis = da.columns[10]
            ca_berat = da.columns[12]

            da[ca_berat] = pd.to_numeric(da[ca_berat], errors="coerce").fillna(0)
            da[ca_spk]   = da[ca_spk].astype(str).str.strip()
            da[ca_tgl]   = da[ca_tgl].astype(str).str.strip()
            da[ca_shift] = da[ca_shift].astype(str).str.strip()
            da[ca_mesin] = da[ca_mesin].astype(str).str.strip()
            da[ca_jenis] = da[ca_jenis].astype(str).str.strip()

            aval_code_candidates = [c for c in da.columns if c.lower() == "code"]
            if aval_code_candidates:
                ca_code = aval_code_candidates[0]
                da[ca_code] = da[ca_code].astype(str).str.strip()
                da["_salah"] = da[ca_code].isin(bad_codes)
            else:
                da["_salah"] = False

            def aval_sum(jenis_val):
                sub = da[
                    (da[ca_jenis].str.lower() == jenis_val.lower()) &
                    (~da["_salah"])
                ]
                return sub.groupby([ca_tgl, ca_spk, ca_shift, ca_mesin])[ca_berat].sum().to_dict()

            aval_plastik   = aval_sum("plastik")
            aval_rafia     = aval_sum("rafia")
            aval_blongsong = aval_sum("blongsong")
            aval_mutasi    = aval_sum("mutasi")

        # ── Bangun respons ──
        rows = []
        for _, r in agg.iterrows():
            key = (str(r[c_tanggal]), str(r[c_spk]), str(r[c_shift]), str(r[c_mesin]))
            rows.append({
                "tanggal":       r[c_tanggal],
                "mesin":         r[c_mesin],
                "spk":           r[c_spk],
                "customer":      r["customer"],
                "produk":        r["produk"],
                "uk":            r["uk"],
                "berat_bersih":  float(r["berat_bersih"]),
                "total_karung":  int(r["total_karung"]),
                "sisa_berat":    round(float(sisa_berat.get(key, 0)), 2),
                "sisa_pack":     round(float(sisa_pack.get(key, 0)), 2),
                "shift":         r[c_shift],
                "afal_plastik":  round(float(aval_plastik.get(key, 0)), 2),
                "afal_rafia":    round(float(aval_rafia.get(key, 0)), 2),
                "afal_blongsong":round(float(aval_blongsong.get(key, 0)), 2),
                "afal_mutasi":   round(float(aval_mutasi.get(key, 0)), 2),
                "has_salah":     r["has_salah"],
            })

        from datetime import datetime
        def parse_tgl(t):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(t), fmt)
                except:
                    continue
            return datetime.min

        rows.sort(key=lambda r: parse_tgl(r["tanggal"]), reverse=True)
        return jsonify(safe_json({"rows": rows, "newest_created": newest_created}))

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500

# STOK PRODUKSI
@app.route("/api/stok_produksi")
@hasil_required
def api_stok_produksi():
    try:
        spk_filter      = request.args.get("spk",      "").strip().lower()
        customer_filter = request.args.get("customer", "").strip().lower()
        produk_filter   = request.args.get("produk",   "").strip().lower()
        uk_filter       = request.args.get("uk",       "").strip().lower()

        # ── Load Summary SPK ──────────────────────────────────────
        df_spk = pd.read_csv(SPK_CSV, dtype=str, encoding="utf-8-sig", low_memory=False)
        df_spk.columns = df_spk.columns.str.strip().str.lower()
        df_spk = df_spk.tail(500)

        # rename kolom — toleran terhadap berbagai nama
        rename_map = {}
        for c in df_spk.columns:
            if c in ("no. spk", "no.spk", "no spk"):
                rename_map[c] = "spk"
            elif c in ("product", "produk", "products"):
                rename_map[c] = "produk"
            elif c == "customer":
                rename_map[c] = "customer"
            elif c == "uk":
                rename_map[c] = "uk"
        df_spk.rename(columns=rename_map, inplace=True)

        # pastikan kolom ada
        for col in ["spk", "customer", "produk", "uk"]:
            if col not in df_spk.columns:
                df_spk[col] = ""

        df_spk = df_spk[["spk", "customer", "produk", "uk"]].fillna("")

        # ── Helper: ambil set kode salah / sudah dipakai ──────────
        def load_codes(path):
            if not os.path.exists(path):
                return set()
            try:
                df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False)
                df.columns = df.columns.str.strip().str.lower()
                code_col = next((c for c in df.columns if c == "code"), None)
                if not code_col:
                    return set()
                return set(df[code_col].str.strip().dropna())
            except Exception as e:
                print(f"WARN load_codes({path}): {e}")
                return set()

        # ── Helper: count stok per SPK ────────────────────────────
        def calc_stok(cat_path, bad_codes, used_codes):
            if not os.path.exists(cat_path):
                return {}
            try:
                df = pd.read_csv(cat_path, dtype=str, encoding="utf-8-sig", low_memory=False)
                df.columns = df.columns.str.strip().str.lower()

                # cari kolom spk
                spk_col = next(
                    (c for c in df.columns if c in ("spk", "no. spk", "no.spk", "no spk")),
                    None
                )
                if not spk_col:
                    # fallback: pakai kolom index 3
                    spk_col = df.columns[3]

                # cari kolom code
                code_col = next((c for c in df.columns if c == "code"), df.columns[-1])

                df[spk_col]  = df[spk_col].astype(str).str.strip()
                df[code_col] = df[code_col].astype(str).str.strip()

                exclude  = bad_codes | used_codes
                df_valid = df[~df[code_col].isin(exclude)]

                return df_valid.groupby(spk_col).size().to_dict()

            except Exception as e:
                print(f"WARN calc_stok({cat_path}): {e}")
                return {}

        # ── Load kode salah ───────────────────────────────────────
        bad_mixing  = load_codes(str(SCAN_DIR / "scansalahmixing.csv"))
        bad_hd      = load_codes(str(SCAN_DIR / "scansalahhd.csv"))
        bad_potong  = load_codes(str(SCAN_DIR / "scansalahpotong.csv"))
        bad_packing = load_codes(str(SCAN_DIR / "scansalahpacking.csv"))
        bad_sisa    = load_codes(str(SCAN_DIR / "scansalahqc.csv"))

        # ── Load kode yang sudah dipakai ──────────────────────────
        used_mixing  = load_codes(str(SCAN_PDIR / "scanmixing.csv"))
        used_hd      = load_codes(str(SCAN_PDIR / "scanhd.csv"))
        used_potong  = load_codes(str(SCAN_PDIR / "scanpotong.csv"))
        used_packing = load_codes(str(SCAN_PDIR / "scanpacking.csv"))
        used_sisa    = load_codes(str(SCAN_PDIR / "scanpacking.csv"))

        # ── Hitung stok ───────────────────────────────────────────
        stok_mixing  = calc_stok(CSV_MIXING,   bad_mixing,  used_mixing)
        stok_hd      = calc_stok(CSV_HD,       bad_hd,      used_hd)
        stok_potong  = calc_stok(CSV_POTONG,   bad_potong,  used_potong)
        stok_packing = calc_stok(CSV_PACKING,  bad_packing, used_packing)
        stok_sisa    = calc_stok(CSV_SISA_PACK,bad_sisa,    used_sisa)

        # ── Gabungkan ke SPK ──────────────────────────────────────
        rows = []
        for _, r in df_spk.iterrows():
            spk = str(r["spk"]).strip()
            rows.append({
                "spk":      spk,
                "customer": r["customer"],
                "produk":   r["produk"],
                "uk":       r["uk"],
                "mixing":   int(stok_mixing.get(spk,  0)),
                "hd":       int(stok_hd.get(spk,      0)),
                "potong":   int(stok_potong.get(spk,  0)),
                "packing":  int(stok_packing.get(spk, 0)),
                "sisa_pack":int(stok_sisa.get(spk,    0)),
            })

        # ── Filter ────────────────────────────────────────────────
        if spk_filter:
            rows = [r for r in rows if spk_filter      in r["spk"].lower()]
        if customer_filter:
            rows = [r for r in rows if customer_filter in r["customer"].lower()]
        if produk_filter:
            rows = [r for r in rows if produk_filter   in r["produk"].lower()]
        if uk_filter:
            rows = [r for r in rows if uk_filter       in r["uk"].lower()]

        return jsonify({"rows": rows})

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("ERROR stok_produksi:\n", tb)
        return jsonify({"rows": [], "error": str(e), "detail": tb}), 500

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
    
@app.route("/api/operators_team/<divisi>")
@login_required
def get_operators_team(divisi):
    try:
        df = pd.read_csv(MAPPING_CSV, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()
        df["divisi"] = df["divisi"].astype(str).str.strip().str.upper()

        filtered = df[df["divisi"] == divisi.strip().upper()]

        op_col   = df.columns[4]
        team_col = df.columns[5] if len(df.columns) > 5 else None

        result = []
        for _, row in filtered.iterrows():
            result.append({
                "operator": str(row[op_col]).strip(),
                "team":     str(row[team_col]).strip() if team_col else ""
            })

        return jsonify(result)

    except Exception as e:
        print("ERROR get_operators_team:", e)
        return jsonify([])    
    
@app.route("/api/tali/<kategori>")
@login_required
def get_tali(kategori):
    try:
        df = pd.read_excel(USER_EXCEL, sheet_name="Tali", engine="openpyxl")
        df.columns = df.columns.str.strip()
        df["kategori_aval"] = df["kategori_aval"].astype(str).str.strip()
        row = df[df["kategori_aval"] == kategori.strip()]
        if not row.empty:
            return jsonify({"warna": str(row.iloc[0].get("warna_tali", ""))})
        return jsonify({"warna": ""})
    except Exception as e:
        return jsonify({"warna": "", "error": str(e)})

# ─── API: SPK LOOKUP ────────────────────────────────────────
@app.route("/get-spk/<spk>")
@login_required
def get_spk(spk):
    df  = load_spk_data()
    row = df[df["No. SPK"].astype(str) == str(spk)]
    if not row.empty:
        r = row.iloc[0]
        return jsonify({
            "customer":   r["CUSTOMER"],
            "product":    r["PRODUCT"],
            "uk":         r["UK"],
            "jenis_aval": str(r.get("JENIS AVAL", "") or ""),
        })
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

        prefix, csv_file, catalog_key, divisi_label = get_prefix_from_code(code)

        if not prefix or catalog_key not in CATALOG_MAP:
            return jsonify(
                found=False,
                error=f"Prefix kode tidak dikenal",
                prefix=prefix or "",
                divisi_label="Unknown",
                csv_file=None
            )

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


# ─── API: SAVE SCAN PEMAKAIAN ───────────────────────────────────
@app.route("/save_pemakaian", methods=["POST"])
@login_required
def save_pemakaian():
    try:
        data    = request.get_json()
        records = data.get("records", [])
        tanggal = data.get("tanggal", "")   # input manual user, format: "2026-05-04T08:30"
        shift   = data.get("shift", "")     # "P" atau "M"

        if not records:
            return jsonify(success=False, error="Tidak ada data")

        if not tanggal:
            return jsonify(success=False, error="Tanggal wajib diisi")

        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")

        # Format tanggal jadi lebih bersih: "2026-05-04 08:30"
        tanggal_clean = tanggal.replace("T", " ")

        from collections import defaultdict
        groups = defaultdict(list)

        for rec in records:
            csv_file = rec.get("csv_file")

            # Fallback: deteksi dari prefix kode
            if not csv_file or csv_file not in CSV_SCAN_PFILES:
                prefix, _, _, _ = get_prefix_from_code(rec.get("code", ""))
                csv_file = PEMAKAIAN_MAP.get(prefix)

            if not csv_file or csv_file not in CSV_SCAN_PFILES:
                return jsonify(
                    success=False,
                    error=f"Kode '{rec.get('code')}' tidak bisa ditentukan CSV tujuannya"
                )

            groups[csv_file].append(rec)

        # Simpan per grup
        for csv_filename, recs in groups.items():
            path = CSV_SCAN_PFILES[csv_filename]
            path.parent.mkdir(parents=True, exist_ok=True)
            file_exists = path.exists()

            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_PSCAN_COLUMNS)
                if not file_exists:
                    writer.writeheader()
                for rec in recs:
                    writer.writerow({
                        "create_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # otomatis saat submit
                        "tanggal":      tanggal_clean,   # input manual user
                        "shift":        shift,
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

def format_tanggal(raw):
    """Normalisasi tanggal ke DD-MM-YYYY"""
    val = (raw or "").split("T")[0].strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%d-%m-%Y")
        except:
            continue
    return val

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
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
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
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
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
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_pa": d.get("operator_pa"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code, "team": d.get("team")
            }
        elif div == "SISA_PACK":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_sp": d.get("operator_sp"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "sisa": float(d.get("sisa") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code, "team": d.get("team")
            }
        elif div == "AVAL_MIXING":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),
                "operator_amix": d.get("operator_amix"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "karung": float(d.get("karung") or 0),
                "berat_kg": float(d.get("berat_kg") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "jenis": d.get("jenis"),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_HD":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),"customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_hd": d.get("operator_hd"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "jenis_hd": d.get("jenis_hd"),
                "kategori_hd": d.get("kategori_hd"),
                "karung": float(d.get("karung") or 0),
                "berat_kg": float(d.get("berat_kg") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_POTONG":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),"customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_cu": d.get("operator_cu"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "jenis_cu": d.get("jenis_cu"),
                "kategori_cu": d.get("kategori_cu"),
                "karung": d.get("karung"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "AVAL_PACKING":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),"customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_pa": d.get("operator_pa"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "jenis_pa": d.get("jenis_pa"),
                "kategori_pa": d.get("kategori_pa"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code, "team": d.get("team")
            }
        elif div == "AVAL_QC":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"),"customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_qc": d.get("operator_qc"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "kategori_qc": d.get("kategori_qc"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        elif div == "MIXING":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_mix": d.get("operator_mix"), "checker": d.get("checker"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "karung": float(d.get("karung") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "code": code
            }
        else:
            return jsonify({"success": False, "message": "Divisi tidak dikenali"})

        save_record(record)

        _div_to_route = {
            "mixing": "barcode_mixing", "hd": "barcode_hd",
            "potong": "barcode_potong", "packing": "barcode_packing",
            "sisa_pack": "barcode_sisa_pack", "aval_mixing": "barcode_aval_mixing",
            "aval_hd": "barcode_aval_hd", "aval_potong": "barcode_aval_potong",
            "aval_packing": "barcode_aval_packing", "aval_qc": "barcode_aval_qc",
        }
        input_page = (d.get("input_page") or "").strip()
        record["_source_route"] = "barcode" if input_page == "barcode" else ""
        cleanup_cache()
        record_cache[order_id] = (record, time.time())  # cache SETELAH _source_route ditambah
        

        cleanup_cache()
        record_cache[order_id] = (record, time.time())

        return jsonify({
            "success": True,
            "order_id": order_id,
            "label_url": f"/label/{order_id}",
            "print_url": f"/label/{order_id}"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


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