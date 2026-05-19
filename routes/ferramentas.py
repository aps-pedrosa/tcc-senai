"""
routes/ferramentas.py
─────────────────────────────────────────────────────────────────
GET    /api/ferramentas                 → lista todas
GET    /api/ferramentas/<peca_code>     → detalhe de uma
POST   /api/ferramentas                 → cadastra nova
PUT    /api/ferramentas/<peca_code>     → edita ferramenta
DELETE /api/ferramentas/<peca_code>     → remove ferramenta
GET    /api/ferramentas/uid/<uid>       → decodifica UID
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, uid_from_parts, UIDParseError

ferramentas_bp = Blueprint("ferramentas", __name__)


@ferramentas_bp.route("/ferramentas", methods=["GET"])
def listar_ferramentas():
    setor      = request.args.get("setor")
    unidade    = request.args.get("unidade")
    disponivel = request.args.get("disponivel")

    query = """
        SELECT f.*, s.nome as setor_nome, u.nome as unidade_nome
        FROM ferramentas f
        JOIN setores  s ON s.codigo = f.setor_codigo
        JOIN unidades u ON u.codigo = f.unidade_codigo
        WHERE 1=1
    """
    params = []
    if setor:
        query += " AND f.setor_codigo = ?"; params.append(int(setor))
    if unidade:
        query += " AND f.unidade_codigo = ?"; params.append(int(unidade))
    if disponivel is not None:
        query += " AND f.disponivel = ?"; params.append(int(disponivel))

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@ferramentas_bp.route("/ferramentas/<int:peca_code>", methods=["GET"])
def detalhe_ferramenta(peca_code):
    row = get_db().execute(
        """SELECT f.*, s.nome as setor_nome, u.nome as unidade_nome
           FROM ferramentas f
           JOIN setores  s ON s.codigo = f.setor_codigo
           JOIN unidades u ON u.codigo = f.unidade_codigo
           WHERE f.peca_code = ?""",
        (peca_code,)
    ).fetchone()
    if not row:
        return jsonify({"erro": "Ferramenta não encontrada"}), 404
    return jsonify(dict(row))


@ferramentas_bp.route("/ferramentas", methods=["POST"])
def cadastrar_ferramenta():
    """
    Payload:
    {
        "nome":            "Furadeira de Bancada",
        "categoria":       "Furação",
        "peca_code":       100,
        "setor_codigo":    4,
        "unidade_codigo":  2,
        "quantidade":      3
    }
    """
    data = request.get_json(silent=True) or {}
    required = ["nome", "categoria", "peca_code", "setor_codigo", "unidade_codigo"]
    for campo in required:
        if campo not in data:
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    try:
        uid_raw = uid_from_parts(data["peca_code"], data["setor_codigo"], data["unidade_codigo"])
    except UIDParseError as e:
        return jsonify({"erro": str(e)}), 422

    db = get_db()
    try:
        db.execute(
            """INSERT INTO ferramentas
                   (peca_code, uid_raw, nome, categoria,
                    setor_codigo, unidade_codigo, quantidade)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data["peca_code"], uid_raw,
                data["nome"], data["categoria"],
                data["setor_codigo"], data["unidade_codigo"],
                data.get("quantidade", 1),
            )
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({
        "mensagem":      "Ferramenta cadastrada com sucesso",
        "peca_code":     data["peca_code"],
        "uid_gerado":    uid_raw,
        "uid_breakdown": {
            "B1+B2 (peca)":  f"{uid_raw[0:4]} → {data['peca_code']}",
            "B3 (setor)":    f"{uid_raw[4:6]} → setor {data['setor_codigo']}",
            "B4 (unidade)":  f"{uid_raw[6:8]} → unidade {data['unidade_codigo']}",
        }
    }), 201


@ferramentas_bp.route("/ferramentas/<int:peca_code>", methods=["PUT"])
def editar_ferramenta(peca_code):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM ferramentas WHERE peca_code = ?", (peca_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Ferramenta não encontrada"}), 404

    campos, valores = [], []
    for campo in ["nome", "categoria", "quantidade"]:
        if campo in data:
            campos.append(f"{campo} = ?"); valores.append(data[campo])
    if "disponivel" in data:
        campos.append("disponivel = ?"); valores.append(1 if data["disponivel"] else 0)

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400

    valores.append(peca_code)
    db.execute(f"UPDATE ferramentas SET {', '.join(campos)} WHERE peca_code = ?", valores)
    db.commit()
    return jsonify({"ok": True, "mensagem": "Ferramenta atualizada"})


@ferramentas_bp.route("/ferramentas/<int:peca_code>", methods=["DELETE"])
def deletar_ferramenta(peca_code):
    db = get_db()
    row = db.execute("SELECT * FROM ferramentas WHERE peca_code = ?", (peca_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Ferramenta não encontrada"}), 404

    # Verifica se há movimentações vinculadas
    mov = db.execute(
        "SELECT COUNT(*) as n FROM movimentacoes WHERE ferramenta_peca = ?", (peca_code,)
    ).fetchone()
    if mov["n"] > 0:
        return jsonify({
            "erro": f"Ferramenta possui {mov['n']} movimentação(ões) registrada(s). Remova-as primeiro ou desative a ferramenta."
        }), 409

    db.execute("DELETE FROM ferramentas WHERE peca_code = ?", (peca_code,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Ferramenta removida"})


@ferramentas_bp.route("/ferramentas/uid/<string:uid>", methods=["GET"])
def decodificar_uid(uid):
    try:
        parsed = parse_uid(uid)
    except UIDParseError as e:
        return jsonify({"erro": str(e)}), 422
    return jsonify(parsed)
