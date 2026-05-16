import socket
import webbrowser
import pandas as pd
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)
EXCEL_PATH = "resultats_participation.xlsx"
_PASSWORD = "admin123"


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def load_data():
    df = pd.read_excel(EXCEL_PATH)
    data = []
    for _, r in df.iterrows():
        data.append({
            "nom": r["Nom"],
            "email": r.get("Email", ""),
            "tests": int(r["Tests (/40)"]),
            "presence": float(r["Présence (/30)"]),
            "github": int(r["GitHub (/30)"]),
            "total": float(r["Total (/90)"]),
            "pct": r["Pourcentage"],
            "details": r.get("Détails du Score", ""),
            "matricule": r.get("Matricule", ""),
        })
    return data


def compute_stats(data):
    totals = [d["total"] for d in data]
    return {
        "count": len(data),
        "moyenne": round(sum(totals) / len(totals), 2),
        "min": round(min(totals), 2),
        "max": round(max(totals), 2),
        "median": round(sorted(totals)[len(totals) // 2], 2),
    }


@app.route("/")
def index():
    data = load_data()
    stats = compute_stats(data)
    return render_template("dashboard.html", data=data, stats=stats)


@app.route("/api/data")
def api_data():
    data = load_data()
    q = request.args.get("q", "").strip().lower()
    if q:
        data = [d for d in data if q in d["nom"].lower()]
    return jsonify(data)


@app.route("/shutdown", methods=["POST"])
def shutdown():
    pwd = request.json.get("password") if request.is_json else ""
    if pwd != _PASSWORD:
        return jsonify({"ok": False, "error": "Mot de passe incorrect"}), 403
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
    else:
        import os
        os._exit(0)
    return jsonify({"ok": True})


if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 5000
    print("=" * 60)
    print("  DASHBOARD GROUPE R — EN LIGNE")
    print("=" * 60)
    print(f"  Local    : http://127.0.0.1:{port}")
    print(f"  LAN      : http://{local_ip}:{port}")
    print(f"  Partagez le lien LAN aux membres du groupe")
    print(f"  Mot de passe pour éteindre : {_PASSWORD}")
    print(f"  Pour fermer : Ctrl+C ici ou bouton dans le dashboard")
    print("=" * 60)
    webbrowser.open(f"http://127.0.0.1:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
