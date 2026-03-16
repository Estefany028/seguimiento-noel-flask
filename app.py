import os
import ssl
import requests
import urllib3
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, abort

from services import (
    obtener_personas_vigentes_externo,
    obtener_solicitudes_admin,
    actualizar_consecutivo
)
from pipeline import revalidar_activos_base

# =========================
# DOTENV (UNA SOLA VEZ)
# =========================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

print("ENV_PATH =", ENV_PATH)
print("ADMIN_TOKEN (.env) =", repr(os.getenv("ADMIN_TOKEN")))

# =========================
# SSL PATCH (igual que tenías)
# =========================
ssl._create_default_https_context = ssl._create_unverified_context

_original_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    kwargs["verify"] = False
    return _original_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")

def is_admin_request():
    token = (request.headers.get("X-ADMIN-TOKEN") or request.args.get("admin_token") or "").strip()
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    print("[ADMIN DEBUG] token=", repr(token), "expected=", repr(expected), "equal=", token == expected)
    return token != "" and token == expected

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/external")
def api_external():
    return jsonify(obtener_personas_vigentes_externo())

@app.get("/api/admin/solicitudes")
def api_admin_solicitudes():
    if not is_admin_request():
        abort(403)
    return jsonify(obtener_solicitudes_admin())

@app.post("/api/admin/consecutivo")
def api_admin_consecutivo():
    if not is_admin_request():
        abort(403)

    payload = request.get_json(force=True)
    row = int(payload["row"])
    consecutivo = str(payload["consecutivo"]).strip()

    if not consecutivo:
        return jsonify({"ok": False, "error": "Consecutivo vacío"}), 400

    actualizar_consecutivo(row=row, consecutivo=consecutivo)
    return jsonify({"ok": True})

@app.post("/api/admin/revalidar")
def api_admin_revalidar():
    if not is_admin_request():
        abort(403)
    return jsonify(revalidar_activos_base())

@app.get("/api/admin/debug_auth")
def debug_auth():
    token = (request.headers.get("X-ADMIN-TOKEN") or request.args.get("admin_token") or "").strip()
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    return jsonify({
        "token_repr": repr(token),
        "expected_repr": repr(expected),
        "equal": token == expected
    })

@app.post("/api/admin/consecutivos/batch")
def api_admin_consecutivos_batch():
    if not is_admin_request():
        abort(403)

    payload = request.get_json(force=True)
    changes = payload.get("changes", [])

    if not isinstance(changes, list) or not changes:
        return jsonify({"ok": False, "error": "Sin cambios"}), 400

    from services import actualizar_consecutivos_batch
    actualizar_consecutivos_batch(changes)
    return jsonify({"ok": True, "updated": len(changes)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
