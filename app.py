from flask import Flask, render_template, request, jsonify, redirect, send_file, session
import qrcode
from PIL import Image, ImageDraw, ImageFont
import csv, os, sqlite3, json, io, base64, uuid, functools
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import time
import secrets
import threading
import time as _time

_csv_lock = threading.Lock()

def safe_write_csv(csv_path, headers, row_data, max_retry=3):
    with _csv_lock:
        for attempt in range(max_retry):
            try:
                file_exists = os.path.exists(csv_path)
                os.makedirs(os.path.dirname(csv_path), exist_ok=True)
                with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow({k: row_data.get(k, "") for k in headers})
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                return True
            except PermissionError as e:
                print(f"CSV WRITE RETRY {attempt+1}/{max_retry}: {e}")
                _time.sleep(0.2 * (attempt + 1))
            except Exception as e:
                print(f"CSV WRITE ERROR: {e}")
                return False
        print(f"CSV WRITE GAGAL setelah {max_retry} retry: {csv_path}")
        return False
    
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
#SPK_CSV      = r"Z:\Checker\Production\SummarySPK.csv"
USER_EXCEL   = r"Z:\Checker\Production\other\other.xlsx"
USER_SHEET   = "User"

CSV_MIXING      = r"Z:\Checker\Production\Database\katalogmixing.csv"
CSV_HD          = r"Z:\Checker\Production\Database\kataloghd.csv"
CSV_POTONG      = r"Z:\Checker\Production\Database\katalogpotong.csv"
CSV_SISA_POTONG      = r"Z:\Checker\Production\Database\katalogsisapotong.csv"
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
    "SISA_POTONG":      CSV_SISA_POTONG,
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
    "CS": "scanpotong.csv",
    "PA": "scanpacking.csv",
    "PS": "scanpacking.csv",
}

SCAN_TDIR  = Path(r"Z:\Checker\Production\Database\scan_transfer")
CSV_SCAN_TFILES = {
    "scantransferhd.csv":      SCAN_TDIR / "scantransferhd.csv",
    "scantransfermixing.csv":  SCAN_TDIR / "scantransfermixing.csv",
    "scantransferpotong.csv":  SCAN_TDIR / "scantransferpotong.csv",
    "scantransferpacking.csv": SCAN_TDIR / "scantransferpacking.csv",
}

TRANSFER_MAP = {
    "HD": "scantransferhd.csv",
    "MI": "scantransfermixing.csv",
    "CU": "scantransferpotong.csv",
    "PA": "scantransferpacking.csv",
    "PS": "scantransferpacking.csv",
}

# sqlite table untuk scan pemakaian
PEMAKAIAN_TABLE_MAP = {
    "scanhd.csv":      "scanhd",
    "scanmixing.csv":  "scanmixing",
    "scanpotong.csv":  "scanpotong",
    "scanpacking.csv": "scanpacking",
}

# sqlite table untuk scan transfer
TRANSFER_TABLE_MAP = {
    "scantransferhd.csv":      "scantransferhd",
    "scantransfermixing.csv":  "scantransfermixing",
    "scantransferpotong.csv":  "scantransferpotong",
    "scantransferpacking.csv": "scantransferpacking",
}

# sqlite table untuk scan salah
SCAN_SALAH_TABLE_MAP = {
    "scansalahhd.csv":      "scansalahhd",
    "scansalahmixing.csv":  "scansalahmixing",
    "scansalahpotong.csv":  "scansalahpotong",
    "scansalahpacking.csv": "scansalahpacking",
    "scansalahqc.csv":      "scansalahqc",
}

PREFIX_CONFIG = {
    "HD":  ("scansalahhd.csv",      "HD",          "HD"),
    "AHP": ("scansalahhd.csv",      "AVAL_HD",     "HD — Prong"),
    "AHD": ("scansalahhd.csv",      "AVAL_HD",     "HD — Daun"),
    "AHS": ("scansalahhd.csv",      "AVAL_HD",     "HD — Sapuan"),
    "AHT": ("scansalahhd.csv",      "AVAL_HD",     "HD — PENARIK HASIL HD"),
    "MI":  ("scansalahmixing.csv",  "MIXING",      "Mixing"),
    "AMS": ("scansalahmixing.csv",  "AVAL_MIXING", "Aval Mixing"),
    "CU":  ("scansalahpotong.csv",  "POTONG",      "Potong"),
    "CS":  ("scansalahpotong.csv",  "SISA_POTONG",      "Sisa_Potong"),
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

CSV_SCAN_COLUMNS = ["create_at", "divisi", "prefix", "divisi_label", "spk", "customer", "produk", "uk", "checker", "scanned_by", "code", "keterangan"]
CSV_PSCAN_COLUMNS = ["create_at", "tanggal", "shift", "divisi", "prefix", "divisi_label", "spk", "customer", "produk", "uk", "checker", "scanned_by", "code", "mesin", "berat_bersih",]
CSV_TSCAN_COLUMNS = ["create_at", "tanggal", "shift", "divisi", "prefix", "divisi_label", "spk", "customer", "produk", "uk", "checker", "scanned_by", "code", "foreman", "berat_bersih",]

CSV_RETUR_DIR = Path(r"Z:\Checker\Production\Database\scan_retur")
CSV_RETUR_LOG = CSV_RETUR_DIR / "scanretur.csv"
CSV_RETUR_COLUMNS = ["create_at", "tanggal", "shift", "divisi", "prefix",  "divisi_label", "spk", "customer", "produk",
                     "uk", "checker", "scanned_by", "code", "foreman", "berat_bersih", "keterangan"]

import re

def get_prefix_from_code(code: str):
    code = code.strip().upper()
    m = re.match(r'^([A-Z]+)', code)
    if not m:
        return None, None, None, None
    raw = m.group(1)
    for length in [3, 2]:
        p = raw[:length]
        if p in PREFIX_CONFIG:
            csv_file, catalog_key, label = PREFIX_CONFIG[p]
            return p, csv_file, catalog_key, label
    return None, None, None, None

_auto_login_tokens = {}

def cleanup_tokens():
    now = datetime.now()
    expired = [k for k, v in list(_auto_login_tokens.items()) if v["expires"] < now]
    for k in expired:
        del _auto_login_tokens[k]
        
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
    "SISA_POTONG":           {"operator": "operator_cu",  "wadah": "bobin"},
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
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=1,)
    qr.add_data(code)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

#LABEL BARCODE
# ─── LABEL SIZE ─────────────────────────────────────────────
LABEL_W = 302  
LABEL_H = 200   
SCALE   = 4
LABEL_W_HI = LABEL_W * SCALE  
LABEL_H_HI = LABEL_H * SCALE  

def generate_label_image(order_id, data, source_route=None):
    img  = Image.new("RGB", (LABEL_W_HI, LABEL_H_HI), "white")
    draw = ImageDraw.Draw(img)

    font_paths = [r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\tahoma.ttf",]
    
    TIKET_SEMENTARA_ROUTES = {
    "barcode_mixing", "barcode_hd", "barcode_potong", "barcode_packing",
    "barcode_sisa_pack", "barcode_aval_mixing", "barcode_aval_hd",
    "barcode_aval_potong", "barcode_aval_packing", "barcode_aval_qc"}

    show_tiket_sementara = (source_route == "barcode")
    CELTIC_FONT_PATH = r"Z:\Checker\Production\Production\templates\celtic-astrologer\CelticAstrologer.ttf"  # sesuaikan namanya

    try:
        celtic_font = ImageFont.truetype(CELTIC_FONT_PATH, 16 * SCALE)
    except:
        for fp in font_paths:
            try:
                celtic_font = ImageFont.truetype(fp, 16 * SCALE)
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
    KARANTINA_DIVISI = {
        "KARANTINA_MIXING",
        "KARANTINA_HD",
        "KARANTINA_POTONG",
        "KARANTINA_PACKING"
    }
    is_karantina = divisi_raw in KARANTINA_DIVISI
    KARANTINA_DISPLAY_MAP = {
    "KARANTINA_MIXING": "KMI",
    "KARANTINA_HD": "KHD",
    "KARANTINA_POTONG": "KCU",
    "KARANTINA_PACKING": "KPA"
    }
    prefix, _, _, _ = get_prefix_from_code(data.get("code", ""))

    if divisi_raw in KARANTINA_DISPLAY_MAP:
        divisi_display = KARANTINA_DISPLAY_MAP[divisi_raw]
    else:
        divisi_display = prefix if prefix else divisi_raw

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

# NOMOR URUT LABEL PER SPK
    table_map = {
        "HD": "kataloghd",
        "POTONG": "katalogpotong",
        "SISA_POTONG": "katalogsisapotong",
        "PACKING": "katalogpacking",
        "SISA_PACK": "katalogsisapack",
        "MIXING": "katalogmixing",
        "AVAL_HD": "katalogavalhd",
        "AVAL_POTONG": "katalogavalpotong",
        "AVAL_PACKING": "katalogavalpacking",
        "AVAL_MIXING": "katalogavalmixing",
        "AVAL_QC": "katalogavalqc"
    }

    urut_label = ""

    try:
        table_name = table_map.get(divisi_raw)
        if table_name and data.get("code") and spk:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            row = c.execute(f"""
                SELECT COUNT(*)
                FROM {table_name}
                WHERE spk = ?
                AND id <= (
                        SELECT id
                        FROM {table_name}
                        WHERE code = ?
                        LIMIT 1
                )
            """, (spk, data["code"])).fetchone()
            conn.close()
            if row:
                urut_label = f"#{row[0]:03d}"

    except Exception as e:
        print("Nomor urut label:", e)
        urut_label = ""   
    
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

    # Baris 1: Customer  Produk
    draw.text((x, y), f"{customer}    {produk}", fill=0, font=font_md)

    # Baris 2: SPK  UK  Operator  Mesin  Team
    y += gap
    mesin_text = f"M{mesin}" if mesin else ""
    team       = str(data.get("team", "") or "").strip()
    SHOW_TEAM_DIVISI = {"PACKING", "SISA_PACK", "AVAL_PACKING"}
    parts2 = [spk, uk, operator, mesin_text]
    if divisi_raw in SHOW_TEAM_DIVISI and team:
        parts2.append(team)
    parts2 = [p for p in parts2 if str(p).strip()]
    line2 = "    ".join(parts2)
    draw.text((x, y), line2, fill=0, font=font_md)

    # TIKET SEMENTARA
    label_tag = data.get("_label_tag", "")
    if show_tiket_sementara:
        label_tag = "TS"
    if not label_tag and divisi_raw == "SISA_POTONG":
        label_tag = "ROLL SISA"
    if not label_tag and is_karantina:
        label_tag = "KARANTINA"
    if label_tag:
        line2_bbox = draw.textbbox((0, 0), line2, font=font_md)
        line2_w    = line2_bbox[2] - line2_bbox[0]
        draw.text((x + line2_w + 8 * SCALE, y), f"'{label_tag}'", fill=0, font=font_md)

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
        
    # Celtic / Nomor urut label per SPK
    if urut_label:
        urut_font = font_lg
        urut_bbox = draw.textbbox((0, 0), urut_label, font=urut_font)
        urut_w    = urut_bbox[2] - urut_bbox[0]
        urut_x = LABEL_W_HI - urut_w - (4 * SCALE)
        urut_y = y - (2 * SCALE)

        draw.text((urut_x, urut_y), urut_label, fill=0, font=urut_font)
    return img

@app.route("/label/<order_id>")
@login_required
def label(order_id):
    entry = record_cache.get(order_id)
    if not entry:
        return "Label tidak ditemukan atau sudah expired", 404

    record, _ = entry
    source_route = record.get("_source_route", "")
    img = generate_label_image(order_id, record, source_route=source_route)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(600, 600))
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

#LABEL BARCODE
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
from datetime import datetime, timedelta

def generate_code(data):
    now = datetime.now()

    if now.hour < 7:
        produksi_date = now - timedelta(days=1)
    else:
        produksi_date = now
    tanggal = produksi_date.strftime("%d-%m-%Y")
    divisi = str(data.get("divisi", "")).strip().upper()

    # Default mapping
    div_map = {
        "MIXING": "MI",
        "HD": "HD",
        "POTONG": "CU",
        "SISA_POTONG": "CS",
        "PACKING": "PA",
        "SISA_PACK": "PS",
        "AVAL_MIXING": "AMS",
        "AVAL_QC": "AQC",
        "KARANTINA_MIXING": "KMI",
        "KARANTINA_HD": "KHD",
        "KARANTINA_POTONG": "KCU",
        "KARANTINA_PACKING": "KPA",
    }

    div = div_map.get(divisi, "XX")

    if divisi == "AVAL_HD":
        jenis_map = {
            "Prong": "AHP",
            "Daun": "AHD",
            "Sapuan": "AHS",
            "PENARIK HASIL HD": "AHT",
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

    spk = str(data.get("spk", "")).strip()
    shift = str(data.get("shift", "")).strip()

    try:
        berat = "{:.2f}".format(float(data.get("berat_bersih") or 0))
    except:
        berat = "0.00"

    waktu = now.strftime("%H%M%S")
    return f"{div}{tanggal}{spk}{shift}{berat}{waktu}"

# ─── SPK LOOKUP ─────────────────────────────────────────────
def load_spk_data():
    df = pd.read_csv(SPK_CSV, encoding="utf-8-sig", on_bad_lines='skip', engine='python')
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
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_mix TEXT, checker TEXT, berat_kg REAL,
        berat_bersih REAL, karung REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS kataloghd (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, keranjang REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogsisapotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, created_at TEXT, code TEXT, team TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogsisapack (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_sp TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, sisa REAL, created_at TEXT, code TEXT, team TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, operator_amix TEXT, checker TEXT, mesin REAL, berat_kg REAL, berat_bersih REAL, jenis REAL,
        created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalHD (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
        mesin REAL, jenis_hd TEXT, kategori_hd TEXT, berat_kg REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
        mesin REAL, jenis_cu TEXT, kategori_cu TEXT, berat_kg REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
        mesin REAL, jenis_pa TEXT, kategori_pa TEXT, berat_bersih REAL, created_at TEXT, code TEXT, team TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalqc (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_qc TEXT, checker TEXT,
        mesin REAL, kategori_qc TEXT, berat_bersih REAL, created_at TEXT, code TEXT
    )""")
  
    c.execute("""
    CREATE TABLE IF NOT EXISTS SummarySPK (
        spk TEXT, so TEXT, tanggal TEXT, customer TEXT, product TEXT, warna TEXT, aval TEXT, uk TEXT, lembar TEXT, pack TEXT,
        kg TEXT, berat_lembar TEXT, berat_pack TEXT, tebal TEXT, order_ball TEXT, qty TEXT, checker TEXT, satuan TEXT, blongsong TEXT, etiket TEXT, mixing TEXT
    )""")
    
    # Scan Pemakaian per divisi
    c.execute("""
    CREATE TABLE IF NOT EXISTS scanmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scanhd (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scanpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scanpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
    )""")

    # Scan Transfer per divisi
    c.execute("""
    CREATE TABLE IF NOT EXISTS scantransfermixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scantransferhd (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scantransferpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scantransferpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
    )""")

    # Scan Salah per divisi
    c.execute("""
    CREATE TABLE IF NOT EXISTS scansalahmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scansalahhd (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scansalahpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scansalahpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scansalahqc (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS scan_retur (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT,
        berat_bersih TEXT, keterangan TEXT
    )""")
    
    #tabel gabungan
    # Tabel gabungan scan salah
    c.execute("""
    CREATE TABLE IF NOT EXISTS scan_salah (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, divisi TEXT, prefix TEXT, divisi_label TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, keterangan TEXT
    )""")

    # Tabel gabungan scan pemakaian
    c.execute("""
    CREATE TABLE IF NOT EXISTS scan_pemakaian (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, mesin TEXT, berat_bersih TEXT
    )""")

    # Tabel gabungan scan transfer
    c.execute("""
    CREATE TABLE IF NOT EXISTS scan_transfer (
        id INTEGER PRIMARY KEY AUTOINCREMENT, create_at TEXT, tanggal TEXT, shift TEXT, divisi TEXT, prefix TEXT,
        divisi_label TEXT, spk TEXT, customer TEXT, produk TEXT, uk TEXT, checker TEXT, scanned_by TEXT, code TEXT, foreman TEXT, berat_bersih TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS mutasimixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT,
        code_scan TEXT, code_baru TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        berat_awal REAL, berat_bersih REAL,
        operator TEXT, checker TEXT, keterangan TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS mutasihd (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT,
        code_scan TEXT, code_baru TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        berat_awal REAL, berat_bersih REAL,
        operator TEXT, checker TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS mutasipotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT,
        code_scan TEXT, code_baru TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        berat_awal REAL, berat_bersih REAL,
        operator TEXT, checker TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS mutasipacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT,
        code_scan TEXT, code_baru TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        berat_awal REAL, berat_bersih REAL,
        operator TEXT, checker TEXT, keterangan TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS mutasisisapack (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_at TEXT, tanggal TEXT, shift TEXT,
        code_scan TEXT, code_baru TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT,
        berat_awal REAL, berat_bersih REAL,
        operator TEXT, checker TEXT, keterangan TEXT
    )""")
    
    #karantina
    c.execute("""
    CREATE TABLE IF NOT EXISTS karantinamixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_mix TEXT, checker TEXT, berat_kg REAL,
        berat_bersih REAL, karung REAL, created_at TEXT, code TEXT
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS karantinahd (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_hd TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, bobin REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS karantinapotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_cu TEXT, checker TEXT,
        mesin REAL, berat_kg REAL, keranjang REAL, berat_bersih REAL, created_at TEXT, code TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS karantinapacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, tanggal TEXT, shift TEXT, divisi TEXT,
        spk TEXT, customer TEXT, produk TEXT, uk TEXT, operator_pa TEXT, checker TEXT,
        mesin REAL, berat_bersih REAL, created_at TEXT, code TEXT, team TEXT
    )""")

    conn.commit()
    conn.close()

# ─── CSV INIT ───────────────────────────────────────────────
CSV_HEADERS = ["tanggal","shift","divisi","spk","customer","produk","uk","operator_mix","checker","berat_bersih","karung","created_at","code"]

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
            operator_hd, checker, mesin, berat_kg, bobin, berat_bersih, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_hd, :checker, :mesin, :berat_kg, :bobin, :berat_bersih, :created_at, :code
        )""", data)
        csv_path = CSV_HD
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_hd","checker","mesin","berat_kg","bobin","berat_bersih","created_at","code"]

    elif div == "POTONG":
        c.execute("""
        INSERT INTO katalogpotong (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_cu, checker, mesin, berat_kg, keranjang, berat_bersih, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_cu, :checker, :mesin, :berat_kg, :keranjang, :berat_bersih, :created_at, :code
        )""", data)
        csv_path = CSV_POTONG
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_cu","checker","mesin","berat_kg","keranjang","berat_bersih","created_at","code"]

    elif div == "SISA_POTONG":
        c.execute("""
        INSERT INTO katalogsisapotong (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_cu, checker, mesin, berat_kg, bobin, berat_bersih, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_cu, :checker, :mesin, :berat_kg, :bobin, :berat_bersih, :created_at, :code
        )""", data)
        csv_path = CSV_SISA_POTONG
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_cu","checker","mesin","berat_kg","bobin","berat_bersih","created_at","code"]
        
    elif div == "PACKING":
        c.execute("""
        INSERT INTO katalogpacking (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_pa, checker, mesin, berat_bersih, created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_pa, :checker, :mesin, :berat_bersih, :created_at, :code, :team
        )""", data)
        csv_path = CSV_PACKING
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_pa","checker","mesin","berat_bersih","created_at","code","team"]

    elif div == "SISA_PACK":
        c.execute("""
        INSERT INTO katalogsisapack (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_sp, checker, mesin, berat_bersih, sisa, created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_sp, :checker, :mesin, :berat_bersih, :sisa, :created_at, :code, :team
        )""", data)
        csv_path = CSV_SISA_PACK
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_sp","checker","mesin","berat_bersih","sisa","created_at","code","team"]

    elif div == "AVAL_MIXING":
        c.execute("""
        INSERT INTO katalogavalmixing (
            tanggal, shift, divisi, spk,
            operator_amix, checker, mesin, karung, berat_kg, berat_bersih, jenis, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk,
            :operator_amix, :checker, :mesin, :karung, :berat_kg, :berat_bersih, :jenis, :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_MIXING
        headers  = ["tanggal","shift","divisi","spk", "operator_amix","checker","mesin","karung","berat_kg","berat_bersih","jenis","created_at","code"]

    elif div == "AVAL_HD":
        c.execute("""
        INSERT INTO katalogavalhd (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_hd, checker, mesin, jenis_hd, kategori_hd, karung, berat_kg, berat_bersih,  created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_hd, :checker, :mesin, :jenis_hd, :kategori_hd, :karung, :berat_kg, :berat_bersih, :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_HD
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_hd","checker","mesin","jenis_hd","kategori_hd","karung","berat_kg","berat_bersih","created_at","code"]

    elif div == "AVAL_POTONG":
        c.execute("""
        INSERT INTO katalogavalpotong (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_cu, checker, mesin, jenis_cu, kategori_cu, karung, berat_kg, berat_bersih,  created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_cu, :checker, :mesin, :jenis_cu, :kategori_cu, :karung, :berat_kg, :berat_bersih, :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_POTONG
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_cu","checker","mesin","jenis_cu","kategori_cu","karung","berat_kg","berat_bersih","created_at","code"]
  
    elif div == "AVAL_PACKING":
        c.execute("""
        INSERT INTO katalogavalpacking (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_pa, checker, mesin, jenis_pa, kategori_pa, berat_bersih, created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_pa, :checker, :mesin, :jenis_pa, :kategori_pa, :berat_bersih, :created_at, :code, :team
        )""", data)
        csv_path = CSV_AVAL_PACKING
        headers  = ["tanggal","shift","divisi","spk", "customer","produk","uk", "operator_pa","checker","mesin","jenis_pa","kategori_pa","berat_bersih","created_at","code","team"]

    elif div == "AVAL_QC":
        c.execute("""
        INSERT INTO katalogavalqc (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_qc, checker, mesin, kategori_qc, berat_bersih, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_qc, :checker, :mesin, :kategori_qc, :berat_bersih, :created_at, :code
        )""", data)
        csv_path = CSV_AVAL_QC
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_qc","checker","mesin","kategori_qc","berat_bersih","created_at","code"]

    elif div == "MIXING":
        c.execute("""
        INSERT INTO katalogmixing (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_mix, checker, berat_kg, berat_bersih, karung, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_mix, :checker, :berat_kg, :berat_bersih, :karung, :created_at, :code
        )""", data)
        csv_path = CSV_MIXING
        headers  = ["tanggal","shift","divisi","spk","customer","produk","uk", "operator_mix","checker","berat_kg","berat_bersih","karung","created_at","code"]
        
    elif div == "SUMMARY_SPK":
        c.execute("""
        INSERT INTO SummarySPK (
            spk, so, tanggal, customer, product, warna, aval, uk, lembar, pack, kg, berat_lembar,
            berat_pack, tebal, order_ball, qty, checker, satuan, blongsong, etiket, mixing
        ) VALUES (
            :spk, :so, :tanggal, :customer, :product, :warna, :aval, :uk, :lembar, :pack, :kg, :berat_lembar,
            :berat_pack, :tebal, :order_ball, :qty, :checker, :satuan, :blongsong, :etiket, :mixing
        )""", data)
        csv_path = SPK_CSV
        headers  = ["spk", "so", "tanggal", "customer", "product", "warna", "aval", "uk", "lembar", "pack", "kg",
                    "berat_lembar", "berat_pack", "tebal", "order_ball", "qty", "checker", "satuan", "blongsong", "etiket", "mixing"]
    
    elif div == "KARANTINA_MIXING":
        c.execute("""
        INSERT INTO karantinamixing (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_mix, checker, berat_kg, berat_bersih, karung, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_mix, :checker, :berat_kg, :berat_bersih, :karung, :created_at, :code
        )""", data)
        
    elif div == "KARANTINA_HD":
        c.execute("""
        INSERT INTO karantinahd (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_hd, checker, mesin, berat_kg, bobin, berat_bersih, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_hd, :checker, :mesin, :berat_kg, :bobin, :berat_bersih, :created_at, :code
        )""", data)

    elif div == "KARANTINA_POTONG":
        c.execute("""
        INSERT INTO karantinapotong (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_cu, checker, mesin, berat_kg, keranjang, berat_bersih, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_cu, :checker, :mesin, :berat_kg, :keranjang, :berat_bersih, :created_at, :code
        )""", data)

    elif div == "KARANTINA_PACKING":
        c.execute("""
        INSERT INTO karantinapacking (
            tanggal, shift, divisi, spk, customer, produk, uk,
            operator_pa, checker, mesin, berat_bersih, created_at, code, team
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_pa, :checker, :mesin, :berat_bersih, :created_at, :code, :team
        )""", data)

    else:
        conn.close()
        raise ValueError(f"Divisi tidak dikenali: {div}")

    conn.commit()
    conn.close()
        
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
        match = users[(users["username"] == username) & (users["password"] == password)]
        if not match.empty:
            session.permanent      = True
            session["logged_in"]   = True
            session["username"]    = username
            session["name"]        = str(match.iloc[0].get("name", username))
            session["role"]        = str(match.iloc[0].get("role", "user"))
            session["last_active"] = datetime.now().isoformat()
            role = session["role"]

            # ── Staff: generate token, redirect ke port 5001 ──
            if role == "staff":
                cleanup_tokens()
                token = secrets.token_urlsafe(32)
                _auto_login_tokens[token] = {
                    "username": username,
                    "name":     session["name"],
                    "role":     role,
                    "expires":  datetime.now() + timedelta(seconds=30),
                }
                redirect_url = f"http://192.168.88.24:5001/auto_login?token={token}"
                return jsonify(success=True, redirect=redirect_url)

            redirect_map = {
                "administrator": "/mixing",
                "checker":       "/mixing",
                "adminwip":      "/scan_pemakaian",
            }
            redirect_url = redirect_map.get(role, "/login")
            return jsonify(success=True, redirect=redirect_url)
        else:
            return jsonify(success=False, message="Username atau password salah.")
    except FileNotFoundError:
        return jsonify(success=False, message="File data user tidak ditemukan.")
    except Exception as e:
        return jsonify(success=False, message=f"Error: {str(e)}")
    
@app.route("/auto_login_token/<token>")
def auto_login_token(token):
    cleanup_tokens()
    entry = _auto_login_tokens.get(token)
    if not entry:
        return jsonify(valid=False, error="Token tidak valid atau sudah expired")
    if entry["expires"] < datetime.now():
        del _auto_login_tokens[token]
        return jsonify(valid=False, error="Token expired")
    # Hapus token setelah dipakai (one-time use)
    del _auto_login_tokens[token]
    return jsonify(valid    = True, username = entry["username"], name     = entry["name"], role     = entry["role"],)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

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

@app.route("/sisa_potong")
@login_required
@checker_required
def sisa_potong():
    return render_template("sisa_potong.html", active_page="sisa_potong", current_user=session.get("name"))

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

@app.route("/stok_checker")
@login_required
@checker_required
def stok_checker():
    return render_template("stok_checker.html", active_page="stok_checker", current_user=session.get("name"))

# ADMIN WIP
@app.route("/summary_spk")
@adminwip_required
def summary_spk():
    return render_template("summary_spk.html", active_page="summary_spk", current_user=session.get("name"))

@app.route("/scan_salah")
@adminwip_required
def scan_salah():
    return render_template("scan_salah.html", active_page="scan_salah", current_user=session.get("name"))

@app.route("/scan_pemakaian")
@adminwip_required
def scan_pemakaian():
    return render_template("scan_pemakaian.html", active_page="scan_pemakaian", current_user=session.get("name"))

@app.route("/scan_transfer")
@checker_required
def scan_transfer():
    return render_template("scan_transfer.html", active_page="scan_transfer", current_user=session.get("name"))

@app.route("/scan_retur")
@checker_required
def scan_retur():
    return render_template("scan_retur.html", active_page="scan_retur", current_user=session.get("name"))

@app.route("/karantina_mixing")
@checker_required
def karantina_mixing():
    return render_template("karantina_mixing.html", active_page="karantina_mixing", current_user=session.get("name"))

@app.route("/karantina_hd")
@checker_required
def karantina_hd():
    return render_template("karantina_hd.html", active_page="karantina_hd", current_user=session.get("name"))

@app.route("/karantina_potong")
@checker_required
def karantina_potong():
    return render_template("karantina_potong.html", active_page="karantina_potong", current_user=session.get("name"))

@app.route("/karantina_packing")
@checker_required
def karantina_packing():
    return render_template("karantina_packing.html", active_page="karantina_packing", current_user=session.get("name"))

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

@app.route("/barcode_sisa_potong")
@adminwip_required
def barcode_sisa_potong():
    return render_template("barcode_sisa_potong.html", active_page="barcode_sisa_potong", current_user=session.get("name"))

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

@app.route("/mutasi_mixing")
@adminwip_required
def mutasi_mixing():
    return render_template("mutasi_mixing.html", active_page="mutasi_mixing", current_user=session.get("name"))

@app.route("/mutasi_hd")
@adminwip_required
def mutasi_hd():
    return render_template("mutasi_hd.html", active_page="mutasi_hd", current_user=session.get("name"))

@app.route("/mutasi_potong")
@adminwip_required
def mutasi_potong():
    return render_template("mutasi_potong.html", active_page="mutasi_potong", current_user=session.get("name"))

@app.route("/mutasi_packing")
@adminwip_required
def mutasi_packing():
    return render_template("mutasi_packing.html", active_page="mutasi_packing", current_user=session.get("name"))

@app.route("/mutasi_sisapack")
@adminwip_required
def mutasi_sisapack():
    return render_template("mutasi_sisapack.html", active_page="mutasi_sisapack", current_user=session.get("name"))

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

CSV_MUTASI_MIXING = r"Z:\Checker\Production\Database\mutasi\katalogmutasimixing.csv"
CSV_MUTASI_MIXING_COLUMNS = ["create_at", "tanggal", "shift", "code_scan", "code_baru", "spk", "customer", "produk", "uk", "berat_awal", "berat_bersih", "operator", "checker", "keterangan"]

@app.route("/api/mutasi_mixing", methods=["POST"])
@login_required
def api_mutasi_mixing():
    try:
        data = request.get_json()
        code_awal     = (data.get("code_awal") or "").strip().upper()
        tanggal_raw   = (data.get("tanggal") or "").strip()
        shift         = (data.get("shift") or "").strip().upper()
        spk_baru      = (data.get("spk_baru") or "").strip()
        hasil_timbang = float(data.get("hasil_timbang") or 0)
        operator      = (data.get("operator") or "").strip()
        admin         = session.get("name", "")
        keterangan    = (data.get("keterangan") or "").strip()

        # VALIDASI
        if not code_awal:
            return jsonify(success=False, error="Kode awal wajib diisi")
        if not tanggal_raw:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not spk_baru:
            return jsonify(success=False, error="SPK baru wajib diisi")
        if not operator:
            return jsonify(success=False, error="Operator wajib dipilih")

        tanggal = format_tanggal(tanggal_raw)

        # LOOKUP DATA KATALOG MIXING
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM katalogmixing
            WHERE UPPER(TRIM(code)) = ?
            ORDER BY id DESC
            LIMIT 1
        """, (code_awal,)).fetchone()

        conn.close()

        if not row:
            return jsonify(success=False, error="Kode awal tidak ditemukan")

        r = dict(row)

        # DATA TIKET AWAL
        spk_awal = str(r.get("spk", "")).strip()
        customer = str(r.get("customer", "")).strip()
        produk = str(r.get("produk", "")).strip()
        uk = str(r.get("uk", "")).strip()

        try:
            berat_awal = float(
                r.get("berat_bersih")
                or r.get("berat_kg")
                or 0
            )
        except:
            berat_awal = 0

        # VALIDASI BERAT
        if hasil_timbang > berat_awal:
            return jsonify(success=False, error="Hasil timbang melebihi berat awal")

        terpakai = round(berat_awal - hasil_timbang, 2)

        # LOOKUP SPK BARU
        customer_baru = customer
        produk_baru   = produk
        uk_baru       = uk

        try:
            if os.path.exists(SPK_CSV):
                df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python")
                df_spk.columns = (df_spk.columns.str.strip())
                spk_col2 = next((
                        c for c
                        in df_spk.columns
                        if "spk"
                        in c.lower()
                    ), df_spk.columns[1])

                df_spk[spk_col2] = (df_spk[spk_col2].astype(str).str.strip())
                match_spk = df_spk[df_spk[spk_col2] == spk_baru]

                if not match_spk.empty:
                    rr = match_spk.iloc[0]
                    customer_baru = str(rr.iloc[3]).strip()
                    produk_baru = str(rr.iloc[4]).strip()
                    uk_baru = str(rr.iloc[7]).strip()

        except Exception as e:
            print("Lookup SPK baru gagal:", e)

        # DATETIME
        now = datetime.now()
        created_at = now.strftime("%d-%m-%Y %H:%M:%S")
        tanggal_code = now.strftime("%d-%m-%Y")
        timestamp = now.strftime("%H%M%S")

        def generate_code(spk, shift, berat):
            berat_str = (f"{float(berat):05.2f}")
            return (
                f"MI"
                f"{tanggal_code}"
                f"{spk}"
                f"{shift}"
                f"{berat_str}"
                f"{timestamp}"
            )

        code_sisa = generate_code(spk_awal, shift, hasil_timbang)
        code_mutasi = generate_code(spk_baru, shift, terpakai)

        # ── SIAPKAN ROW LOG MUTASI (untuk CSV & SQLite) ──
        row_sisa_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_sisa,
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "berat_awal": berat_awal,
            "berat_bersih": f"{terpakai:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }
        row_mutasi_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_mutasi,
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "berat_awal": berat_awal,
            "berat_bersih": f"{hasil_timbang:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }

        # SIMPAN CSV MUTASI

        # DATA BARU UNTUK KATALOG MIXING
        data_sisa = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "MIXING",
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "operator_mix": operator,
            "checker": admin,
            "berat_kg": round(hasil_timbang, 2),
            "berat_bersih": round(hasil_timbang, 2),
            "karung": 0.09,
            "created_at": created_at,
            "code": code_sisa
        }
        data_mutasi = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "MIXING",
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "operator_mix": operator,
            "checker": admin,
            "berat_kg": round(terpakai, 2),
            "berat_bersih": round(terpakai, 2),
            "karung": 0.09,
            "created_at": created_at,
            "code": code_mutasi
        }

        # SIMPAN KE CSV MIXING

        # ── SIMPAN SQLITE ──
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        sql_katalog = """
        INSERT INTO katalogmixing (
            tanggal, shift, divisi, spk, customer, produk, uk, operator_mix, checker, berat_kg, berat_bersih, karung, created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi, :spk, :customer, :produk, :uk,
            :operator_mix, :checker, :berat_kg, :berat_bersih, :karung, :created_at, :code
        )
        """
        c.execute(sql_katalog, data_sisa)
        c.execute(sql_katalog, data_mutasi)

        # log mutasi ke tabel mutasimixing
        sql_log = """
        INSERT INTO mutasimixing (
            create_at, tanggal, shift, code_scan, code_baru,
            spk, customer, produk, uk, berat_awal, berat_bersih,
            operator, checker, keterangan
        ) VALUES (
            :create_at, :tanggal, :shift, :code_scan, :code_baru,
            :spk, :customer, :produk, :uk, :berat_awal, :berat_bersih,
            :operator, :checker, :keterangan
        )
        """
        c.execute(sql_log, row_sisa_log)
        c.execute(sql_log, row_mutasi_log)

        conn.commit()
        conn.close()

        # CACHE UNTUK LABEL
        for rec_data, rec_code in [(data_sisa, code_sisa), (data_mutasi, code_mutasi)]:
            cache_rec = {
                "order_id":    rec_code,
                "tanggal":     tanggal,
                "shift":       shift,
                "divisi":      "MIXING",
                "spk":         rec_data["spk"],
                "customer":    rec_data["customer"],
                "produk":      rec_data["produk"],
                "uk":          rec_data["uk"],
                "operator_mix": operator,
                "checker":     admin,
                "berat_kg":    rec_data["berat_kg"],
                "berat_bersih": rec_data["berat_bersih"],
                "karung":      0.09,
                "created_at":  created_at,
                "code":        rec_code,
                "_label_tag":  "MUTASI",
                "_source_route": "",
            }
            cleanup_cache()
            record_cache[rec_code] = (cache_rec, time.time())

        return jsonify(success=True, saved=2, code_sisa=code_sisa, code_mutasi=code_mutasi,
            print_urls=[
                f"/label/print/{code_sisa}",
                f"/label/print/{code_mutasi}"
            ]
        )
    except Exception as e:
        import traceback
        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
        
CSV_MUTASI_HD = r"Z:\Checker\Production\Database\mutasi\katalogmutasihd.csv"
CSV_MUTASI_HD_COLUMNS = ["create_at", "tanggal", "shift", "code_scan", "code_baru", "spk", "customer", "produk", "uk", "berat_awal", "berat_bersih", "operator", "checker", "keterangan"]

@app.route("/api/mutasi_hd", methods=["POST"])
@login_required
def api_mutasi_hd():
    try:
        data = request.get_json()
        code_awal     = (data.get("code_awal") or "").strip().upper()
        tanggal_raw   = (data.get("tanggal") or "").strip()
        shift         = (data.get("shift") or "").strip().upper()
        spk_baru      = (data.get("spk_baru") or "").strip()
        hasil_timbang = float(data.get("hasil_timbang") or 0)
        operator      = (data.get("operator") or "").strip()
        admin         = session.get("name", "")
        keterangan    = (data.get("keterangan") or "").strip()

        # VALIDASI
        if not code_awal:
            return jsonify(success=False, error="Kode awal wajib diisi")
        if not tanggal_raw:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not spk_baru:
            return jsonify(success=False, error="SPK baru wajib diisi")
        if not operator:
            return jsonify(success=False, error="Operator wajib dipilih")

        tanggal = format_tanggal(tanggal_raw)

        # LOOKUP DATA KATALOG
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM kataloghd
            WHERE UPPER(TRIM(code)) = ?
            ORDER BY id DESC
            LIMIT 1
        """, (code_awal,)).fetchone()

        conn.close()

        if not row:
            return jsonify(success=False, error="Kode awal tidak ditemukan")

        r = dict(row)

        spk_awal = str(r.get("spk", "")).strip()
        customer = str(r.get("customer", "")).strip()
        produk = str(r.get("produk", "")).strip()
        uk = str(r.get("uk", "")).strip()
        mesin = str(r.get("mesin", "")).strip()

        try:
            berat_awal = float(
                r.get("berat_bersih")
                or r.get("berat_kg")
                or 0
            )
        except:
            berat_awal = 0

        # VALIDASI BERAT
        if hasil_timbang > berat_awal:
            return jsonify(success=False, error="Hasil timbang melebihi berat awal")

        terpakai = round(berat_awal - hasil_timbang, 2)

        # LOOKUP SPK BARU
        customer_baru = customer
        produk_baru   = produk
        uk_baru       = uk

        try:
            if os.path.exists(SPK_CSV):

                df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python" )
                df_spk.columns = (df_spk.columns.str.strip())

                spk_col = next(
                    (
                        c for c in df_spk.columns
                        if "spk" in c.lower()
                    ), df_spk.columns[1])
                df_spk[spk_col] = (df_spk[spk_col].astype(str).str.strip())
                match_spk = df_spk[df_spk[spk_col]  == spk_baru]

                if not match_spk.empty:
                    rr = match_spk.iloc[0]
                    customer_baru = str(rr.iloc[3]).strip()
                    produk_baru = str(rr.iloc[4]).strip()
                    uk_baru = str(rr.iloc[7]).strip()

        except Exception as e:
            print("Lookup SPK baru gagal:",e)

        # DATETIME
        now = datetime.now()
        created_at = now.strftime("%d-%m-%Y %H:%M:%S")
        tanggal_code = now.strftime("%d-%m-%Y")
        timestamp = now.strftime("%H%M%S")

        def generate_code(spk, shift, berat):
            berat_str = (f"{float(berat):05.2f}")
            return (
                f"HD"
                f"{tanggal_code}"
                f"{spk}"
                f"{shift}"
                f"{berat_str}"
                f"{timestamp}"
            )

        code_sisa = generate_code(spk_awal, shift, hasil_timbang)
        code_mutasi = generate_code(spk_baru, shift, terpakai)

        # ── SIAPKAN ROW LOG MUTASI ──
        row_sisa_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_sisa,
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "berat_awal": berat_awal,
            "berat_bersih": f"{terpakai:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }
        row_mutasi_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_mutasi,
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "berat_awal": berat_awal,
            "berat_bersih": f"{hasil_timbang:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }

        # SIMPAN CSV MUTASI HD

        # DATA BARU UNTUK KATALOG
        data_sisa = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "HD",
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "operator_hd": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_kg": round(hasil_timbang,2),
            "berat_bersih": round(hasil_timbang,2),
            "bobin": 0.09,
            "created_at": created_at,
            "code": code_sisa
        }
        data_mutasi = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "HD",
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "operator_hd": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_kg": round(terpakai,2),
            "berat_bersih": round(terpakai,2),
            "bobin": 0.09,
            "created_at": created_at,
            "code": code_mutasi
        }

        # SIMPAN KE CSV_HD

        # SQLITE
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = """
        INSERT INTO kataloghd (
            tanggal, shift, divisi, spk, customer, produk, uk, operator_hd, checker, mesin, berat_kg, berat_bersih, bobin, created_at, code
        ) VALUES (
            :tanggal,
            :shift,
            :divisi,
            :spk,
            :customer,
            :produk,
            :uk,
            :operator_hd,
            :checker,
            :mesin,
            :berat_kg,
            :berat_bersih,
            :bobin,
            :created_at,
            :code
        )
        """
        c.execute(sql,data_sisa)
        c.execute(sql,data_mutasi)

        # log mutasi ke tabel mutasihd
        sql_log = """
        INSERT INTO mutasihd (
            create_at, tanggal, shift, code_scan, code_baru,
            spk, customer, produk, uk, berat_awal, berat_bersih,
            operator, checker, keterangan
        ) VALUES (
            :create_at, :tanggal, :shift, :code_scan, :code_baru,
            :spk, :customer, :produk, :uk, :berat_awal, :berat_bersih,
            :operator, :checker, :keterangan
        )
        """
        c.execute(sql_log, row_sisa_log)
        c.execute(sql_log, row_mutasi_log)

        conn.commit()
        conn.close()
        
        # Simpan ke record_cache agar /label/print/<code>
        for rec_data, rec_code in [(data_sisa, code_sisa), (data_mutasi, code_mutasi)]:
            cache_rec = {
                "order_id": rec_code,
                "tanggal": tanggal,
                "shift": shift,
                "divisi": "HD",
                "spk": rec_data["spk"],
                "customer": rec_data["customer"],
                "produk": rec_data["produk"],
                "uk": rec_data["uk"],
                "operator_hd": operator,
                "bobin": 0.09,
                "operator_mix": operator,
                "karung": 0.09,
                "checker": admin,
                "mesin": mesin,
                "berat_kg": rec_data["berat_kg"],
                "berat_bersih": rec_data["berat_bersih"],
                "created_at": created_at,
                "code": rec_code,
                "_label_tag": "MUTASI",
                "_source_route": "",
            }
            cleanup_cache()
            record_cache[rec_code] = (cache_rec, time.time())
        return jsonify(success=True, saved=2, code_sisa=code_sisa, code_mutasi=code_mutasi,
    print_urls=[
        f"/label/print/{code_sisa}",
        f"/label/print/{code_mutasi}"
    ]
)
    except Exception as e:
        import traceback
        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
    
CSV_MUTASI_POTONG = r"Z:\Checker\Production\Database\mutasi\katalogmutasipotong.csv"
CSV_MUTASI_POTONG_COLUMNS = ["create_at", "tanggal", "shift", "code_scan", "code_baru", "spk", "customer", "produk", "uk", "berat_awal", "berat_bersih", "operator", "checker", "keterangan"]

@app.route("/api/mutasi_potong", methods=["POST"])
@login_required
def api_mutasi_potong():
    try:
        data = request.get_json()
        code_awal     = (data.get("code_awal") or "").strip().upper()
        tanggal_raw   = (data.get("tanggal") or "").strip()
        shift         = (data.get("shift") or "").strip().upper()
        spk_baru      = (data.get("spk_baru") or "").strip()
        hasil_timbang = float(data.get("hasil_timbang") or 0)
        operator      = (data.get("operator") or "").strip()
        admin         = session.get("name", "")
        keterangan    = (data.get("keterangan") or "").strip()

        # VALIDASI
        if not code_awal:
            return jsonify(success=False, error="Kode awal wajib diisi")
        if not tanggal_raw:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not spk_baru:
            return jsonify(success=False, error="SPK baru wajib diisi")
        if not operator:
            return jsonify(success=False, error="Operator wajib dipilih")

        tanggal = format_tanggal(tanggal_raw)

        # LOOKUP DATA KATALOG
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM katalogpotong
            WHERE UPPER(TRIM(code)) = ?
            ORDER BY id DESC
            LIMIT 1
        """, (code_awal,)).fetchone()

        conn.close()

        if not row:
            return jsonify(success=False, error="Kode awal tidak ditemukan")

        r = dict(row)

        spk_awal = str(r.get("spk", "")).strip()
        customer = str(r.get("customer", "")).strip()
        produk = str(r.get("produk", "")).strip()
        uk = str(r.get("uk", "")).strip()
        mesin = str(r.get("mesin", "")).strip()

        try:
            berat_awal = float(
                r.get("berat_bersih")
                or r.get("berat_kg")
                or 0
            )
        except:
            berat_awal = 0

        # VALIDASI BERAT
        if hasil_timbang > berat_awal:
            return jsonify(success=False, error="Hasil timbang melebihi berat awal")

        terpakai = round(berat_awal - hasil_timbang, 2)

        # LOOKUP SPK BARU
        customer_baru = customer
        produk_baru   = produk
        uk_baru       = uk

        try:
            if os.path.exists(SPK_CSV):

                df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python" )
                df_spk.columns = (df_spk.columns.str.strip())
                spk_col = next(
                    (
                        c for c in df_spk.columns
                        if "spk" in c.lower()
                    ),
                    df_spk.columns[1]
                )

                df_spk[spk_col] = (df_spk[spk_col].astype(str).str.strip())
                match_spk = df_spk[df_spk[spk_col] == spk_baru]

                if not match_spk.empty:
                    rr = match_spk.iloc[0]
                    customer_baru = str(rr.iloc[3]).strip()
                    produk_baru = str(rr.iloc[4]).strip()
                    uk_baru = str(rr.iloc[7]).strip()

        except Exception as e:
            print("Lookup SPK baru gagal:",e)

        # DATETIME
        now = datetime.now()
        created_at = now.strftime("%d-%m-%Y %H:%M:%S")
        tanggal_code = now.strftime("%d-%m-%Y")
        timestamp = now.strftime("%H%M%S")

        def generate_code(spk, shift, berat):
            berat_str = (f"{float(berat):05.2f}")
            return (
                f"CU"
                f"{tanggal_code}"
                f"{spk}"
                f"{shift}"
                f"{berat_str}"
                f"{timestamp}"
            )

        code_sisa = generate_code(spk_awal, shift, hasil_timbang)
        code_mutasi = generate_code(spk_baru, shift, terpakai)

        # ── SIAPKAN ROW LOG MUTASI ──
        row_sisa_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_sisa,
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "berat_awal": berat_awal,
            "berat_bersih": f"{terpakai:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }
        row_mutasi_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_mutasi,
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "berat_awal": berat_awal,
            "berat_bersih": f"{hasil_timbang:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }

        # SIMPAN CSV MUTASI POTONG

        # DATA BARU UNTUK KATALOG
        data_sisa = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "POTONG",
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "operator_cu": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_kg": round(hasil_timbang,2),
            "berat_bersih": round(hasil_timbang,2),
            "keranjang": 1,
            "created_at": created_at,
            "code": code_sisa
        }
        data_mutasi = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "POTONG",
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "operator_cu": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_kg": round(terpakai,2),
            "berat_bersih": round(terpakai,2),
            "keranjang": 1,
            "created_at": created_at,
            "code": code_mutasi
        }

        # SIMPAN KE CSV_POTONG

        # SQLITE
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = """
        INSERT INTO katalogpotong (
            tanggal, shift, divisi, spk, customer, produk, uk, operator_cu, checker, mesin, berat_kg, berat_bersih, keranjang, created_at, code
        ) VALUES (
            :tanggal,
            :shift,
            :divisi,
            :spk,
            :customer,
            :produk,
            :uk,
            :operator_cu,
            :checker,
            :mesin,
            :berat_kg,
            :berat_bersih,
            :keranjang,
            :created_at,
            :code
        )
        """

        c.execute(sql,data_sisa)
        c.execute(sql,data_mutasi)

        # log mutasi ke tabel mutasipotong
        sql_log = """
        INSERT INTO mutasipotong (
            create_at, tanggal, shift, code_scan, code_baru,
            spk, customer, produk, uk, berat_awal, berat_bersih,
            operator, checker, keterangan
        ) VALUES (
            :create_at, :tanggal, :shift, :code_scan, :code_baru,
            :spk, :customer, :produk, :uk, :berat_awal, :berat_bersih,
            :operator, :checker, :keterangan
        )
        """
        c.execute(sql_log, row_sisa_log)
        c.execute(sql_log, row_mutasi_log)

        conn.commit()
        conn.close()
        
        # Simpan ke record_cache agar /label/print/<code>
        for rec_data, rec_code in [(data_sisa, code_sisa), (data_mutasi, code_mutasi)]:
            cache_rec = {
                "order_id": rec_code,
                "tanggal": tanggal,
                "shift": shift,
                "divisi": "POTONG",
                "spk": rec_data["spk"],
                "customer": rec_data["customer"],
                "produk": rec_data["produk"],
                "uk": rec_data["uk"],
                "operator_cu": operator,
                "keranjang": 1,
                "operator_mix": operator,
                "karung": 1,
                "checker": admin,
                "mesin": mesin,
                "berat_kg": rec_data["berat_kg"],
                "berat_bersih": rec_data["berat_bersih"],
                "created_at": created_at,
                "code": rec_code,
                "_label_tag": "MUTASI",
                "_source_route": "",
            }
            cleanup_cache()
            record_cache[rec_code] = (cache_rec, time.time())
        return jsonify(success=True, saved=2, code_sisa=code_sisa, code_mutasi=code_mutasi,
    print_urls=[
        f"/label/print/{code_sisa}",
        f"/label/print/{code_mutasi}"
    ]
)
    except Exception as e:
        import traceback

        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
    
CSV_MUTASI_PACKING = r"Z:\Checker\Production\Database\mutasi\katalogmutasipacking.csv"
CSV_MUTASI_PACKING_COLUMNS = ["create_at", "tanggal", "shift", "code_scan", "code_baru", "spk", "customer", "produk", "uk", "berat_awal", "berat_bersih", "operator", "checker", "keterangan"]

@app.route("/api/mutasi_packing", methods=["POST"])
@login_required
def api_mutasi_packing():
    try:
        data = request.get_json()
        code_awal     = (data.get("code_awal") or "").strip().upper()
        tanggal_raw   = (data.get("tanggal") or "").strip()
        shift         = (data.get("shift") or "").strip().upper()
        spk_baru      = (data.get("spk_baru") or "").strip()
        hasil_timbang = float(data.get("hasil_timbang") or 0)
        operator      = (data.get("operator") or "").strip()
        admin         = session.get("name", "")
        keterangan    = (data.get("keterangan") or "").strip()

        # VALIDASI
        if not code_awal:
            return jsonify(success=False, error="Kode awal wajib diisi")
        if not tanggal_raw:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not spk_baru:
            return jsonify(success=False, error="SPK baru wajib diisi")
        if not operator:
            return jsonify(success=False, error="Operator wajib dipilih")
        tanggal = format_tanggal(tanggal_raw)

        # LOOKUP DATA KATALOG
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM katalogpacking
            WHERE UPPER(TRIM(code)) = ?
            ORDER BY id DESC
            LIMIT 1
        """, (code_awal,)).fetchone()

        conn.close()

        if not row:
            return jsonify(success=False, error="Kode awal tidak ditemukan")

        r = dict(row)

        # DATA TIKET AWAL
        spk_awal = str(r.get("spk", "")).strip()
        customer = str(r.get("customer", "")).strip()
        produk = str(r.get("produk", "")).strip()
        uk = str(r.get("uk", "")).strip()
        mesin = str(r.get("mesin", "")).strip()

        try:
            berat_awal = float(
                r.get("berat_bersih")
                or r.get("berat_kg")
                or 0
            )
        except:
            berat_awal = 0

        # VALIDASI BERAT
        if hasil_timbang > berat_awal:
            return jsonify(success=False,error="Hasil timbang melebihi berat awal")
        terpakai = round(berat_awal - hasil_timbang,2)

        # LOOKUP SPK BARU
        customer_baru = customer
        produk_baru   = produk
        uk_baru       = uk

        try:
            if os.path.exists(SPK_CSV):
                df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python" )
                df_spk.columns = (df_spk.columns.str.strip())

                spk_col = next(
                    (
                        c for c in df_spk.columns
                        if "spk" in c.lower()
                    ),
                    df_spk.columns[1]
                )
                df_spk[spk_col] = (df_spk[spk_col].astype(str).str.strip())
                match_spk = df_spk[df_spk[spk_col]  == spk_baru]
                if not match_spk.empty:
                    rr = match_spk.iloc[0]
                    customer_baru = str(rr.iloc[3]).strip()
                    produk_baru = str(rr.iloc[4]).strip()
                    uk_baru = str(rr.iloc[7]).strip()

        except Exception as e:
            print("Lookup SPK baru gagal:",e)

        # DATETIME
        now = datetime.now()
        created_at = now.strftime("%d-%m-%Y %H:%M:%S")
        tanggal_code = now.strftime("%d-%m-%Y")
        timestamp = now.strftime("%H%M%S")

        def generate_code(spk, shift, berat):
            berat_str = (
                f"{float(berat):05.2f}"
            )
            return (
                f"PA"
                f"{tanggal_code}"
                f"{spk}"
                f"{shift}"
                f"{berat_str}"
                f"{timestamp}"
            )

        code_sisa = generate_code(spk_awal, shift, hasil_timbang)
        code_mutasi = generate_code(spk_baru, shift, terpakai)

        # ── SIAPKAN ROW LOG MUTASI ──
        row_sisa_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_sisa,
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "berat_awal": berat_awal,
            "berat_bersih": f"{terpakai:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }
        row_mutasi_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_mutasi,
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "berat_awal": berat_awal,
            "berat_bersih": f"{hasil_timbang:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }

        # SIMPAN CSV MUTASI PACKING

        # DATA BARU UNTUK KATALOG
        data_sisa = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "PACKING",
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "operator_pa": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_bersih": round(hasil_timbang,2),
            "created_at": created_at,
            "code": code_sisa
        }
        data_mutasi = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "PACKING",
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "operator_pa": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_bersih": round(terpakai,2),
            "created_at": created_at,
            "code": code_mutasi
        }

        # SIMPAN KE CSV_PACKING

        # SQLITE
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = """
        INSERT INTO katalogpacking (
            tanggal, shift, divisi, spk, customer, produk, uk, operator_pa, checker, mesin, berat_bersih, created_at, code
        ) VALUES (
            :tanggal,
            :shift,
            :divisi,
            :spk,
            :customer,
            :produk,
            :uk,
            :operator_pa,
            :checker,
            :mesin,
            :berat_bersih,
            :created_at,
            :code
        )
        """

        c.execute(sql,data_sisa)
        c.execute(sql,data_mutasi)

        # log mutasi ke tabel mutasipacking
        sql_log = """
        INSERT INTO mutasipacking (
            create_at, tanggal, shift, code_scan, code_baru,
            spk, customer, produk, uk, berat_awal, berat_bersih,
            operator, checker, keterangan
        ) VALUES (
            :create_at, :tanggal, :shift, :code_scan, :code_baru,
            :spk, :customer, :produk, :uk, :berat_awal, :berat_bersih,
            :operator, :checker, :keterangan
        )
        """
        c.execute(sql_log, row_sisa_log)
        c.execute(sql_log, row_mutasi_log)

        conn.commit()
        conn.close()
        
        # Simpan ke record_cache agar /label/print/<code>
        for rec_data, rec_code in [(data_sisa, code_sisa), (data_mutasi, code_mutasi)]:
            cache_rec = {
                "order_id": rec_code,
                "tanggal": tanggal,
                "shift": shift,
                "divisi": "PACKING",
                "spk": rec_data["spk"],
                "customer": rec_data["customer"],
                "produk": rec_data["produk"],
                "uk": rec_data["uk"],
                "operator_pa": operator,
                "operator_mix": operator,
                "checker": admin,
                "mesin": mesin,
                "berat_bersih": rec_data["berat_bersih"],
                "created_at": created_at,
                "code": rec_code,
                "_label_tag": "MUTASI",
                "_source_route": "",
            }
            cleanup_cache()
            record_cache[rec_code] = (cache_rec, time.time())
        return jsonify(success=True, saved=2, code_sisa=code_sisa, code_mutasi=code_mutasi,
    print_urls=[
        f"/label/print/{code_sisa}",
        f"/label/print/{code_mutasi}"
    ]
)
    except Exception as e:
        import traceback
        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
    
CSV_MUTASI_SISAPACK = r"Z:\Checker\Production\Database\mutasi\katalogmutasisisapack.csv"
CSV_MUTASI_SISAPACK_COLUMNS = ["create_at", "tanggal", "shift", "code_scan", "code_baru", "spk", "customer", "produk", "uk", "berat_awal", "berat_bersih", "operator", "checker", "keterangan"]

@app.route("/api/mutasi_sisapack", methods=["POST"])
@login_required
def api_mutasi_sisapack():
    try:
        data = request.get_json()
        code_awal     = (data.get("code_awal") or "").strip().upper()
        tanggal_raw   = (data.get("tanggal") or "").strip()
        shift         = (data.get("shift") or "").strip().upper()
        spk_baru      = (data.get("spk_baru") or "").strip()
        hasil_timbang = float(data.get("hasil_timbang") or 0)
        operator      = (data.get("operator") or "").strip()
        admin         = session.get("name", "")
        keterangan    = (data.get("keterangan") or "").strip()
        hasil_sisa    = float(data.get("hasil_sisa") or 0)

        # VALIDASI
        if not code_awal:
            return jsonify(success=False, error="Kode awal wajib diisi")
        if not tanggal_raw:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not spk_baru:
            return jsonify(success=False, error="SPK baru wajib diisi")
        if not operator:
            return jsonify(success=False, error="Operator wajib dipilih")

        tanggal = format_tanggal(tanggal_raw)
        # LOOKUP DATA KATALOG
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM katalogsisapack
            WHERE UPPER(TRIM(code)) = ?
            ORDER BY id DESC
            LIMIT 1
        """, (code_awal,)).fetchone()

        conn.close()

        if not row:
            return jsonify(success=False, error="Kode awal tidak ditemukan")

        r = dict(row)

        # DATA TIKET AWAL
        spk_awal = str(r.get("spk", "")).strip()
        customer = str(r.get("customer", "")).strip()
        produk = str(r.get("produk", "")).strip()
        uk = str(r.get("uk", "")).strip()
        mesin = str(r.get("mesin", "")).strip()

        try:
            berat_awal = float(
                r.get("berat_bersih")
                or 0
            )
        except:
            berat_awal = 0

        try:
            sisa_awal = float(
                r.get("sisa")
                or 0
            )
        except:
            sisa_awal = 0

        # VALIDASI BERAT
        if hasil_timbang > berat_awal:
            return jsonify(success=False, error="Hasil timbang melebihi berat awal")

        terpakai = round(berat_awal - hasil_timbang,2)
        terpakai_sisa = round(sisa_awal - hasil_sisa, 0)
        # LOOKUP SPK BARU
        customer_baru = customer
        produk_baru   = produk
        uk_baru       = uk

        try:
            if os.path.exists(SPK_CSV):

                df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python" )
                df_spk.columns = (df_spk.columns.str.strip())
                spk_col = next(
                    (
                        c for c in df_spk.columns
                        if "spk" in c.lower()
                    ),
                    df_spk.columns[1]
                )
                df_spk[spk_col] = (df_spk[spk_col].astype(str).str.strip())
                match_spk = df_spk[df_spk[spk_col] == spk_baru]

                if not match_spk.empty:
                    rr = match_spk.iloc[0]
                    customer_baru = str(rr.iloc[3]).strip()
                    produk_baru = str(rr.iloc[4]).strip()
                    uk_baru = str(rr.iloc[7]).strip()
        except Exception as e:
            print("Lookup SPK baru gagal:",e)

        # DATETIME
        now = datetime.now()
        created_at = now.strftime("%d-%m-%Y %H:%M:%S")
        tanggal_code = now.strftime("%d-%m-%Y")
        timestamp = now.strftime("%H%M%S")

        def generate_code(spk, shift, berat):
            berat_str = (
                f"{float(berat):05.2f}"
            )
            return (
                f"PS"
                f"{tanggal_code}"
                f"{spk}"
                f"{shift}"
                f"{berat_str}"
                f"{timestamp}"
            )

        code_sisa = generate_code(spk_awal, shift, hasil_timbang)
        code_mutasi = generate_code(spk_baru, shift, terpakai)

        # ── SIAPKAN ROW LOG MUTASI ──
        row_sisa_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_sisa,
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "berat_awal": berat_awal,
            "berat_bersih": f"{terpakai:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }
        row_mutasi_log = {
            "create_at": created_at,
            "tanggal": tanggal,
            "shift": shift,
            "code_scan": code_awal,
            "code_baru": code_mutasi,
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "berat_awal": berat_awal,
            "berat_bersih": f"{hasil_timbang:.2f}",
            "operator": operator,
            "checker": admin,
            "keterangan": keterangan
        }

        # SIMPAN CSV MUTASI SISAPACK

        # DATA BARU UNTUK KATALOG
        data_sisa = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "SISA_PACK",
            "spk": spk_awal,
            "customer": customer,
            "produk": produk,
            "uk": uk,
            "operator_sp": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_bersih": round(terpakai,2),
            "sisa": round(terpakai_sisa, 0),
            "created_at": created_at,
            "code": code_sisa
        }
        data_mutasi = {
            "tanggal": tanggal,
            "shift": shift,
            "divisi": "SISA_PACK",
            "spk": spk_baru,
            "customer": customer_baru,
            "produk": produk_baru,
            "uk": uk_baru,
            "operator_sp": operator,
            "checker": admin,
            "mesin": mesin,
            "berat_bersih": round(hasil_timbang,2),
            "sisa": round(hasil_sisa, 0),
            "created_at": created_at,
            "code": code_mutasi
        }

        # SIMPAN KE CSV_SISA_PACK

        # SQLITE
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        sql = """
        INSERT INTO katalogsisapack (
            tanggal, shift, divisi, spk, customer, produk, uk, operator_sp, checker, mesin, berat_bersih, sisa, created_at, code
        ) VALUES (
            :tanggal,
            :shift,
            :divisi,
            :spk,
            :customer,
            :produk,
            :uk,
            :operator_sp,
            :checker,
            :mesin,
            :berat_bersih,
            :sisa,
            :created_at,
            :code
        )
        """
        c.execute(sql,data_sisa)
        c.execute(sql,data_mutasi)

        # log mutasi ke tabel mutasisisapack
        sql_log = """
        INSERT INTO mutasisisapack (
            create_at, tanggal, shift, code_scan, code_baru,
            spk, customer, produk, uk, berat_awal, berat_bersih,
            operator, checker, keterangan
        ) VALUES (
            :create_at, :tanggal, :shift, :code_scan, :code_baru,
            :spk, :customer, :produk, :uk, :berat_awal, :berat_bersih,
            :operator, :checker, :keterangan
        )
        """
        c.execute(sql_log, row_sisa_log)
        c.execute(sql_log, row_mutasi_log)

        conn.commit()
        conn.close()
        
        # Simpan ke record_cache agar /label/print/<code>
        for rec_data, rec_code in [(data_sisa, code_sisa), (data_mutasi, code_mutasi)]:
            cache_rec = {
                "order_id": rec_code,
                "tanggal": tanggal,
                "shift": shift,
                "divisi": "SISA_PACK",
                "spk": rec_data["spk"],
                "customer": rec_data["customer"],
                "produk": rec_data["produk"],
                "uk": rec_data["uk"],
                "operator_sp": operator,
                "operator_mix": operator,
                "checker": admin,
                "mesin": mesin,
                "berat_bersih": rec_data["berat_bersih"],
                "sisa": rec_data["sisa"],
                "created_at": created_at,
                "code": rec_code,
                "_label_tag": "MUTASI",
                "_source_route": "",
            }
            cleanup_cache()
            record_cache[rec_code] = (cache_rec, time.time())
        return jsonify(success=True, saved=2, code_sisa=code_sisa, code_mutasi=code_mutasi,
    print_urls=[
        f"/label/print/{code_sisa}",
        f"/label/print/{code_mutasi}"
    ]
)
    except Exception as e:
        import traceback
        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
        
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

# ─── API: CODE LOOKUP
CATALOG_TABLE_MAP = {
    "MIXING":       "katalogmixing",
    "HD":           "kataloghd",
    "POTONG":       "katalogpotong",
    "SISA_POTONG":  "katalogsisapotong",
    "PACKING":      "katalogpacking",
    "SISA_PACK":    "katalogsisapack",
    "AVAL_MIXING":  "katalogavalmixing",
    "AVAL_HD":      "katalogavalHD",
    "AVAL_POTONG":  "katalogavalpotong",
    "AVAL_PACKING": "katalogavalpacking",
    "AVAL_QC":      "katalogavalqc",
}

@app.route("/api/lookup_code", methods=["POST"])
@login_required
def lookup_code():
    try:
        data = request.get_json()
        code = (data.get("code") or "").strip()

        if not code:
            return jsonify(found=False, error="Kode kosong")

        prefix, csv_file, catalog_key, divisi_label = get_prefix_from_code(code)

        if not prefix or catalog_key not in CATALOG_TABLE_MAP:
            return jsonify(found=False, error="Prefix kode tidak dikenal",
                           prefix=prefix or "", divisi_label="Unknown", csv_file=None)

        table = CATALOG_TABLE_MAP[catalog_key]

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table} WHERE TRIM(UPPER(code)) = ? LIMIT 1",
                  (code.strip().upper(),))
        row = c.fetchone()
        conn.close()

        if row is None:
            return jsonify(found=False, prefix=prefix, divisi_label=divisi_label, csv_file=csv_file)

        r = dict(row)
        return jsonify(
            found        = True,
            prefix       = prefix,
            divisi_label = divisi_label,
            csv_file     = csv_file,
            spk          = str(r.get("spk", "")),
            customer     = str(r.get("customer", "")),
            produk       = str(r.get("produk", "") or r.get("product", "")),
            uk           = str(r.get("uk", "")),
            berat_bersih = str(r.get("berat_bersih", "")),
            checker      = str(r.get("checker", "")),
            sisa         = str(r.get("sisa", "")),
        )

    except Exception as e:
        return jsonify(found=False, error=str(e))

TRANSFER_TABLE = {
    "MIXING":       "scantransfermixing",
    "HD":           "scantransferhd",
    "POTONG":       "scantransferpotong",
    "SISA_POTONG":  "scantransferpotong",
    "PACKING":      "scantransferpacking",
    "SISA_PACK":    "scantransferpacking",
}

#SCAN PEMAKAIAN
@app.route("/api/lookup_codep", methods=["POST"])
@login_required
def lookup_codep():
    try:
        data = request.get_json()
        code = (data.get("code") or "").strip()

        if not code:
            return jsonify(found=False, error="Kode kosong")

        # normalisasi code (biar tidak gagal karena spasi/format aneh)
        clean_code = "".join(code.strip().upper().split())

        prefix, csv_file, catalog_key, divisi_label = get_prefix_from_code(clean_code)

        catalog_key = (catalog_key or "").strip().upper()

        if not prefix:
            return jsonify(found=False, error="Prefix kosong")

        if catalog_key not in TRANSFER_TABLE:
            return jsonify(
                found=False,
                error=f"Prefix tidak dikenal: {catalog_key}",
                prefix=prefix,
                divisi_label="Unknown",
                csv_file=None,
                debug_keys=list(TRANSFER_TABLE.keys())
            )

        table = TRANSFER_TABLE[catalog_key]

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # DEBUG OPTIONAL (aktifkan kalau perlu)
        # print("TABLE:", table)
        # print("LOOKUP CODE:", clean_code)

        c.execute(f"""
            SELECT * FROM {table}
            WHERE REPLACE(UPPER(code), ' ', '') = ?
            LIMIT 1
        """, (clean_code,))

        row = c.fetchone()
        conn.close()

        if row is None:
            return jsonify(
                found=False,
                prefix=prefix,
                divisi_label=divisi_label,
                csv_file=csv_file,
                error="Data transfer tidak ditemukan",
                debug_code=clean_code,
                debug_table=table
            )

        r = dict(row)

        return jsonify(
            found=True,
            prefix=prefix,
            divisi_label=divisi_label,
            csv_file=csv_file,

            spk=str(r.get("spk", "")),
            customer=str(r.get("customer", "")),
            produk=str(r.get("produk", "")),
            uk=str(r.get("uk", "")),
            berat_bersih=str(r.get("berat_bersih", "")),
            checker=str(r.get("checker", "")),
            sisa=str(r.get("sisa", "")),
        )

    except Exception as e:
        print("ERROR:", str(e))
        print("TABLE YANG DIPAKAI:", table)
        return jsonify(found=False, error=str(e))

# ─── API: SAVE SCAN SALAH ───────────────────────────────────
@app.route("/save_csv", methods=["POST"])
@login_required
def save_csv():
    try:
        data = request.get_json()
        records = data.get("records", [])
        keterangan = data.get("keterangan", "")

        if not records:
            return jsonify(success=False, error="Tidak ada data")

        from collections import defaultdict
        groups = defaultdict(list)

        # ── GROUPING (tetap sama) ─────────────────────────────
        for rec in records:
            csv_file = rec.get("csv_file")

            if not csv_file or csv_file not in CSV_SCAN_FILES:
                _, csv_file, _, _ = get_prefix_from_code(rec.get("code", ""))

            if not csv_file or csv_file not in CSV_SCAN_FILES:
                return jsonify(
                    success=False,
                    error=f"Kode '{rec.get('code')}' tidak bisa ditentukan CSV tujuannya")

            groups[csv_file].append(rec)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scanned_by = session.get("name", "")

        # ── CSV SECTION DIHAPUS TOTAL ─────────────────────────

        # ── INSERT KE SQLITE (tetap sama) ─────────────────────
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        for csv_filename, recs in groups.items():
            table_divisi = SCAN_SALAH_TABLE_MAP.get(csv_filename)

            for rec in recs:
                row_vals = (
                    now_str,
                    rec.get("prefix", ""),
                    rec.get("prefix", ""),
                    rec.get("divisi_label", ""),
                    rec.get("spk", ""),
                    rec.get("customer", ""),
                    rec.get("produk", ""),
                    rec.get("uk", ""),
                    rec.get("checker", ""),
                    scanned_by,
                    rec.get("code", ""),
                    keterangan,
                )

                # tabel gabungan
                c.execute("""
                    INSERT INTO scan_salah
                    (create_at, divisi, prefix, divisi_label,
                     spk, customer, produk, uk,
                     checker, scanned_by, code, keterangan)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, row_vals)

                # tabel per divisi
                if table_divisi:
                    c.execute(f"""
                        INSERT INTO {table_divisi}
                        (create_at, divisi, prefix, divisi_label,
                         spk, customer, produk, uk,
                         checker, scanned_by, code, keterangan)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, row_vals)

        conn.commit()
        conn.close()

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
        tanggal = data.get("tanggal", "")
        shift   = data.get("shift", "")
        mesin   = data.get("mesin", "")

        if not records:
            return jsonify(success=False, error="Tidak ada data")
        if not tanggal:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not mesin:
            return jsonify(success=False, error="Mesin wajib dipilih")

        tanggal_clean = format_tanggal(tanggal)

        from collections import defaultdict
        groups = defaultdict(list)

        for rec in records:
            csv_file = rec.get("csv_file")

            if not csv_file or csv_file not in PEMAKAIAN_TABLE_MAP:
                prefix, _, _, _ = get_prefix_from_code(rec.get("code", ""))
                csv_file = PEMAKAIAN_MAP.get(prefix)

            if not csv_file or csv_file not in PEMAKAIAN_TABLE_MAP:
                return jsonify(
                    success=False,
                    error=f"Kode '{rec.get('code')}' tidak bisa ditentukan tabel tujuannya")
            groups[csv_file].append(rec)

        # INSERT KE SQLITE 
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scanned_by = session.get("name", "")

        for csv_filename, recs in groups.items():
            table_divisi = PEMAKAIAN_TABLE_MAP.get(csv_filename)
            for rec in recs:
                row_vals = (
                    now_str,
                    tanggal_clean,
                    shift,
                    rec.get("prefix", ""),
                    rec.get("prefix", ""),
                    rec.get("divisi_label", ""),
                    rec.get("spk", ""),
                    rec.get("customer", ""),
                    rec.get("produk", ""),
                    rec.get("uk", ""),
                    rec.get("checker", ""),
                    scanned_by,
                    rec.get("code", ""),
                    mesin,
                    rec.get("berat_bersih", ""),
                )
                # tabel gabungan
                c.execute("""
                    INSERT INTO scan_pemakaian
                    (create_at, tanggal, shift, divisi, prefix, divisi_label,
                    spk, customer, produk, uk, checker, scanned_by,
                    code, mesin, berat_bersih)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, row_vals)
                # tabel per-divisi
                if table_divisi:
                    c.execute(f"""
                        INSERT INTO {table_divisi}
                        (create_at, tanggal, shift, divisi, prefix, divisi_label,
                        spk, customer, produk, uk, checker, scanned_by,
                        code, mesin, berat_bersih)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, row_vals)

        conn.commit()
        conn.close()

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

@app.route("/save_transfer", methods=["POST"])
@login_required
def save_transfer():
    try:
        data    = request.get_json()
        records = data.get("records", [])
        tanggal = data.get("tanggal", "")
        shift   = data.get("shift", "")
        foreman = data.get("foreman", "")

        if not records:
            return jsonify(success=False, error="Tidak ada data")
        if not tanggal:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not foreman:
            return jsonify(success=False, error="Foreman wajib diisi")

        tanggal_clean = format_tanggal(tanggal)

        from collections import defaultdict
        groups = defaultdict(list)

        for rec in records:
            prefix, _, _, _ = get_prefix_from_code(rec.get("code", ""))
            csv_file = TRANSFER_MAP.get(prefix)

            if not csv_file or csv_file not in TRANSFER_TABLE_MAP:
                return jsonify(success=False, error=f"Kode '{rec.get('code')}' tidak bisa ditentukan CSV tujuannya (prefix: {prefix})")
            groups[csv_file].append(rec)

        # INSERT KE SQLITE
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scanned_by = session.get("name", "")

        for csv_filename, recs in groups.items():
            table_divisi = TRANSFER_TABLE_MAP.get(csv_filename)
            for rec in recs:
                row_vals = (
                    now_str,
                    tanggal_clean,
                    shift,
                    rec.get("prefix", ""),
                    rec.get("prefix", ""),
                    rec.get("divisi_label", ""),
                    rec.get("spk", ""),
                    rec.get("customer", ""),
                    rec.get("produk", ""),
                    rec.get("uk", ""),
                    rec.get("checker", ""),
                    scanned_by,
                    rec.get("code", ""),
                    foreman,
                    rec.get("berat_bersih", ""),
                )
                # tabel gabungan
                c.execute("""
                    INSERT INTO scan_transfer
                    (create_at, tanggal, shift, divisi, prefix, divisi_label,
                    spk, customer, produk, uk, checker, scanned_by,
                    code, foreman, berat_bersih)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, row_vals)
                # tabel per-divisi
                if table_divisi:
                    c.execute(f"""
                        INSERT INTO {table_divisi}
                        (create_at, tanggal, shift, divisi, prefix, divisi_label,
                        spk, customer, produk, uk, checker, scanned_by,
                        code, foreman, berat_bersih)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, row_vals)

        conn.commit()
        conn.close()

        return jsonify(success=True, saved=len(records))

    except Exception as e:
        return jsonify(success=False, error=str(e))

#SCAN TRANSFER  
@app.route("/api/lookup_transfer", methods=["POST"])
@login_required
def lookup_transfer():
    try:
        data = request.get_json()
        code = (data.get("code") or "").strip().upper()

        if not code:
            return jsonify(found=False, error="Kode kosong")

        prefix, csv_file, _, divisi_label = get_prefix_from_code(code)

        if not prefix:
            return jsonify(found=False, error="Prefix tidak dikenal", prefix="")

        # Tentukan file transfer yang relevan berdasarkan prefix
        transfer_file = TRANSFER_MAP.get(prefix)
        if not transfer_file or transfer_file not in CSV_SCAN_TFILES:
            return jsonify(found=False, error=f"Prefix '{prefix}' tidak punya file transfer", prefix=prefix,)

        path = CSV_SCAN_TFILES[transfer_file]
        if not path.exists():
            return jsonify(found=False, prefix=prefix, divisi_label=divisi_label, transfer_file=transfer_file, error="File scan_transfer tidak ditemukan", )

        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python")
        df.columns = df.columns.str.strip()

        if "code" not in df.columns:
            return jsonify(found=False, error="Kolom 'code' tidak ada di file transfer")

        df["code"] = df["code"].astype(str).str.strip().str.upper()
        match = df[df["code"] == code]

        if match.empty:
            return jsonify(found=False, prefix=prefix, divisi_label=divisi_label, transfer_file=transfer_file,)

        r = match.iloc[0]
        return jsonify(
            found        = True,
            prefix       = prefix,
            divisi_label = divisi_label,
            transfer_file= transfer_file,
            spk          = str(r.get("spk", "")),
            customer     = str(r.get("customer", "")),
            produk       = str(r.get("produk", "")),
            uk           = str(r.get("uk", "")),
            berat_bersih = str(r.get("berat_bersih", "")),
            checker      = str(r.get("checker", "")),
        )

    except Exception as e:
        return jsonify(found=False, error=str(e))

# ─── API: /save_retur ────────────────────────────────────────────────────────
@app.route("/save_retur", methods=["POST"])
@login_required
def save_retur():
    try:
        data       = request.get_json()
        records    = data.get("records", [])
        tanggal    = data.get("tanggal", "")
        shift      = data.get("shift", "")
        foreman    = data.get("foreman", "")
        keterangan = data.get("keterangan", "")

        if not records:
            return jsonify(success=False, error="Tidak ada data")
        if not tanggal:
            return jsonify(success=False, error="Tanggal wajib diisi")
        if not shift:
            return jsonify(success=False, error="Shift wajib dipilih")
        if not foreman:
            return jsonify(success=False, error="Foreman wajib diisi")

        tanggal_clean = format_tanggal(tanggal)
        now_str       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scanned_by    = session.get("name", "")

        # ── 1. Group per tabel transfer ─────────────────────────────────────
        from collections import defaultdict
        groups = defaultdict(list)

        for rec in records:
            code = (rec.get("code") or "").strip().upper()
            tf   = rec.get("transfer_file")

            if not tf or tf not in TRANSFER_TABLE_MAP:
                prefix, _, _, _ = get_prefix_from_code(code)
                tf = TRANSFER_MAP.get(prefix)

            if not tf or tf not in TRANSFER_TABLE_MAP:
                continue

            groups[tf].append(rec)

        deleted  = 0
        skipped  = 0
        log_rows = []

        # ── 2. Proses tiap tabel SQLite ─────────────────────────────────────
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        for tf, recs in groups.items():
            table = TRANSFER_TABLE_MAP.get(tf)
            if not table:
                skipped += len(recs)
                continue

            codes_to_delete = {
                (rec.get("code") or "").strip().upper()
                for rec in recs
            }

            for code_val in codes_to_delete:
                # Ambil data dulu untuk log
                c.execute(
                    f"SELECT * FROM {table} WHERE TRIM(UPPER(code)) = ? LIMIT 1",
                    (code_val,)
                )
                row = c.fetchone()

                if row is None:
                    skipped += 1
                    continue

                r = dict(row)
                rec_match = next(
                    (rec for rec in recs if (rec.get("code") or "").upper() == code_val),
                    {}
                )

                log_rows.append({
                    "create_at":    now_str,
                    "tanggal":      tanggal_clean,
                    "shift":        shift,
                    "divisi":       rec_match.get("prefix", str(r.get("prefix", ""))),
                    "prefix":       rec_match.get("prefix", str(r.get("prefix", ""))),
                    "divisi_label": rec_match.get("divisi_label", str(r.get("divisi_label", ""))),
                    "spk":          str(r.get("spk", "")),
                    "customer":     str(r.get("customer", "")),
                    "produk":       str(r.get("produk", "")),
                    "uk":           str(r.get("uk", "")),
                    "checker":      str(r.get("checker", "")),
                    "scanned_by":   scanned_by,
                    "code":         code_val,
                    "foreman":      foreman,
                    "berat_bersih": str(r.get("berat_bersih", "")),
                    "keterangan":   keterangan,
                })

                # Hapus dari SQLite
                c.execute(
                    f"DELETE FROM {table} WHERE TRIM(UPPER(code)) = ?",
                    (code_val,)
                )
                deleted += c.rowcount

        # ── 3. Insert log ke scan_retur SQLite ──────────────────────────────
        for row in log_rows:
            c.execute("""
                INSERT INTO scan_retur
                (create_at, tanggal, shift, divisi, prefix, divisi_label,
                 spk, customer, produk, uk, checker, scanned_by,
                 code, foreman, berat_bersih, keterangan)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row["create_at"], row["tanggal"], row["shift"],
                row["divisi"], row["prefix"], row["divisi_label"],
                row["spk"], row["customer"], row["produk"], row["uk"],
                row["checker"], row["scanned_by"], row["code"],
                row["foreman"], row["berat_bersih"], row["keterangan"],
            ))

        conn.commit()
        conn.close()

        # ── 4. Hapus dari CSV transfer ───────────────────────────────────────
        # ── 5. Tulis log retur ke CSV ────────────────────────────────────────
        return jsonify(success=True, deleted=deleted, skipped=skipped)

    except Exception as e:
        import traceback
        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
    
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
        elif div == "SISA_POTONG":
            record = {
                "order_id": order_id, "tanggal": format_tanggal(d.get("tanggal","")),
                "shift": d.get("shift"), "divisi": div,
                "spk": d.get("spk"), "customer": d.get("customer"),
                "produk": d.get("produk"), "uk": d.get("uk"),
                "operator_cu": d.get("operator_cu"), "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "bobin": float(d.get("bobin") or 0),
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
                "spk": d.get("spk"), "customer": d.get("customer"),
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
                "spk": d.get("spk"), "customer": d.get("customer"),
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
                "spk": d.get("spk"), "customer": d.get("customer"),
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
                "spk": d.get("spk"), "customer": d.get("customer"),
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
        elif div == "SUMMARY_SPK":
            record = {
                "spk": d.get("spk"),
                "so": d.get("so"),
                "tanggal": format_tanggal(d.get("tanggal","")),
                "customer": d.get("customer"),
                "product": d.get("product"),
                "warna": d.get("warna"),
                "aval": d.get("aval"),
                "uk": d.get("uk"),
                "lembar": d.get("lembar"),
                "pack": d.get("pack"),
                "kg": d.get("kg"),
                "berat_lembar": d.get("berat_lembar"),
                "berat_pack": d.get("berat_pack"),
                "tebal": d.get("tebal"),
                "order_ball": d.get("order_ball"),
                "qty": d.get("qty"),
                "checker": d.get("checker"),
                "satuan": d.get("satuan"),
                "blongsong": d.get("blongsong"),
                "etiket": d.get("etiket"),
                "mixing": d.get("mixing"),
            }
        elif div == "KARANTINA_MIXING":
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
        elif div == "KARANTINA_HD":
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
        elif div == "KARANTINA_POTONG":
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
        elif div == "KARANTINA_PACKING":
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
        else:
            return jsonify({"success": False, "message": "Divisi tidak dikenali"})
        save_record(record)

        input_page = (d.get("input_page") or "").strip()
        record["_source_route"] = "barcode" if input_page == "barcode" else ""
        cleanup_cache()
        record_cache[order_id] = (record, time.time())
        return jsonify({"success": True, "order_id": order_id, "label_url": f"/label/{order_id}", "print_url": f"/label/{order_id}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    
@app.route("/api/submit_summary_spk", methods=["POST"])
@login_required
def submit_summary_spk():
    try:
        d = request.json
        record = {
            "divisi": "SUMMARY_SPK",
            "spk": d.get("spk"),
            "so": d.get("so"),
            "tanggal": format_tanggal(d.get("tanggal", "")),
            "customer": d.get("customer"),
            "product": d.get("product"),
            "warna": d.get("warna"),
            "aval": d.get("aval"),
            "uk": d.get("uk"),
            "lembar": d.get("lembar"),
            "pack": d.get("pack"),
            "kg": d.get("kg"),
            "berat_lembar": d.get("berat_lembar"),
            "berat_pack": d.get("berat_pack"),
            "tebal": d.get("tebal"),
            "order_ball": d.get("order_ball"),
            "qty": d.get("qty"),
            "checker": d.get("checker"),
            "satuan": d.get("satuan"),
            "blongsong": d.get("blongsong"),
            "etiket": d.get("etiket"),
            "mixing": d.get("mixing"),
        }
        save_record(record)
        return jsonify({"success": True, "message": "Data berhasil disimpan"})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/check_spk_berat/<spk>")
@login_required
def check_spk_berat(spk):
    try:
        spk = str(spk).strip()

        # ── Limit dari Summary SPK (CSV tetap) ────────────────
        limit = None
        try:
            df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python")
            df_spk.columns = df_spk.columns.str.strip()
            spk_col = next(
                (c for c in df_spk.columns if "spk" in c.lower()),
                df_spk.columns[1]
            )
            df_spk[spk_col] = df_spk[spk_col].astype(str).str.strip()
            row_spk = df_spk[df_spk[spk_col] == spk]
            if not row_spk.empty:
                u_col = next(
                    (c for c in df_spk.columns if c.strip().upper() == "U"),
                    None
                )
                if u_col is None and len(df_spk.columns) > 20:
                    u_col = df_spk.columns[20]

                if u_col:
                    try:
                        limit = float(str(row_spk.iloc[0][u_col]).replace(",", ".").strip())
                    except:
                        limit = None

        except Exception as e:
            print(f"Gagal baca SPK CSV: {e}")

        # ── Ambil bad codes dari SQLite scansalahmixing ───────
        bad_codes = set()
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT code
                FROM scansalahmixing
                WHERE code IS NOT NULL
            """)
            bad_codes = {
                str(row[0]).strip()
                for row in cur.fetchall()
                if row[0]
            }
            conn.close()

        except Exception as e:
            print(f"Gagal baca scansalahmixing: {e}")

        # ── Hitung used dari SQLite katalogmixing ─────────────
        used = 0.0
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT code, berat_bersih
                FROM katalogmixing
                WHERE TRIM(spk) = ?
            """, (spk,))

            rows = cur.fetchall()
            for row in rows:
                code = str(row["code"]).strip() if row["code"] else ""

                # skip jika masuk scan salah
                if code in bad_codes:
                    continue
                try:
                    used += float(row["berat_bersih"] or 0)
                except:
                    pass
            conn.close()

        except Exception as e:
            print(f"Gagal baca katalogmixing: {e}")

        used = round(used, 2)

        remaining = (round(limit - used, 2)
            if limit is not None
            else None
        )
        over_limit = (
            used >= limit
            if limit is not None
            else False
        )

        return jsonify(spk=spk, limit=limit, used=used, remaining=remaining, over_limit=over_limit)

    except Exception as e:
        import traceback

        return jsonify(success=False, error=str(e), detail=traceback.format_exc())

@app.route("/api/check_spk_berat_hd/<spk>")
@login_required
def check_spk_berat_hd(spk):
    try:
        spk = str(spk).strip()

        # ── Limit dari Summary SPK (CSV tetap) ────────────────
        limit = None
        try:
            df_spk = pd.read_csv(SPK_CSV, encoding="utf-8-sig", dtype=str, on_bad_lines="skip", engine="python")
            df_spk.columns = df_spk.columns.str.strip()
            spk_col = next(
                (c for c in df_spk.columns if "spk" in c.lower()),
                df_spk.columns[1]
            )
            df_spk[spk_col] = df_spk[spk_col].astype(str).str.strip()
            row_spk = df_spk[df_spk[spk_col] == spk]
            if not row_spk.empty:
                u_col = next(
                    (c for c in df_spk.columns if c.strip().upper() == "U"),
                    None
                )
                if u_col is None and len(df_spk.columns) > 20:
                    u_col = df_spk.columns[20]
                if u_col:
                    try:
                        limit = float(str(row_spk.iloc[0][u_col]).replace(",", ".").strip())
                    except:
                        limit = None

        except Exception as e:
            print(f"Gagal baca SPK CSV: {e}")

        # ── Ambil code scan salah dari SQLite ────────────────
        bad_codes = set()

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT code
                FROM scansalahhd
                WHERE code IS NOT NULL
            """)
            bad_codes = {
                str(row[0]).strip()
                for row in cur.fetchall()
                if row[0]
            }
            conn.close()

        except Exception as e:
            print(f"Gagal baca scansalahhd: {e}")

        # ── Hitung total berat dari kataloghd ────────────────
        used = 0.0

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            if bad_codes:
                placeholders = ",".join(["?"] * len(bad_codes))

                sql = f"""
                    SELECT COALESCE(SUM(berat_bersih), 0)
                    FROM kataloghd
                    WHERE TRIM(spk)=?
                    AND code NOT IN ({placeholders})
                """

                params = [spk] + list(bad_codes)

            else:
                sql = """
                    SELECT COALESCE(SUM(berat_bersih), 0)
                    FROM kataloghd
                    WHERE TRIM(spk)=?
                """

                params = [spk]

            cur.execute(sql, params)

            result = cur.fetchone()
            used = float(result[0] or 0)

            conn.close()

        except Exception as e:
            print(f"Gagal baca kataloghd: {e}")

        used = round(used, 2)

        remaining = (
            round(limit - used, 2)
            if limit is not None
            else None
        )
        over_limit = (
            used >= limit
            if limit is not None
            else False
        )
        return jsonify(spk=spk, limit=limit, used=used, remaining=remaining, over_limit=over_limit)

    except Exception as e:
        import traceback

        return jsonify(success=False, error=str(e), detail=traceback.format_exc())
    
# Helper sorting kronologis untuk stok opname
def _tanggal_sort_key(tanggal_str):
    """DD-MM-YYYY -> YYYY-MM-DD biar bisa diurutkan. Gagal parse -> dianggap paling lama."""
    try:
        d, m, y = str(tanggal_str).strip().split("-")
        return f"{y}-{m}-{d}"
    except Exception:
        return "0000-00-00"

# Urutan shift dalam satu hari produksi: Pagi (P) -> Malam (M)
SHIFT_ORDER = {"P": 0, "PAGI": 0, "M": 1, "MALAM": 1}

def _shift_sort_key(shift_str):
    s = str(shift_str or "").strip().upper()
    return SHIFT_ORDER.get(s, 99)

def _build_stok_opname(divisi_key):

    config = {
        "hd": {
            "katalog_table": "kataloghd",
            "scansalah_table": "scansalahhd",
            "transfer_table": "scantransferhd",
        },
        "potong": {
            "katalog_table": "katalogpotong",
            "scansalah_table": "scansalahpotong",
            "transfer_table": "scantransferpotong",
        },
    }.get(divisi_key)

    if not config:
        return []

    katalog_table   = config["katalog_table"]
    scansalah_table = config["scansalah_table"]
    transfer_table  = config["transfer_table"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(f"SELECT code FROM {scansalah_table} WHERE code IS NOT NULL")
    bad_codes = {str(r[0]).strip().upper() for r in c.fetchall() if r[0]}

    c.execute(f"""
        SELECT tanggal, shift, spk, customer, produk, uk, code, berat_bersih
        FROM {katalog_table}
    """)
    katalog_rows = c.fetchall()

    c.execute(f"""
        SELECT tanggal, shift, spk, customer, produk, uk, code, berat_bersih
        FROM {transfer_table}
    """)
    transfer_rows = c.fetchall()

    conn.close()

    buckets = {}

    def get_bucket(tanggal, shift, spk, customer, produk, uk):
        key = (str(tanggal or "").strip(), str(shift or "").strip(), str(spk or "").strip())
        if key not in buckets:
            buckets[key] = {
                "tanggal": key[0],
                "shift": key[1],
                "spk": key[2],
                "customer": customer or "",
                "produk": produk or "",
                "uk": uk or "",
                "input_count": 0,
                "input_qty": 0.0,
                "transfer_count": 0,
                "transfer_qty": 0.0,
            }
        b = buckets[key]
        if not b["customer"] and customer:
            b["customer"] = customer
        if not b["produk"] and produk:
            b["produk"] = produk
        if not b["uk"] and uk:
            b["uk"] = uk
        return b

    for row in katalog_rows:
        r = dict(row)
        code = str(r.get("code", "") or "").strip().upper()
        if code in bad_codes:
            continue

        bucket = get_bucket(
            r.get("tanggal"), r.get("shift"), r.get("spk"),
            r.get("customer"), r.get("produk"), r.get("uk")
        )
        bucket["input_count"] += 1
        try:
            bucket["input_qty"] += float(r.get("berat_bersih") or 0)
        except (TypeError, ValueError):
            pass

    for row in transfer_rows:
        r = dict(row)
        bucket = get_bucket(
            r.get("tanggal"), r.get("shift"), r.get("spk"),
            r.get("customer"), r.get("produk"), r.get("uk")
        )
        bucket["transfer_count"] += 1
        try:
            bucket["transfer_qty"] += float(r.get("berat_bersih") or 0)
        except (TypeError, ValueError):
            pass

    by_spk = {}
    for b in buckets.values():
        by_spk.setdefault(b["spk"], []).append(b)

    result = []
    for spk, rows in by_spk.items():
        rows.sort(key=lambda b: (_tanggal_sort_key(b["tanggal"]), _shift_sort_key(b["shift"])))

        saldo = 0.0
        saldo_count = 0
        for b in rows:
            saldo_sebelum = round(saldo, 2)
            saldo += b["input_qty"]

            saldo_count_sebelum = saldo_count
            saldo_count += b["input_count"]

            transfer_qty = b["transfer_qty"]
            dari_shift_ini = min(transfer_qty, b["input_qty"])
            dari_stok_lama = round(transfer_qty - dari_shift_ini, 2)
            dari_shift_ini = round(dari_shift_ini, 2)

            transfer_count = b["transfer_count"]

            saldo -= transfer_qty
            saldo_akhir = round(saldo, 2)

            saldo_count -= transfer_count
            saldo_count_akhir = saldo_count

            result.append({
                "tanggal":        b["tanggal"],
                "shift":          b["shift"],
                "spk":            b["spk"],
                "customer":       b["customer"],
                "produk":         b["produk"],
                "uk":             b["uk"],
                "input_count":    b["input_count"],
                "input_qty":      round(b["input_qty"], 2),
                "transfer_count": transfer_count,
                "transfer_qty":   round(transfer_qty, 2),
                "transfer_dari_shift_ini": dari_shift_ini,
                "transfer_dari_stok_lama": dari_stok_lama,
                "saldo_sebelum":  saldo_sebelum,
                "saldo_akhir":    saldo_akhir,
                "saldo_count_sebelum": saldo_count_sebelum,
                "saldo_count_akhir":   saldo_count_akhir,
                "sisa_count":     saldo_count_akhir,
                "sisa_qty":       saldo_akhir,
            })

    def sort_key(r):
        return (_tanggal_sort_key(r["tanggal"]), _shift_sort_key(r["shift"]), r["spk"])

    result.sort(key=sort_key, reverse=True)
    return result


def _build_stok_ringkasan(divisi_key):

    rows = _build_stok_opname(divisi_key)

    latest_per_spk = {}
    for r in rows:
        spk = r["spk"]
        if spk not in latest_per_spk:
            latest_per_spk[spk] = r

    result = []
    for spk, r in latest_per_spk.items():
        stok_qty = r["saldo_akhir"]
        if stok_qty is None or stok_qty <= 0:
            continue  # sembunyikan yg sudah habis/minus
        result.append({
            "spk":        r["spk"],
            "customer":   r["customer"],
            "produk":     r["produk"],
            "uk":         r["uk"],
            "stok_count": r["saldo_count_akhir"],
            "stok_qty":   stok_qty,
        })

    result.sort(key=lambda r: r["stok_qty"], reverse=True)
    return result

@app.route("/api/stok_opname/hd")
@login_required
def api_stok_opname_hd():
    try:
        data = _build_stok_opname("hd")
        return jsonify(data)
    except Exception as e:
        print("ERROR api_stok_opname_hd:", e)
        return jsonify([])


@app.route("/api/stok_opname/potong")
@login_required
def api_stok_opname_potong():
    try:
        data = _build_stok_opname("potong")
        return jsonify(data)
    except Exception as e:
        print("ERROR api_stok_opname_potong:", e)
        return jsonify([])


@app.route("/api/stok_ringkasan/hd")
@login_required
def api_stok_ringkasan_hd():
    try:
        data = _build_stok_ringkasan("hd")
        return jsonify(data)
    except Exception as e:
        print("ERROR api_stok_ringkasan_hd:", e)
        return jsonify([])


@app.route("/api/stok_ringkasan/potong")
@login_required
def api_stok_ringkasan_potong():
    try:
        data = _build_stok_ringkasan("potong")
        return jsonify(data)
    except Exception as e:
        print("ERROR api_stok_ringkasan_potong:", e)
        return jsonify([])
    
def _build_stok_karantina(divisi_key):
    """
    Hitung total stok karantina per SPK untuk masing-masing divisi.
    divisi_key: 'mixing' | 'hd' | 'potong' | 'packing'
    """
    table_map = {
        "mixing":  ("karantinamixing",  "berat_bersih"),
        "hd":      ("karantinahd",      "berat_bersih"),
        "potong":  ("karantinapotong",  "berat_bersih"),
        "packing": ("karantinapacking", "berat_bersih"),
    }
    if divisi_key not in table_map:
        return []

    table, qty_col = table_map[divisi_key]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(f"""
        SELECT spk, customer, produk, uk,
               COUNT(*)        AS stok_count,
               SUM({qty_col})  AS stok_qty
        FROM {table}
        WHERE spk IS NOT NULL
        GROUP BY spk, customer, produk, uk
        HAVING stok_qty > 0
        ORDER BY stok_qty DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    for r in rows:
        r["stok_count"] = int(r["stok_count"] or 0)
        r["stok_qty"]   = round(float(r["stok_qty"] or 0), 2)

    return rows


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/api/stok_karantina/mixing")
@login_required
def api_stok_karantina_mixing():
    try:
        return jsonify(_build_stok_karantina("mixing"))
    except Exception as e:
        print("ERROR api_stok_karantina_mixing:", e)
        return jsonify([])

@app.route("/api/stok_karantina/hd")
@login_required
def api_stok_karantina_hd():
    try:
        return jsonify(_build_stok_karantina("hd"))
    except Exception as e:
        print("ERROR api_stok_karantina_hd:", e)
        return jsonify([])

@app.route("/api/stok_karantina/potong")
@login_required
def api_stok_karantina_potong():
    try:
        return jsonify(_build_stok_karantina("potong"))
    except Exception as e:
        print("ERROR api_stok_karantina_potong:", e)
        return jsonify([])

@app.route("/api/stok_karantina/packing")
@login_required
def api_stok_karantina_packing():
    try:
        return jsonify(_build_stok_karantina("packing"))
    except Exception as e:
        print("ERROR api_stok_karantina_packing:", e)
        return jsonify([])
    
# ─── API: RECENT ────────────────────────────────────────────
@app.route("/api/recent/<divisi>")
@login_required
def recent(divisi):
    try:
        divisi = (divisi or "").strip().lower()
        table_map = {
            "mixing":       "katalogmixing",
            "hd":           "kataloghd",
            "potong":       "katalogpotong",
            "sisa_potong":  "katalogsisapotong",
            "packing":      "katalogpacking",
            "sisa_pack":    "katalogsisapack",
            "aval_mixing":  "katalogavalmixing",
            "aval_hd":      "katalogavalhd",
            "aval_potong":  "katalogavalpotong",
            "aval_packing": "katalogavalpacking",
            "aval_qc":      "katalogavalqc",
            "karantina_mixing":       "karantinamixing",
            "karantina_hd":           "karantinahd",
            "karantina_potong":       "karantinapotong",
            "karantina_packing":      "karantinapacking",
        }
        table = table_map.get(divisi)
        if not table:
            return jsonify([])

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 500")
        rows = c.fetchall()
        conn.close()

        result = []
        for row in rows:
            d = dict(row)
            # konversi None ke ""
            result.append({k: ("" if v is None else v) for k, v in d.items()})

        return jsonify(result)

    except Exception as e:
        print("ERROR recent():", e)
        return jsonify([])

# ─── RUN ────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    init_csv(CSV_MIXING)
    init_csv(CSV_HD)
    init_csv(CSV_POTONG)
    init_csv(CSV_SISA_POTONG)
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