"""
routes/terminais.py — VoidLog
─────────────────────────────────────────────────────────────────
Gerenciamento de terminais ESP32.

GET  /api/terminal/<id>/config      → ESP32 busca config + registra presença
GET  /api/terminais                 → lista todos (dashboard)
GET  /api/terminais/pendentes       → apenas aguardando aprovação
PUT  /api/terminal/<id>/config      → admin salva setor/unidade/apelido
PUT  /api/terminal/<id>/aprovar     → admin aprova terminal
PUT  /api/terminal/<id>/rejeitar    → admin rejeita terminal
DELETE /api/terminal/<id>           → admin remove terminal
"""

from flask import Blueprint, request, jsonify
from database import get_db

terminais_bp = Blueprint("terminais", __name__)


# ── GET config — chamado pelo ESP32 ──────────────────────────────

@terminais_bp.route("/terminal/<terminal_id>/config", methods=["GET"])
def get_config(terminal_id):
    db  = get_db()
    ip  = request.remote_addr
    ver = request.args.get("fw", "2.0")

    # Verifica se terminal já existe
    terminal = db.execute(
        "SELECT * FROM terminais WHERE terminal_id = ?", (terminal_id,)
    ).fetchone()

    if terminal is None:
        # Primeiro acesso — cria como pendente
        db.execute("""
            INSERT INTO terminais (terminal_id, ip_address, firmware_ver, status, ultimo_acesso)
            VALUES (?, ?, ?, 'pendente', CURRENT_TIMESTAMP)
        """, (terminal_id, ip, ver))
        db.commit()
        return jsonify({
            "status": "pendente",
            "msg": "Terminal aguardando aprovação do administrador."
        }), 403

    status = terminal["status"] or "pendente"

    if status == "pendente":
        return jsonify({
            "status": "pendente",
            "msg": "Terminal aguardando aprovação do administrador."
        }), 403

    if status == "rejeitado":
        return jsonify({
            "status": "rejeitado",
            "msg": "Terminal rejeitado pelo administrador."
        }), 403

    # Aprovado — atualiza presença e devolve config
    db.execute("""
        UPDATE terminais SET ip_address=?, firmware_ver=?, ultimo_acesso=CURRENT_TIMESTAMP
        WHERE terminal_id=?
    """, (ip, ver, terminal_id))
    db.commit()

    setores  = db.execute("SELECT codigo, nome FROM setores  ORDER BY codigo").fetchall()
    unidades = db.execute("SELECT codigo, nome FROM unidades ORDER BY codigo").fetchall()

    return jsonify({
        "status": "ok",
        "terminal": {
            "terminal_id":    terminal_id,
            "apelido":        terminal["apelido"] or terminal_id,
            "setor_codigo":   terminal["setor_codigo"],
            "unidade_codigo": terminal["unidade_codigo"],
        },
        "setores":  [{"codigo": r["codigo"], "nome": r["nome"]} for r in setores],
        "unidades": [{"codigo": r["codigo"], "nome": r["nome"]} for r in unidades],
    })


# ── GET lista — para o dashboard ─────────────────────────────────

@terminais_bp.route("/terminais", methods=["GET"])
def listar_terminais():
    db = get_db()
    rows = db.execute("""
        SELECT t.*,
               s.nome AS setor_nome,
               u.nome AS unidade_nome
        FROM terminais t
        LEFT JOIN setores  s ON s.codigo = t.setor_codigo
        LEFT JOIN unidades u ON u.codigo = t.unidade_codigo
        ORDER BY
            CASE t.status WHEN 'pendente' THEN 0 WHEN 'aprovado' THEN 1 ELSE 2 END,
            t.ultimo_acesso DESC
    """).fetchall()

    return jsonify([{
        "terminal_id":    r["terminal_id"],
        "apelido":        r["apelido"] or r["terminal_id"],
        "status":         r["status"] or "pendente",
        "setor_codigo":   r["setor_codigo"],
        "setor_nome":     r["setor_nome"],
        "unidade_codigo": r["unidade_codigo"],
        "unidade_nome":   r["unidade_nome"],
        "ip_address":     r["ip_address"],
        "firmware_ver":   r["firmware_ver"],
        "ultimo_acesso":  r["ultimo_acesso"],
    } for r in rows])


# ── GET pendentes — badge no dashboard ───────────────────────────

@terminais_bp.route("/terminais/pendentes", methods=["GET"])
def pendentes():
    db = get_db()
    n = db.execute(
        "SELECT COUNT(*) FROM terminais WHERE status='pendente'"
    ).fetchone()[0]
    return jsonify({"total": n})


# ── PUT config — admin configura setor/unidade/apelido ───────────

@terminais_bp.route("/terminal/<terminal_id>/config", methods=["PUT"])
def set_config(terminal_id):
    body           = request.get_json(silent=True) or {}
    setor_codigo   = body.get("setor_codigo")
    unidade_codigo = body.get("unidade_codigo")
    apelido        = body.get("apelido")
    db = get_db()

    db.execute("""
        INSERT INTO terminais (terminal_id, setor_codigo, unidade_codigo, apelido, status)
        VALUES (?, ?, ?, ?, 'aprovado')
        ON CONFLICT(terminal_id) DO UPDATE SET
            setor_codigo   = COALESCE(excluded.setor_codigo,   terminais.setor_codigo),
            unidade_codigo = COALESCE(excluded.unidade_codigo, terminais.unidade_codigo),
            apelido        = COALESCE(excluded.apelido,        terminais.apelido)
    """, (terminal_id, setor_codigo, unidade_codigo, apelido))
    db.commit()
    return jsonify({"status": "ok", "msg": "Configuração salva."})


# ── PUT aprovar ───────────────────────────────────────────────────

@terminais_bp.route("/terminal/<terminal_id>/aprovar", methods=["PUT"])
def aprovar(terminal_id):
    body           = request.get_json(silent=True) or {}
    setor_codigo   = body.get("setor_codigo")
    unidade_codigo = body.get("unidade_codigo")
    apelido        = body.get("apelido")
    db = get_db()

    db.execute("""
        UPDATE terminais SET
            status         = 'aprovado',
            setor_codigo   = COALESCE(?, setor_codigo),
            unidade_codigo = COALESCE(?, unidade_codigo),
            apelido        = COALESCE(?, apelido)
        WHERE terminal_id = ?
    """, (setor_codigo, unidade_codigo, apelido, terminal_id))
    db.commit()
    return jsonify({"status": "ok", "msg": f"Terminal {terminal_id} aprovado."})


# ── PUT rejeitar ──────────────────────────────────────────────────

@terminais_bp.route("/terminal/<terminal_id>/rejeitar", methods=["PUT"])
def rejeitar(terminal_id):
    db = get_db()
    db.execute(
        "UPDATE terminais SET status='rejeitado' WHERE terminal_id=?", (terminal_id,)
    )
    db.commit()
    return jsonify({"status": "ok", "msg": f"Terminal {terminal_id} rejeitado."})


# ── DELETE remove ─────────────────────────────────────────────────

@terminais_bp.route("/terminal/<terminal_id>", methods=["DELETE"])
def remover(terminal_id):
    db = get_db()
    db.execute("DELETE FROM terminais WHERE terminal_id=?", (terminal_id,))
    db.commit()
    return jsonify({"status": "ok", "msg": f"Terminal {terminal_id} removido."})
