"""
app.py — VoidLog API
─────────────────────────────────────────────────────────────────
Para rodar:
    pip install flask
    python app.py

A API sobe em http://0.0.0.0:5000
"""

import os
from flask import Flask, jsonify, render_template, send_from_directory
from database import init_db
from routes.rfid import rfid_bp
from routes.pecas import pecas_bp
from routes.movimentacoes import mov_bp
from routes.operadores import operadores_bp
from routes.auth import auth_bp

app = Flask(__name__)
app.secret_key = os.environ.get("VOIDLOG_SECRET", "voidlog-dev-secret-change-in-prod")

# Registra todos os blueprints sob /api
app.register_blueprint(rfid_bp,         url_prefix="/api")
app.register_blueprint(pecas_bp,  url_prefix="/api")
app.register_blueprint(mov_bp,          url_prefix="/api")
app.register_blueprint(operadores_bp,   url_prefix="/api")
app.register_blueprint(auth_bp,         url_prefix="/api")


@app.route('/')
def index():
    return render_template('dashboard.html')


# ── Rota de saúde ───────────────────────────────────────────────────
@app.route("/api/ping")
def ping():
    return jsonify({"status": "online", "sistema": "VoidLog"})


# ── Mapa de rotas ───────────────────────────────────────────────────
@app.route("/api/rotas")
def rotas():
    return jsonify({
        "Autenticação": {
            "POST /api/auth/login":    "Login (email + senha)",
            "POST /api/auth/logout":   "Logout",
            "GET  /api/auth/me":       "Dados do usuário logado",
        },
        "Usuários (admin)": {
            "GET  /api/usuarios":      "Lista todos os usuários",
            "POST /api/usuarios":      "Cria novo usuário",
            "PUT  /api/usuarios/<id>": "Edita usuário",
            "DELETE /api/usuarios/<id>": "Desativa usuário",
        },
        "RFID (ESP32)": {
            "POST /api/rfid": "Envia leitura de tag ou crachá"
        },
        "Peças": {
            "GET  /api/pecas":              "Lista todas (filtros: setor, unidade, disponivel)",
            "GET  /api/pecas/<peca_code>":  "Detalhe de uma peca",
            "POST /api/pecas":              "Cadastra nova peca",
            "DELETE /api/pecas/<peca_code>": "Remove peca",
            "GET  /api/pecas/uid/<uid>":    "Decodifica bytes de um UID",
        },
        "Operadores": {
            "GET  /api/operadores":        "Lista todos os operadores",
            "POST /api/operadores":        "Cadastra novo operador",
            "DELETE /api/operadores/<id>": "Remove operador",
            "GET  /api/operadores/ativos": "Sessões abertas agora",
        },
        "Movimentações": {
            "GET /api/movimentacoes": "Histórico (filtros: setor, unidade, tipo, data_ini, data_fim)"
        },
        "Dashboard": {
            "GET /api/dashboard/dados": "Totais e séries para gráficos"
        },
        "Alertas": {
            "GET /api/alertas": "Peças em uso / estoque crítico"
        },
    })


if __name__ == "__main__":
    init_db()
    print("\n[VoidLog] API rodando em http://0.0.0.0:5000")
    print("[VoidLog] Login padrão: admin@voidlog.local / admin123")
    print("[VoidLog] Mapa de rotas: http://localhost:5000/api/rotas\n")
    app.run(host="0.0.0.0", port=5000, debug=True)

admin = conn.execute("SELECT id FROM usuarios WHERE email='admin@voidlog.local'").fetchone()
if not admin:
    conn.execute(
        "INSERT INTO usuarios (nome,email,senha_hash,perfil) VALUES (?,?,?,?)",
        ("Administrador", "admin@voidlog.local", _hash("admin123"), "admin")
    )
