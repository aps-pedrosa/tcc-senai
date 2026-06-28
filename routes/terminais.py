"""
routes/terminais.py — VoidLog v3
GET    /api/terminais              → lista todos
GET    /api/terminais/pendentes    → lista pendentes
POST   /api/terminais/registro     → ESP registra (pelo MAC)
POST   /api/terminais/<tid>/aprovar
POST   /api/terminais/<tid>/rejeitar
PUT    /api/terminais/<tid>        → edita (apelido, tipo, setor, unidade)
DELETE /api/terminais/<tid>        → remove
GET    /api/terminais/descobrir    → ESP pergunta se servidor reconhece ele (por MAC)
"""

from flask import Blueprint, request, jsonify
from database import get_db
from datetime import datetime

terminais_bp = Blueprint("terminais", __name__)


@terminais_bp.route("/terminais", methods=["GET"])
def listar_terminais():
    rows = get_db().execute("""
        SELECT t.*,
               s.nome AS setor_nome,
               u.nome AS unidade_nome
        FROM terminais t
        LEFT JOIN setores  s ON s.codigo = t.setor_codigo
        LEFT JOIN unidades u ON u.codigo = t.unidade_codigo
        ORDER BY t.ultimo_acesso DESC
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@terminais_bp.route("/terminais/pendentes", methods=["GET"])
def listar_pendentes():
    rows = get_db().execute(
        "SELECT * FROM terminais WHERE status='pendente' ORDER BY ultimo_acesso DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@terminais_bp.route("/terminais/registro", methods=["POST"])
def registrar_terminal():
    """
    ESP32 chama este endpoint ao ligar.
    Payload: { terminal_id: "<MAC>", firmware_ver: "3.0", tipo: "normal"|"manutencao" }
    Retorna: { status: "aprovado"|"pendente"|"rejeitado", setor, unidade }
    """
    data = request.get_json(silent=True) or {}
    terminal_id = (data.get("terminal_id") or "").upper().strip()
    if not terminal_id:
        return jsonify({"erro": "terminal_id (MAC) obrigatório"}), 400

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    tipo = data.get("tipo", "normal")
    if tipo not in ("normal", "manutencao"):
        tipo = "normal"

    db = get_db()
    row = db.execute("SELECT * FROM terminais WHERE terminal_id=?", (terminal_id,)).fetchone()

    if row:
        db.execute(
            "UPDATE terminais SET ultimo_acesso=?, ip_address=?, firmware_ver=? WHERE terminal_id=?",
            (datetime.now().isoformat(), ip, data.get("firmware_ver", "3.0"), terminal_id)
        )
        db.commit()
        return jsonify({
            "status":   row["status"],
            "tipo":     row["tipo"],
            "setor":    row["setor_codigo"],
            "unidade":  row["unidade_codigo"],
            "apelido":  row["apelido"] or terminal_id,
        })
    else:
        db.execute("""
            INSERT INTO terminais (terminal_id, tipo, status, ip_address, firmware_ver)
            VALUES (?,?,?,?,?)
        """, (terminal_id, tipo, "pendente", ip, data.get("firmware_ver", "3.0")))
        db.commit()
        return jsonify({
            "status":  "pendente",
            "tipo":    tipo,
            "setor":   None,
            "unidade": None,
            "apelido": terminal_id,
        }), 202


@terminais_bp.route("/terminais/descobrir", methods=["GET"])
def descobrir_servidor():
    """
    ESP32 faz GET /api/terminais/descobrir?mac=XX:XX:XX:XX:XX:XX
    para confirmar que achou o servidor certo.
    """
    mac = (request.args.get("mac") or "").upper().strip()
    if not mac:
        return jsonify({"ok": True, "servidor": "voidlog", "versao": "3.0"})
    db = get_db()
    row = db.execute("SELECT * FROM terminais WHERE terminal_id=?", (mac,)).fetchone()
    return jsonify({
        "ok":      True,
        "servidor": "voidlog",
        "versao":  "3.0",
        "mac":     mac,
        "status":  row["status"] if row else "desconhecido",
    })


@terminais_bp.route("/terminais/<string:terminal_id>/aprovar", methods=["POST"])
def aprovar_terminal(terminal_id):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    row  = db.execute("SELECT * FROM terminais WHERE terminal_id=?", (terminal_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Terminal não encontrado"}), 404

    campos = ["status='aprovado'"]
    valores = []
    if data.get("setor"):
        campos.append("setor_codigo=?");  valores.append(int(data["setor"]))
    if data.get("unidade"):
        campos.append("unidade_codigo=?"); valores.append(int(data["unidade"]))
    if data.get("apelido"):
        campos.append("apelido=?");        valores.append(data["apelido"])
    if data.get("tipo") in ("normal", "manutencao"):
        campos.append("tipo=?");           valores.append(data["tipo"])

    valores.append(terminal_id)
    db.execute(f"UPDATE terminais SET {', '.join(campos)} WHERE terminal_id=?", valores)
    db.commit()
    return jsonify({"ok": True, "mensagem": "Terminal aprovado"})


@terminais_bp.route("/terminais/<string:terminal_id>/rejeitar", methods=["POST"])
def rejeitar_terminal(terminal_id):
    db = get_db()
    row = db.execute("SELECT * FROM terminais WHERE terminal_id=?", (terminal_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Terminal não encontrado"}), 404
    db.execute("UPDATE terminais SET status='rejeitado' WHERE terminal_id=?", (terminal_id,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Terminal rejeitado"})


@terminais_bp.route("/terminais/<string:terminal_id>", methods=["PUT"])
def editar_terminal(terminal_id):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    row  = db.execute("SELECT * FROM terminais WHERE terminal_id=?", (terminal_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Terminal não encontrado"}), 404

    campos, valores = [], []
    if "apelido" in data:
        campos.append("apelido=?");        valores.append(data["apelido"])
    if "tipo" in data and data["tipo"] in ("normal", "manutencao"):
        campos.append("tipo=?");           valores.append(data["tipo"])
    if "setor" in data:
        campos.append("setor_codigo=?");   valores.append(int(data["setor"]) if data["setor"] else None)
    if "unidade" in data:
        campos.append("unidade_codigo=?"); valores.append(int(data["unidade"]) if data["unidade"] else None)
    if "status" in data and data["status"] in ("aprovado", "rejeitado", "pendente"):
        campos.append("status=?");         valores.append(data["status"])

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400
    valores.append(terminal_id)
    db.execute(f"UPDATE terminais SET {', '.join(campos)} WHERE terminal_id=?", valores)
    db.commit()
    return jsonify({"ok": True})


@terminais_bp.route("/terminais/<string:terminal_id>", methods=["DELETE"])
def deletar_terminal(terminal_id):
    db = get_db()
    db.execute("DELETE FROM terminais WHERE terminal_id=?", (terminal_id,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Terminal removido"})
