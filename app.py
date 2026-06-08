"""
app.py — VoidLog API
─────────────────────────────────────────────────────────────────
Para rodar:
    pip install flask
    python app.py

A API sobe em http://0.0.0.0:5000
"""

import os
import json
import time
import queue
import threading
from flask import Flask, jsonify, render_template, send_from_directory, Response, stream_with_context
from database import init_db
from routes.rfid import rfid_bp
from routes.pecas import pecas_bp
from routes.movimentacoes import mov_bp
from routes.operadores import operadores_bp
from routes.auth import auth_bp
from routes.terminais import terminais_bp

app = Flask(__name__)
app.secret_key = os.environ.get("VOIDLOG_SECRET", "voidlog-dev-secret-change-in-prod")

# ── SSE broadcast broker ────────────────────────────────────────────
# Qualquer parte do backend chama `sse_push(evento, dados)` para
# notificar todos os clientes conectados em tempo real.
_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()

def sse_push(event: str, data: dict | None = None):
    """Envia um evento SSE para todos os clientes conectados."""
    msg = f"event: {event}\ndata: {json.dumps(data or {})}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)

# Expõe para os blueprints importarem
app.sse_push = sse_push

# Registra todos os blueprints sob /api
app.register_blueprint(rfid_bp,        url_prefix="/api")
app.register_blueprint(pecas_bp,       url_prefix="/api")
app.register_blueprint(mov_bp,         url_prefix="/api")
app.register_blueprint(operadores_bp,  url_prefix="/api")
app.register_blueprint(auth_bp,        url_prefix="/api")
app.register_blueprint(terminais_bp,   url_prefix="/api")


@app.route('/')
def index():
    return render_template('dashboard.html')


# ── SSE stream ──────────────────────────────────────────────────────
@app.route("/api/events")
def events():
    """Endpoint SSE — dashboard escuta aqui para atualizações em tempo real."""
    q: queue.Queue = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        # Heartbeat inicial
        yield ": connected\n\n"
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": ping\n\n"   # mantém conexão viva
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


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
