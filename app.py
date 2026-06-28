"""
app.py — VoidLog v3
"""

import json
import queue
import threading
from datetime import datetime
from flask import Flask, render_template, Response, session, redirect, url_for
from database import get_db, init_db

from routes.auth          import auth_bp
from routes.equipamentos  import equipamentos_bp, pecas_compat_bp
from routes.operadores    import operadores_bp
from routes.movimentacoes import movimentacoes_bp
from routes.terminais     import terminais_bp
from routes.rfid          import rfid_bp
from routes.manutencao    import manutencao_bp
from routes.dashboard     import dashboard_bp

app = Flask(__name__)
app.secret_key = "voidlog-v3-secret-change-me-in-production"

# ── SSE broadcast ──────────────────────────────────────────────────────────

_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _sse_push(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


app.sse_push = _sse_push


@app.route("/events")
def sse_stream():
    q: queue.Queue = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        yield "event: connected\ndata: {}\n\n"
        try:
            while True:
                msg = q.get(timeout=30)
                yield msg
        except (queue.Empty, GeneratorExit):
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ── Blueprints ─────────────────────────────────────────────────────────────

for bp in [auth_bp, equipamentos_bp, pecas_compat_bp,
           operadores_bp, movimentacoes_bp, terminais_bp,
           rfid_bp, manutencao_bp, dashboard_bp]:
    app.register_blueprint(bp, url_prefix="/api")


# ── Dashboard web ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "usuario_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("dashboard.html")


@app.route("/login")
def login_page():
    return render_template("dashboard.html")


@app.context_processor
def inject_now():
    return {"now": datetime.now()}


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
