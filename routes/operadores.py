"""
routes/operadores.py
─────────────────────────────────────────────────────────────────
GET    /api/operadores          → lista todos
POST   /api/operadores          → cadastra novo operador (crachá RFID)
DELETE /api/operadores/<id>     → remove operador
GET    /api/operadores/ativos   → operadores com sessão ativa agora
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, UIDParseError

operadores_bp = Blueprint("operadores", __name__)


@operadores_bp.route("/operadores", methods=["GET"])
def listar_operadores():
    rows = get_db().execute(
        """SELECT o.*, s.nome AS setor_nome, u.nome AS unidade_nome
           FROM operadores o
           JOIN setores  s ON s.codigo = o.setor_codigo
           JOIN unidades u ON u.codigo = o.unidade_codigo
           ORDER BY o.nome"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@operadores_bp.route("/operadores", methods=["POST"])
def cadastrar_operador():
    """
    Payload:
    {
        "uid_raw":   "A34F0302",
        "nome":      "João Silva",
        "matricula": "TS-0042"
    }
    O setor e a unidade são extraídos automaticamente dos bytes B3 e B4 do UID.
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
            """INSERT INTO operadores
                   (uid_raw, peca_code, setor_codigo, unidade_codigo, nome, matricula)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                uid["uid_raw"],
                uid["peca_code"],
                uid["setor_code"],
                uid["unidade_code"],
                data["nome"],
                data["matricula"],
            )
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({
        "mensagem":  "Operador cadastrado com sucesso",
        "operador":  data["nome"],
        "matricula": data["matricula"],
        "uid_breakdown": {
            "B1+B2 (id cracha)": f"{uid['b1']} {uid['b2']} → {uid['peca_code']}",
            "B3 (setor)":        f"{uid['b3']} → {uid['setor_nome']}",
            "B4 (unidade)":      f"{uid['b4']} → {uid['unidade_nome']}",
        }
    }), 201


@operadores_bp.route("/operadores/<int:op_id>", methods=["DELETE"])
def deletar_operador(op_id):
    db = get_db()
    row = db.execute("SELECT * FROM operadores WHERE id = ?", (op_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Operador não encontrado"}), 404

    # Encerra sessões ativas primeiro
    db.execute("UPDATE sessoes SET ativa = 0 WHERE operador_id = ?", (op_id,))

    # Verifica movimentações
    mov = db.execute(
        "SELECT COUNT(*) as n FROM movimentacoes WHERE operador_id = ?", (op_id,)
    ).fetchone()
    if mov["n"] > 0:
        return jsonify({
            "erro": f"Operador possui {mov['n']} movimentação(ões). Não é possível remover."
        }), 409

    db.execute("DELETE FROM operadores WHERE id = ?", (op_id,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Operador removido"})


@operadores_bp.route("/operadores/ativos", methods=["GET"])
def operadores_ativos():
    rows = get_db().execute(
        """SELECT o.nome, o.matricula, s.nome AS setor, u.nome AS unidade,
                  sess.inicio
           FROM sessoes sess
           JOIN operadores o ON o.id    = sess.operador_id
           JOIN setores    s ON s.codigo = sess.setor_codigo
           JOIN unidades   u ON u.codigo = sess.unidade_codigo
           WHERE sess.ativa = 1
           ORDER BY sess.inicio DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])
