# ─────────────────────────────────────────────────────────────
# LOGIN SYSTEM
# Tambahkan import ini di bagian atas app.py (jika belum ada):
#
#   from flask import session
#   import functools
#
# Tambahkan juga secret key setelah app = Flask(__name__):
#
#   app.secret_key = "ganti-dengan-secret-key-aman"
#
# Path ke file Excel users:
USER_EXCEL = r"Z:\Checker\Production\other\other.xlsx"
USER_SHEET = "User"   # nama sheet
# ─────────────────────────────────────────────────────────────

import functools
from flask import session


def load_users():
    """Baca kolom name, username, password dari sheet User di other.xlsx."""
    df = pd.read_excel(USER_EXCEL, sheet_name=USER_SHEET, engine="openpyxl")
    df.columns = df.columns.str.strip()          # hapus spasi di header
    df = df.dropna(subset=["username", "password"])
    df["username"] = df["username"].astype(str).str.strip()
    df["password"] = df["password"].astype(str).str.strip()
    return df


def login_required(f):
    """Decorator — redirect ke /login kalau belum login."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


# ─── LOGIN PAGE ──────────────────────────────────────────────
@app.route("/login", methods=["GET"])
def login_page():
    if session.get("logged_in"):
        return redirect("/")
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
            session["logged_in"] = True
            session["username"]  = username
            session["name"]      = str(match.iloc[0].get("name", username))
            return jsonify(success=True, redirect="/")
        else:
            return jsonify(success=False, message="Username atau password salah.")

    except FileNotFoundError:
        return jsonify(success=False, message="File data user tidak ditemukan.")
    except Exception as e:
        return jsonify(success=False, message=f"Error: {str(e)}")


# ─── LOGOUT ──────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ─────────────────────────────────────────────────────────────
# CARA PAKAI:
# Tambahkan @login_required di setiap route yang ingin dilindungi.
# Contoh:
#
#   @app.route("/mixing")
#   @login_required
#   def mixing():
#       return render_template("index.html", active_page="mixing")
#
#   @app.route("/hd")
#   @login_required
#   def hd():
#       return render_template("hd.html", active_page="hd")
#
# (dst untuk semua route yang ada)
# ─────────────────────────────────────────────────────────────
