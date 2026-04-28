"""
Factory Label System - Main Application
"""

from flask import Flask, render_template, request, jsonify, send_file
import qrcode
from PIL import Image, ImageDraw, ImageFont
import csv
import os
import sqlite3
import json
from datetime import datetime
import io
import base64

app = Flask(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DB_PATH         = os.path.join(BASE_DIR, "data", "production.db")
CSV_PATH        = os.path.join(BASE_DIR, "data", "production_output.csv")
LABELS_DIR      = os.path.join(BASE_DIR, "labels_output")

LABEL_WIDTH_MM  = 100
LABEL_HEIGHT_MM = 60
DPI             = 203

def mm_to_px(mm): return int(mm * DPI / 25.4)
LABEL_W = mm_to_px(LABEL_WIDTH_MM)
LABEL_H = mm_to_px(LABEL_HEIGHT_MM)

# ─── SPK MASTER DATA ───────────────────────────────────────────────────────────
# Key   = Nomor SPK (uppercase)
# Value = { divisi, produk }
SPK_MASTER = {
    "SPK-001": {"divisi": "HDPE Kantong",  "produk": "Kantong 30x50"},
    "SPK-002": {"divisi": "HDPE Kantong",  "produk": "Kantong 40x60"},
    "SPK-003": {"divisi": "HDPE Kantong",  "produk": "Kantong 50x70"},
    "SPK-004": {"divisi": "HDPE Kantong",  "produk": "Kantong 60x90"},
    "SPK-005": {"divisi": "HDPE Rol",      "produk": "Rol Natural 60cm"},
    "SPK-006": {"divisi": "HDPE Rol",      "produk": "Rol Hitam 80cm"},
    "SPK-007": {"divisi": "HDPE Rol",      "produk": "Rol Putih 100cm"},
    "SPK-008": {"divisi": "PP Woven",      "produk": "Karung 50kg"},
    "SPK-009": {"divisi": "PP Woven",      "produk": "Karung 25kg"},
    "SPK-010": {"divisi": "PP Woven",      "produk": "Big Bag 1000L"},
    "SPK-011": {"divisi": "PET Sheet",     "produk": "Sheet 0.5mm"},
    "SPK-012": {"divisi": "PET Sheet",     "produk": "Sheet 1mm"},
    "SPK-013": {"divisi": "PET Sheet",     "produk": "Sheet 2mm"},
    "SPK-014": {"divisi": "LDPE Film",     "produk": "Film 0.03mm"},
    "SPK-015": {"divisi": "LDPE Film",     "produk": "Film 0.05mm"},
    "SPK-016": {"divisi": "LDPE Film",     "produk": "Film 0.08mm"},
    "SPK-017": {"divisi": "LLDPE Stretch", "produk": "Stretch 17mic"},
    "SPK-018": {"divisi": "LLDPE Stretch", "produk": "Stretch 20mic"},
    "SPK-019": {"divisi": "LLDPE Stretch", "produk": "Stretch 23mic"},
}

# ─── DATABASE ──────────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_output (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            no_spk     TEXT NOT NULL,
            divisi     TEXT NOT NULL,
            produk     TEXT NOT NULL,
            tanggal    TEXT NOT NULL,
            waktu      TEXT NOT NULL,
            shift      TEXT NOT NULL,
            no_mesin   TEXT NOT NULL,
            operator   TEXT NOT NULL,
            checker    TEXT NOT NULL,
            berat_kg   REAL NOT NULL,
            qr_string  TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ─── CSV ───────────────────────────────────────────────────────────────────────
CSV_HEADERS = [
    "no_spk","divisi","produk","tanggal","waktu","shift",
    "no_mesin","operator","checker","berat_kg","qr_string","created_at"
]

def init_csv():
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()

def save_record(data: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO production_output
            (no_spk,divisi,produk,tanggal,waktu,shift,
             no_mesin,operator,checker,berat_kg,qr_string,created_at)
        VALUES
            (:no_spk,:divisi,:produk,:tanggal,:waktu,:shift,
             :no_mesin,:operator,:checker,:berat_kg,:qr_string,:created_at)
    """, data)
    conn.commit()
    conn.close()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_HEADERS).writerow(
            {k: data.get(k, "") for k in CSV_HEADERS}
        )

# ─── QR STRING FORMAT ──────────────────────────────────────────────────────────
# divisi & DD-MM-YYYY & nomor_spk & shift & berat(00.00) & HH:MM:SS
def build_qr_string(data: dict) -> str:
    dt    = datetime.strptime(data["tanggal"], "%Y-%m-%d")
    date  = dt.strftime("%d-%m-%Y")
    berat = f"{float(data['berat_kg']):.2f}"
    return f"{data['divisi']}&{date}&{data['no_spk']}&{data['shift']}&{berat}&{data['waktu']}"

# ─── QR IMAGE ──────────────────────────────────────────────────────────────────
def generate_qr_image(qr_string: str) -> Image.Image:
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6, border=2
    )
    qr.add_data(qr_string)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

# ─── LABEL IMAGE ───────────────────────────────────────────────────────────────
def generate_label_image(data: dict, qr_string: str) -> Image.Image:
    img  = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(img)

    try:
        f_bold   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        f_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        f_small  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      17)
        f_tiny   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      14)
    except IOError:
        f_bold = f_medium = f_small = f_tiny = ImageFont.load_default()

    PAD     = 10
    qr_size = LABEL_H - PAD * 2
    text_x  = PAD + qr_size + PAD

    # QR code — full left panel
    qr_img = generate_qr_image(qr_string)
    qr_img = qr_img.resize((qr_size, qr_size))
    img.paste(qr_img, (PAD, PAD))

    # Header bar
    y = PAD
    draw.rectangle([text_x, y, LABEL_W - PAD, y + 30], fill="black")
    draw.text((text_x + 5, y + 5), "OUTPUT PRODUKSI", font=f_medium, fill="white")
    y += 36

    # SPK number — prominent
    draw.text((text_x, y), data["no_spk"], font=f_bold, fill="black")
    y += 30

    # Divider
    draw.line([text_x, y, LABEL_W - PAD, y], fill="#aaaaaa", width=1)
    y += 6

    # Format date DD-MM-YYYY
    try:
        tanggal_fmt = datetime.strptime(data["tanggal"], "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        tanggal_fmt = data["tanggal"]

    shift_short = "Morning" if "morning" in data["shift"].lower() else "Night"

    fields = [
        ("Produk",   data["produk"]),
        ("Divisi",   data["divisi"]),
        ("Mesin",    data["no_mesin"]),
        ("Operator", data["operator"]),
        ("Checker",  data["checker"]),
        ("Shift",    shift_short),
        ("Tgl/Jam",  f"{tanggal_fmt} {data['waktu']}"),
        ("Berat",    f"{float(data['berat_kg']):.2f} kg"),
    ]

    for lbl, val in fields:
        if y > LABEL_H - 20:
            break
        draw.text((text_x,      y), lbl + ":", font=f_tiny,  fill="#555555")
        draw.text((text_x + 65, y), val,        font=f_small, fill="black")
        y += 20

    draw.rectangle([0, 0, LABEL_W - 1, LABEL_H - 1], outline="black", width=2)
    return img

# ─── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", spk_json=json.dumps(SPK_MASTER))

@app.route("/api/spk/<no_spk>")
def get_spk(no_spk):
    info = SPK_MASTER.get(no_spk.upper())
    if info:
        return jsonify({"found": True, **info})
    return jsonify({"found": False})

@app.route("/api/spk_list")
def spk_list():
    return jsonify(SPK_MASTER)

@app.route("/api/submit", methods=["POST"])
def submit():
    d   = request.json
    now = datetime.now()

    spk_key  = d["no_spk"].upper()
    spk_info = SPK_MASTER.get(spk_key, {})
    divisi   = spk_info.get("divisi", "")
    produk   = spk_info.get("produk", "")

    tanggal  = d.get("tanggal", now.strftime("%Y-%m-%d"))
    waktu    = d.get("waktu",   now.strftime("%H:%M:%S"))
    shift    = d.get("shift", "")

    record = {
        "no_spk":    spk_key,
        "divisi":    divisi,
        "produk":    produk,
        "tanggal":   tanggal,
        "waktu":     waktu,
        "shift":     shift,
        "no_mesin":  d["no_mesin"],
        "operator":  d["operator"],
        "checker":   d["checker"],
        "berat_kg":  float(d["berat_kg"]),
        "qr_string": "",
        "created_at": now.isoformat(),
    }

    qr_string           = build_qr_string(record)
    record["qr_string"] = qr_string

    save_record(record)

    label_img = generate_label_image(record, qr_string)
    buf = io.BytesIO()
    label_img.save(buf, format="PNG", dpi=(DPI, DPI))
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()

    os.makedirs(LABELS_DIR, exist_ok=True)
    file_key = f"{spk_key}_{now.strftime('%Y%m%d_%H%M%S')}"
    label_img.save(os.path.join(LABELS_DIR, f"{file_key}.png"), dpi=(DPI, DPI))

    return jsonify({
        "success":       True,
        "file_key":      file_key,
        "qr_string":     qr_string,
        "label_preview": b64,
    })

@app.route("/api/print/<file_key>")
def print_label(file_key):
    path = os.path.join(LABELS_DIR, f"{file_key}.png")
    if not os.path.exists(path):
        return jsonify({"error": "Label not found"}), 404
    return send_file(path, mimetype="image/png", as_attachment=False)

@app.route("/api/download_label/<file_key>")
def download_label(file_key):
    path = os.path.join(LABELS_DIR, f"{file_key}.png")
    if not os.path.exists(path):
        return jsonify({"error": "Label not found"}), 404
    return send_file(path, as_attachment=True, download_name=f"{file_key}.png")

@app.route("/api/download_csv")
def download_csv():
    return send_file(CSV_PATH, as_attachment=True, download_name="production_output.csv")

@app.route("/api/recent")
def recent_records():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM production_output ORDER BY created_at DESC LIMIT 25"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/history")
def history():
    return render_template("history.html")

# ─── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    init_csv()
    print("=" * 55)
    print("  Factory Label System  →  http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=True)
