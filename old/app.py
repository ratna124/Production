from flask import Flask, render_template, request, jsonify, redirect
import qrcode
from PIL import Image, ImageDraw
import csv, os, sqlite3, json, io, base64, uuid
from datetime import datetime
import pandas as pd

app = Flask(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, "data", "production.db")
CSV_PATH   = os.path.join(BASE_DIR, "data", "katalogmixing.csv")
LABELS_DIR = os.path.join(BASE_DIR, "labels_output")

LABEL_W, LABEL_H = 800, 400


# ─── LOAD SPK ─────────────────
def load_spk_data():
    df = pd.read_csv(r"C:\Coba\Summary SPK.csv", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df[["No. SPK", "CUSTOMER", "PRODUCT", "UK"]]


# ─── DB INIT ───────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

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
            operator TEXT,
            checker TEXT,
            jumlah_roll INTEGER,
            berat_kg REAL,
            keterangan TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─── CSV INIT ──────────────────
CSV_HEADERS = [
    "order_id","tanggal","shift","divisi",
    "spk","customer","produk","uk",
    "operator","checker",
    "jumlah_roll","berat_kg",
    "keterangan","created_at"
]

def init_csv():
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()


# ─── SAVE DATA ─────────────────
def save_record(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        INSERT INTO katalogmixing VALUES (
        NULL,:order_id,:tanggal,:shift,:divisi,
        :spk,:customer,:produk,:uk,
        :operator,:checker,
        :jumlah_roll,:berat_kg,
        :keterangan,:created_at)
    """, data)

    conn.commit()
    conn.close()

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow({k: data.get(k, "") for k in CSV_HEADERS})


# ─── QR ───────────────────────
def generate_qr(order_id, data):
    payload = json.dumps({
        "order_id": order_id,
        "spk": data.get("spk",""),
        "produk": data.get("produk",""),
        "berat": data.get("berat_kg",0)
    })
    return qrcode.make(payload).convert("RGB")


# ─── LABEL ─────────────────────
def generate_label_image(order_id, data):
    img = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(img)

    qr = generate_qr(order_id, data).resize((200,200))
    img.paste(qr, (20,100))

    y = 20
    draw.text((250,y), f"ORDER : {order_id}", fill="black"); y+=40
    draw.text((250,y), f"SPK : {data.get('spk','')}", fill="black"); y+=30
    draw.text((250,y), f"CUSTOMER : {data.get('customer','')}", fill="black"); y+=30
    draw.text((250,y), f"PRODUK : {data.get('produk','')}", fill="black"); y+=30
    draw.text((250,y), f"UK : {data.get('uk','')}", fill="black"); y+=30
    draw.text((250,y), f"ROLL : {data.get('jumlah_roll',0)}", fill="black"); y+=30
    draw.text((250,y), f"KG : {data.get('berat_kg',0)}", fill="black")

    return img


# ─── ROUTES ───────────────────
@app.route("/")
def home():
    return redirect("/mixing")


@app.route("/mixing")
def mixing():
    return render_template("index.html")


# ─── SPK AUTO ────────────────
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


# ─── SUBMIT (FIX TOTAL) ───────
@app.route("/api/submit", methods=["POST"])
def submit():
    try:
        d = request.json or {}

        print("🔥 DATA MASUK:", d)

        order_id = f"{d.get('divisi','MIX')[:3]}-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4]}"

        record = {
            "order_id": order_id,
            "tanggal": d.get("tanggal"),
            "shift": d.get("shift"),
            "divisi": d.get("divisi"),

            "spk": d.get("spk"),
            "customer": d.get("customer"),
            "produk": d.get("produk"),
            "uk": d.get("uk"),

            "operator": d.get("operator_mix") or d.get("operator"),
            "checker": d.get("checker"),

            "jumlah_roll": int(d.get("jumlah_roll") or 0),
            "berat_kg": float(d.get("berat_kg") or 0),
            "keterangan": d.get("keterangan"),
            "created_at": datetime.now().isoformat()
        }

        save_record(record)
        print("✔ SAVED CSV + DB")

        img = generate_label_image(order_id, record)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        os.makedirs(LABELS_DIR, exist_ok=True)
        img.save(os.path.join(LABELS_DIR, f"{order_id}.png"))

        print("✔ LABEL GENERATED")

        return jsonify({
            "success": True,
            "order_id": order_id,
            "label_preview": base64.b64encode(buf.read()).decode()
        })

    except Exception as e:
        print("🔥 ERROR:", e)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ─── HISTORY ─────────────────
@app.route("/api/recent")
def recent():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM katalogmixing ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─── RUN ─────────────────────
if __name__ == "__main__":
    init_db()
    init_csv()
    app.run(host="0.0.0.0", port=5000, debug=True)