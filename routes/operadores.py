"""
routes/operadores.py — VoidLog v2
─────────────────────────────────────────────────────────────────
Operador não tem setor/unidade fixos.
uid_raw armazena o UID COMPLETO do crachá (todos os bytes).
Lookup por uid_raw completo tem prioridade sobre peca_code.

GET    /api/operadores        → lista todos
POST   /api/operadores        → cadastra novo operador
DELETE /api/operadores/<id>   → remove operador
GET    /api/operadores/ativos → sessões abertas agora
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, UIDParseError

operadores_bp = Blueprint("operadores", __name__)


@operadores_bp.route("/operadores", methods=["GET"])
def listar_operadores():
    rows = get_db().execute(
        "SELECT id, uid_raw, peca_code, nome, matricula FROM operadores ORDER BY nome"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@operadores_bp.route("/operadores", methods=["POST"])
def cadastrar_operador():
    """
    Payload v2:
    {
        "uid_raw":   "04A3F21B7C8D90",  ← UID COMPLETO do crachá (todos os bytes)
        "nome":      "João Silva",
        "matricula": "TS-0042"
    }

    uid_raw deve ser o UID completo lido pelo RC522 (8, 14 ou 20 chars hex
    para tags de 4, 7 ou 10 bytes respectivamente).
    peca_code (B1+B2) é extraído automaticamente do uid_raw.
    Setor e unidade não são necessários no cadastro.
    """
    data = request.get_json(silent=True) or {}
    for campo in ["uid_raw", "nome", "matricula"]:
        if campo not in data:
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    try:
        uid = parse_uid(data["uid_raw"])
    except UIDParseError as e:
        return jsonify({"erro": str(e)}), 422

    db = get_db()
    try:
        db.execute(
            "INSERT INTO operadores (uid_raw, peca_code, nome, matricula) VALUES (?,?,?,?)",
            (uid["uid_raw"], uid["peca_code"], data["nome"], data["matricula"])
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({
        "mensagem":  "Operador cadastrado com sucesso",
        "operador":  data["nome"],
        "matricula": data["matricula"],
        "peca_code": uid["peca_code"],
        "uid_raw":   uid["uid_raw"],
        "num_bytes": uid["num_bytes"],
    }), 201


@operadores_bp.route("/operadores/<int:op_id>", methods=["DELETE"])
def deletar_operador(op_id):
    db  = get_db()
    row = db.execute("SELECT * FROM operadores WHERE id=?", (op_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Operador não encontrado"}), 404

    mov = db.execute(
        "SELECT COUNT(*) as n FROM movimentacoes WHERE operador_id=?", (op_id,)
    ).fetchone()
    if mov["n"] > 0:
        return jsonify({"erro": f"Operador possui {mov['n']} movimentação(ões). Não é possível remover."}), 409

    db.execute("UPDATE sessoes SET ativa=0 WHERE operador_id=?", (op_id,))
    db.execute("DELETE FROM operadores WHERE id=?", (op_id,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Operador removido"})


@operadores_bp.route("/operadores/ativos", methods=["GET"])
def operadores_ativos():
    rows = get_db().execute(
        """SELECT o.nome, o.matricula,
                  s.nome AS setor, u.nome AS unidade,
                  sess.inicio, sess.terminal_id
           FROM sessoes sess
           JOIN operadores o ON o.id     = sess.operador_id
           JOIN setores    s ON s.codigo = sess.setor_codigo
           JOIN unidades   u ON u.codigo = sess.unidade_codigo
           WHERE sess.ativa=1
           ORDER BY sess.inicio DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])
