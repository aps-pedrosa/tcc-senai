"""
app.py — VoidLog API
─────────────────────────────────────────────────────────────────
Para rodar:
    pip install flask
    python app.py

A API sobe em http://0.0.0.0:5000
"""

from flask import Flask, jsonify, render_template, send_from_directory
from database import init_db
from routes.rfid import rfid_bp
from routes.ferramentas import ferramentas_bp
from routes.movimentacoes import mov_bp
from routes.operadores import operadores_bp

app = Flask(__name__)

# Registra todos os blueprints sob /api
app.register_blueprint(rfid_bp,         url_prefix="/api")
app.register_blueprint(ferramentas_bp,  url_prefix="/api")
app.register_blueprint(mov_bp,          url_prefix="/api")
app.register_blueprint(operadores_bp,   url_prefix="/api")


@app.route('/')
def index():
    return render_template('dashboard.html')

# ── Rota de saúde (health check) ───────────────────────────────────
@app.route("/api/ping")
def ping():
    return jsonify({"status": "online", "sistema": "VoidLog"})


# ── Mapa de rotas disponíveis ───────────────────────────────────────
@app.route("/api/rotas")
def rotas():
    return jsonify({
        "RFID (ESP32)": {
            "POST /api/rfid": "Envia leitura de tag ou crachá"
        },
        "Ferramentas": {
            "GET  /api/ferramentas":              "Lista todas (filtros: setor, unidade, disponivel)",
            "GET  /api/ferramentas/<peca_code>":  "Detalhe de uma ferramenta",
            "POST /api/ferramentas":              "Cadastra nova ferramenta",
            "GET  /api/ferramentas/uid/<uid>":    "Decodifica bytes de um UID",
        },
        "Operadores": {
            "GET  /api/operadores":        "Lista todos os operadores",
            "POST /api/operadores":        "Cadastra novo operador",
            "GET  /api/operadores/ativos": "Sessões abertas agora",
        },
        "Movimentações": {
            "GET /api/movimentacoes": "Histórico (filtros: setor, unidade, tipo, data_ini, data_fim)"
        },
        "Dashboard": {
            "GET /api/dashboard/dados": "Totais e séries para gráficos"
        },
        "Alertas": {
            "GET /api/alertas": "Ferramentas em uso / estoque crítico"
        },
    })


if __name__ == "__main__":
    init_db()
    print("\n[VoidLog] API rodando em http://0.0.0.0:5000")
    print("[VoidLog] Mapa de rotas: http://localhost:5000/api/rotas\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
