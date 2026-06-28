"""
routes/operadores.py — VoidLog v3
GET    /api/operadores        → lista (filtros: nome, matricula, uid)
POST   /api/operadores        → cadastra
PUT    /api/operadores/<id>   → edita
DELETE /api/operadores/<id>   → remove
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, UIDParseError

operadores_bp = Blueprint("operadores", __name__)


@operadores_bp.route("/operadores", methods=["GET"])
def listar_operadores():
    nome_q  = request.args.get("nome", "").strip()
    mat_q   = request.args.get("matricula", "").strip()
    uid_q   = request.args.get("uid", "").strip().upper()

    query = """
        SELECT o.*, e.nome AS equipamento_nome, e.categoria AS equipamento_categoria
        FROM operadores o
        LEFT JOIN equipamentos e ON e.equipamento_code = o.equipamento_code
        WHERE 1=1
    """
    params = []
    if nome_q:
        query += " AND LOWER(o.nome) LIKE ?";    params.append(f"%{nome_q.lower()}%")
    if mat_q:
        query += " AND LOWER(o.matricula) LIKE ?"; params.append(f"%{mat_q.lower()}%")
    if uid_q:
        query += " AND UPPER(o.uid_raw) LIKE ?";  params.append(f"%{uid_q}%")
    query += " ORDER BY o.nome"

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@operadores_bp.route("/operadores", methods=["POST"])
def cadastrar_operador():
    data = request.get_json(silent=True) or {}
    for campo in ["nome", "matricula", "uid_raw", "equipamento_code"]:
        if campo not in data or str(data[campo]).strip() == "":
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    try:
        parsed = parse_uid(data["uid_raw"])
        uid_raw = parsed["uid_raw"]
    except UIDParseError as e:
        return jsonify({"erro": str(e)}), 422

    db = get_db()
    try:
        db.execute(
            "INSERT INTO operadores (uid_raw, equipamento_code, nome, matricula) VALUES (?,?,?,?)",
            (uid_raw, int(data["equipamento_code"]), data["nome"].strip(), data["matricula"].strip())
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({"mensagem": "Operador cadastrado com sucesso"}), 201


@operadores_bp.route("/operadores/<int:operador_id>", methods=["PUT"])
def editar_operador(operador_id):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    row  = db.execute("SELECT * FROM operadores WHERE id=?", (operador_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Operador não encontrado"}), 404

    campos, valores = [], []
    for campo in ["nome", "matricula", "equipamento_code"]:
        if campo in data:
            campos.append(f"{campo}=?"); valores.append(data[campo])
    if "uid_raw" in data:
        try:
            parsed = parse_uid(data["uid_raw"])
            campos.append("uid_raw=?"); valores.append(parsed["uid_raw"])
        except UIDParseError as e:
            return jsonify({"erro": str(e)}), 422

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400

    valores.append(operador_id)
    db.execute(f"UPDATE operadores SET {', '.join(campos)} WHERE id=?", valores)
    db.commit()
    return jsonify({"ok": True, "mensagem": "Operador atualizado"})


@operadores_bp.route("/operadores/<int:operador_id>", methods=["DELETE"])
def deletar_operador(operador_id):
    db  = get_db()
    row = db.execute("SELECT * FROM operadores WHERE id=?", (operador_id,)).fetchone()
    if not row:
        return jsonify({"erro": "Operador não encontrado"}), 404

    mov = db.execute(
        "SELECT COUNT(*) as n FROM movimentacoes WHERE operador_id=?", (operador_id,)
    ).fetchone()
    if mov["n"] > 0:
        return jsonify({"erro": f"Operador possui {mov['n']} movimentação(ões). Não é possível remover."}), 409

    db.execute("DELETE FROM operadores WHERE id=?", (operador_id,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Operador removido"})
