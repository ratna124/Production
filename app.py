from flask import Flask, render_template, request, jsonify, redirect, send_file
import qrcode
from PIL import Image, ImageDraw, ImageFont
import csv, os, sqlite3, json, io, base64, uuid
from datetime import datetime
import pandas as pd
from pathlib import Path

app = Flask(__name__)

BASE_DIR = Path(r"Z:\Checker\Production\scan_salah")

CSV_FILES = {
    "Mixing":  BASE_DIR / "scansalahmixing.csv",
    "HD":      BASE_DIR / "scansalahhd.csv",
    "Potong": BASE_DIR / "scansalahpotong.csv",
    "Packing": BASE_DIR / "scansalahpacking.csv",
    "SisaPack": BASE_DIR / "scansalahsisapack.csv",
}

CSV_COLUMNS = ["create_at", "divisi", "code"]

def ensure_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()


@app.route("/save_csv", methods=["POST"])
def save_csv():
    data = request.get_json()

    divisi = data.get("divisi")
    codes = data.get("codes")

    if divisi not in CSV_FILES:
        return jsonify(success=False, error="Divisi tidak valid")

    path = CSV_FILES[divisi]
    ensure_csv(path)

    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

            for code in codes:
                writer.writerow({
                    "create_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "divisi": divisi,
                    "code": code
                })

        return jsonify(success=True)

    except Exception as e:
        return jsonify(success=False, error=str(e))

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, "data", "production.db")
CSV_MIXING   = r"Z:\Checker\Production\katalogmixing.csv"
CSV_HD   = r"Z:\Checker\Production\kataloghd.csv"
CSV_POTONG   = r"Z:\Checker\Production\katalogpotong.csv"
CSV_PACKING   = r"Z:\Checker\Production\katalogpacking.csv"
CSV_SISA_PACK   = r"Z:\Checker\Production\katalogsisapack.csv"
CSV_AVAL_MIXING   = r"Z:\Checker\Production\katalogavalmixing.csv"
LABELS_DIR = r"Z:\Checker\Production\labels_output"

LABEL_W = 560
LABEL_H = 240


# ─── QR ─────────────────
def generate_qr(code):
    qr = qrcode.make(code)
    return qr.convert("RGB")


# ─── SPK ─────────────────
def load_spk_data():
    df = pd.read_csv(r"Z:\Checker\Summary SPK.csv", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df[["No. SPK", "CUSTOMER", "PRODUCT", "UK"]]

# INIT DB
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # MIXING
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        tanggal TEXT,
        shift TEXT,
        divisi TEXT,
        spk TEXT,
        customer TEXT,
        produk TEXT,
        uk TEXT,
        operator_mix TEXT,
        checker TEXT,
        berat_bersih REAL,
        karung REAL,
        created_at TEXT,
        code TEXT
    )
    """)

    # HD 
    c.execute("""
    CREATE TABLE IF NOT EXISTS kataloghd (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        tanggal TEXT,
        shift TEXT,
        divisi TEXT,
        spk TEXT,
        customer TEXT,
        produk TEXT,
        uk TEXT,
        operator_hd TEXT,
        checker TEXT,
        mesin REAL,
        berat_kg REAL,
        bobin REAL,
        berat_bersih REAL,
        created_at TEXT,
        code TEXT
    )
    """)

    # POTONG
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogpotong (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        tanggal TEXT,
        shift TEXT,
        divisi TEXT,
        spk TEXT,
        customer TEXT,
        produk TEXT,
        uk TEXT,
        operator_cu TEXT,
        checker TEXT,
        mesin REAL,
        berat_kg REAL,
        keranjang REAL,
        berat_bersih REAL,
        created_at TEXT,
        code TEXT
    )
    """)

    # PACKING
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogpacking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        tanggal TEXT,
        shift TEXT,
        divisi TEXT,
        spk TEXT,
        customer TEXT,
        produk TEXT,
        uk TEXT,
        operator_pa TEXT,
        checker TEXT,
        mesin REAL,
        berat_bersih REAL,
        created_at TEXT,
        code TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogsisapack (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        tanggal TEXT,
        shift TEXT,
        divisi TEXT,
        spk TEXT,
        customer TEXT,
        produk TEXT,
        uk TEXT,
        operator_sp TEXT,
        checker TEXT,
        mesin REAL,
        berat_bersih REAL,
        sisa REAL,
        created_at TEXT,
        code TEXT
    )
    """)

    # AVAL MIXING
    c.execute("""
    CREATE TABLE IF NOT EXISTS katalogavalmixing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        tanggal TEXT,
        shift TEXT,
        divisi TEXT,
        spk TEXT,
        operator_amix TEXT,
        checker TEXT,
        mesin REAL,
        berat_bersih REAL,
        jenis REAL,
        created_at TEXT,
        code TEXT
    )
    """)

    conn.commit()
    conn.close()



# ─── CSV ─────────────────
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

    # SAVE CSV
def save_record(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # NORMALISASI DIVISI (biar gak case-sensitive error)
    div = (data.get("divisi") or "").strip().upper()

    # ================= HD =================
    if div == "HD":
        c.execute("""
        INSERT INTO kataloghd (
            tanggal, shift, divisi,
            spk, customer, produk, uk,
            operator_hd, checker,
            mesin, berat_kg, bobin, berat_bersih,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi,
            :spk, :customer, :produk, :uk,
            :operator_hd, :checker,
            :mesin, :berat_kg, :bobin, :berat_bersih,
            :created_at, :code
        )
        """, data)

        csv_path = CSV_HD

    # ================= POTONG =================
    elif div == "POTONG":
        c.execute("""
        INSERT INTO katalogpotong (
            tanggal, shift, divisi,
            spk, customer, produk, uk,
            operator_cu, checker,
            mesin, berat_kg, keranjang, berat_bersih,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi,
            :spk, :customer, :produk, :uk,
            :operator_cu, :checker,
            :mesin, :berat_kg, :keranjang, :berat_bersih,
            :created_at, :code
        )
        """, data)

        csv_path = CSV_POTONG

        # ================= PACKING =================
    elif div == "PACKING":
        c.execute("""
        INSERT INTO katalogpacking (
            tanggal, shift, divisi,
            spk, customer, produk, uk,
            operator_pa, checker,
            berat_bersih,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi,
            :spk, :customer, :produk, :uk,
            :operator_pa, :checker,
            :berat_bersih,
            :created_at, :code
        )
        """, data)

        csv_path = CSV_PACKING

            # ================= SISA_PACK =================
    elif div == "SISA_PACK":
        c.execute("""
        INSERT INTO katalogsisapack (
            tanggal, shift, divisi,
            spk, customer, produk, uk,
            operator_sp, checker, mesin,
            berat_bersih, sisa,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi,
            :spk, :customer, :produk, :uk,
            :operator_sp, :checker, :mesin,
            :berat_bersih, :sisa,
            :created_at, :code
        )
        """, data)

        csv_path = CSV_SISA_PACK

    # ================= MIXING =================
    elif div == "MIXING":
        c.execute("""
        INSERT INTO katalogmixing (
            tanggal, shift, divisi,
            spk, customer, produk, uk,
            operator_mix, checker,
            berat_bersih, karung,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi,
            :spk, :customer, :produk, :uk,
            :operator_mix, :checker,
            :berat_bersih, :karung,
            :created_at, :code
        )
        """, data)

        csv_path = CSV_MIXING
    
    # ================= AVAL MIXING =================
    if div == "AVAL_MIXING":
        c.execute("""
        INSERT INTO katalogavalmixing (
            tanggal, shift, divisi,
            spk,
            operator_amix, checker,
            mesin, berat_bersih, jenis,
            created_at, code
        ) VALUES (
            :tanggal, :shift, :divisi,
            :spk,
            :operator_amix, :checker,
            :mesin, :berat_bersih, :jenis,
            :created_at, :code
        )
        """, data)

        csv_path = CSV_AVAL_MIXING

    else:
        conn.close()
        raise ValueError(f"Divisi tidak dikenali: {div}")

    conn.commit()
    conn.close()

    # ================= CSV =================
    if div == "HD":
        headers = [
            "tanggal","shift","divisi",
            "spk","customer","produk","uk",
            "operator_hd","checker","mesin",
            "berat_kg","bobin","berat_bersih",
            "created_at","code"
        ]

    elif div == "POTONG":
        headers = [
            "tanggal","shift","divisi",
            "spk","customer","produk","uk",
            "operator_cu","checker",
            "mesin","berat_kg","keranjang","berat_bersih",
            "created_at","code"
        ]

    elif div == "PACKING":
        headers = [
            "tanggal","shift","divisi",
            "spk","customer","produk","uk",
            "operator_pa","checker",
            "mesin","berat_bersih",
            "created_at","code"
        ]

    elif div == "SISA_PACK":
        headers = [
            "tanggal","shift","divisi",
            "spk","customer","produk","uk",
            "operator_sp","checker",
            "mesin","berat_bersih", "sisa",
            "created_at","code"
        ]
    
    elif div == "AVAL_MIXING":
        headers = [
            "tanggal","shift","divisi",
            "spk",
            "operator_amix","checker",
            "mesin","berat_bersih", "jenis",
            "created_at","code"
        ]

    else:  # MIXING
        headers = [
            "tanggal","shift","divisi",
            "spk","customer","produk","uk",
            "operator_mix","checker",
            "berat_bersih","karung",
            "created_at","code"
        ]

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)

        if f.tell() == 0:
            writer.writeheader()

        writer.writerow({k: data.get(k, "") for k in headers})


# ─── CODE ─────────────────
def generate_code(data):
    now = datetime.now()

    # Mapping divisi
    div_raw = str(data.get("divisi", "")).strip().upper()

    div_map = {
        "MIXING": "MI",
        "HD": "HD",
        "POTONG": "CU",
        "PACKING": "PA",
        "SISA_PACK": "PS",
        "AVAL_MIXING": "AMS"
    }

    div = div_map.get(div_raw, "XX")

    # Format tanggal → 25-04-2026
    tanggal = now.strftime("%d-%m-%Y")

    # Ambil data
    spk = str(data.get("spk", "")).strip()
    shift = str(data.get("shift", "")).strip()

    # Format berat → 30.11
    try:
        berat = "{:.2f}".format(float(data.get("berat_bersih") or 0))
    except:
        berat = "0.00"

    # Format jam → 120554
    waktu = now.strftime("%H%M%S")

    # FINAL FORMAT
    code = f"{div}{tanggal}{spk}{shift}{berat}{waktu}"

    return code


# ─── LABEL ─────────────────
def generate_label_image(order_id, data):
    img = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(img)

    qr = generate_qr(data["code"]).resize((180, 180))
    img.paste(qr, (10, 30))

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()

    x = 210
    y = 20
    gap = 22

    text_data = [
        data.get("customer"),
        data.get("spk"),
        data.get("produk"),
        data.get("uk"),
        data.get("operator_mix") or data.get("operator_hd") or data.get("operator_cu")or data.get("operator_pa")or data.get("operator_sp")or data.get("operator_amix"),
        f"{data.get('berat_bersih')} kg",
        f"{data.get('karung')} kg",
        data.get("divisi"),
        data.get("tanggal"),
        data.get("shift"),
        data.get("checker"),
        data.get("created_at")
    ]

    for i, t in enumerate(text_data):
        draw.text((x, y + i * gap), str(t), fill="black", font=font)

    return img


# ─── ROUTES ─────────────────
@app.route("/")
def home():
    return redirect("/mixing")

@app.route("/mixing")
def mixing():
    return render_template("index.html", active_page="mixing")

@app.route("/hd")
def hd():
    return render_template("hd.html", active_page="hd")

@app.route("/potong")
def potong():
    return render_template("potong.html", active_page="potong")

@app.route("/packing")
def packing():
    return render_template("packing.html", active_page="packing")

@app.route("/sisa_pack")
def sisa_pack():
    return render_template("sisa_pack.html", active_page="sisa_pack")

@app.route("/aval_mixing")
def aval_mixing():
    return render_template("aval_mixing.html", active_page="aval_mixing")

@app.route("/aval_hd")
def aval_hd():
    return render_template("aval_hd.html", active_page="aval_hd")

@app.route("/scan_salah")
def scan_salah():
    return render_template("scan_salah.html", active_page="scan_salah")

@app.route("/get-spk/<spk>")
def get_spk(spk):
    df = load_spk_data()
    row = df[df["No. SPK"].astype(str) == str(spk)]

    if not row.empty:
        r = row.iloc[0]
        return jsonify({
            "customer": r["CUSTOMER"],
            "product": r["PRODUCT"],
            "uk": r["UK"]
        })

    return jsonify({})


# ─── SUBMIT ─────────────────
@app.route("/api/submit", methods=["POST"])
def submit():
    try:
        d = request.json

        order_id = str(uuid.uuid4())[:8]
        code = generate_code(d)

        div = d.get("divisi")

        # ================= HD =================
        if div == "HD":
            record = {
                "order_id": order_id,
                "tanggal": d.get("tanggal", "").split("T")[0],
                "shift": d.get("shift"),
                "divisi": div,
                "spk": d.get("spk"),
                "customer": d.get("customer"),
                "produk": d.get("produk"),
                "uk": d.get("uk"),
                "operator_hd": d.get("operator_hd"),
                "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "bobin": float(d.get("bobin") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "code": code
            }

        # ================= POTONG =================
        elif div == "Potong":
            record = {
                "order_id": order_id,
                "tanggal": d.get("tanggal", "").split("T")[0],
                "shift": d.get("shift"),
                "divisi": div,
                "spk": d.get("spk"),
                "customer": d.get("customer"),
                "produk": d.get("produk"),
                "uk": d.get("uk"),
                "operator_cu": d.get("operator_cu"),
                "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_kg": float(d.get("berat_kg") or 0),
                "keranjang": float(d.get("keranjang") or 0),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "code": code
            }

        elif div == "Packing":
            record = {
                "order_id": order_id,
                "tanggal": d.get("tanggal", "").split("T")[0],
                "shift": d.get("shift"),
                "divisi": div,
                "spk": d.get("spk"),
                "customer": d.get("customer"),
                "produk": d.get("produk"),
                "uk": d.get("uk"),
                "operator_pa": d.get("operator_pa"),
                "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "code": code
            }

        elif div == "Sisa_Pack":
            record = {
                "order_id": order_id,
                "tanggal": d.get("tanggal", "").split("T")[0],
                "shift": d.get("shift"),
                "divisi": div,
                "spk": d.get("spk"),
                "customer": d.get("customer"),
                "produk": d.get("produk"),
                "uk": d.get("uk"),
                "operator_sp": d.get("operator_sp"),
                "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "sisa": float(d.get("sisa") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "code": code
            }

        elif div == "Aval_Mixing":
            record = {
                "order_id": order_id,
                "tanggal": d.get("tanggal", "").split("T")[0],
                "shift": d.get("shift"),
                "divisi": div,
                "spk": d.get("spk"),
                "operator_amix": d.get("operator_amix"),
                "checker": d.get("checker"),
                "mesin": d.get("mesin"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "jenis": d.get("jenis"),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "code": code
            }

        # ================= MIXING =================
        elif div == "Mixing":
            record = {
                "order_id": order_id,
                "tanggal": d.get("tanggal", "").split("T")[0],
                "shift": d.get("shift"),
                "divisi": div,
                "spk": d.get("spk"),
                "customer": d.get("customer"),
                "produk": d.get("produk"),
                "uk": d.get("uk"),
                "operator_mix": d.get("operator_mix"),
                "checker": d.get("checker"),
                "berat_bersih": float(d.get("berat_bersih") or 0),
                "karung": float(d.get("karung") or 0),
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                "code": code
            }

        else:
            return jsonify({"success": False, "message": "Divisi tidak dikenali"})

        # ✔ SIMPAN SEKALI SAJA
        save_record(record)

        # ✔ LABEL SEKALI SAJA
        img = generate_label_image(order_id, record)

        os.makedirs(LABELS_DIR, exist_ok=True)
        path = os.path.join(LABELS_DIR, f"{order_id}.png")
        img.save(path)

        return jsonify({
            "success": True,
            "order_id": order_id,
            "label_url": f"/label/{order_id}",
            "print_url": f"/label/{order_id}"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ─── LABEL VIEW ─────────────────
@app.route("/label/<order_id>")
def label(order_id):
    path = os.path.join(LABELS_DIR, f"{order_id}.png")
    return send_file(path, mimetype="image/png")


# ─── RECENT ─────────────────
@app.route("/api/recent/<divisi>")
def recent(divisi):
    try:
        divisi = (divisi or "").strip().lower()

        # MAP FILE
        if divisi == "hd":
            path = CSV_HD
        elif divisi == "potong":
            path = CSV_POTONG
        elif divisi == "packing":
            path = CSV_PACKING
        elif divisi == "sisa_pack":
            path = CSV_SISA_PACK
        elif divisi == "aval_mixing":
            path = CSV_AVAL_MIXING
        elif divisi == "mixing":
            path = CSV_MIXING
        else:
            return jsonify({
                "success": False,
                "message": "Divisi tidak dikenali"
            })

        # CEK FILE ADA
        if not os.path.exists(path):
            return jsonify([])

        # READ CSV
        df = pd.read_csv(path, encoding="utf-8")
        df = df.fillna("")

        # URUT TERBARU DI ATAS
        df = df.iloc[::-1]

        return jsonify(df.to_dict(orient="records"))

    except Exception as e:
        print("ERROR recent():", e)
        return jsonify([])

# ─── RUN ─────────────────
if __name__ == "__main__":
    init_db()
    init_csv(CSV_MIXING)
    init_csv(CSV_HD)
    init_csv(CSV_POTONG)
    init_csv(CSV_PACKING)
    init_csv(CSV_SISA_PACK)
    init_csv(CSV_AVAL_MIXING)
    print("=" * 55)
    print("  Factory Label System running at http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=True)