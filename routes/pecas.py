"""
routes/pecas.py — VoidLog v2
─────────────────────────────────────────────────────────────────
Peça não tem setor/unidade fixos.
Localização atual é atualizada a cada movimentação.

uid_raw armazena o UID COMPLETO da tag (todos os bytes).
Lookup por uid_raw tem prioridade sobre peca_code.

GET  /api/pecas                → lista todas (filtros: setor, unidade, disponivel)
GET  /api/pecas/<peca_code>    → detalhe de uma peça
POST /api/pecas                → cadastra nova peça
PUT  /api/pecas/<peca_code>    → edita peça
DELETE /api/pecas/<peca_code>  → remove peça
GET  /api/pecas/uid/<uid>      → decodifica bytes de um UID
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, uid_from_parts, UIDParseError

pecas_bp = Blueprint("pecas", __name__)


@pecas_bp.route("/pecas", methods=["GET"])
def listar_pecas():
    setor      = request.args.get("setor")
    unidade    = request.args.get("unidade")
    disponivel = request.args.get("disponivel")

    query = """
        SELECT
            f.*,
            s.nome  AS loc_setor_nome,
            u.nome  AS loc_unidade_nome,
            o.nome  AS ultimo_operador_nome,
            o.matricula AS ultimo_operador_mat
        FROM pecas f
        LEFT JOIN setores    s ON s.codigo = f.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = f.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = f.ultimo_operador_id
        WHERE 1=1
    """
    params = []
    if setor:
        query += " AND f.localizacao_setor = ?";    params.append(int(setor))
    if unidade:
        query += " AND f.localizacao_unidade = ?";  params.append(int(unidade))
    if disponivel is not None:
        query += " AND f.disponivel = ?";           params.append(int(disponivel))

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@pecas_bp.route("/pecas/<int:peca_code>", methods=["GET"])
def detalhe_peca(peca_code):
    row = get_db().execute(
        """SELECT f.*,
                  s.nome  AS loc_setor_nome,
                  u.nome  AS loc_unidade_nome,
                  o.nome  AS ultimo_operador_nome,
                  o.matricula AS ultimo_operador_mat
           FROM pecas f
           LEFT JOIN setores    s ON s.codigo = f.localizacao_setor
           LEFT JOIN unidades   u ON u.codigo = f.localizacao_unidade
           LEFT JOIN operadores o ON o.id     = f.ultimo_operador_id
           WHERE f.peca_code = ?""",
        (peca_code,)
    ).fetchone()
    if not row:
        return jsonify({"erro": "Peça não encontrada"}), 404
    return jsonify(dict(row))


@pecas_bp.route("/pecas", methods=["POST"])
def cadastrar_peca():
    """
    Payload v2:
    {
        "nome":       "Furadeira de Bancada",
        "categoria":  "Furação",
        "peca_code":  100,
        "quantidade": 3,
        "uid_raw":    "04A3F21B7C8D90"   ← opcional: UID COMPLETO da tag RFID.
                                            Se omitido, gerado como B1B2 (hex de peca_code).
    }

    uid_raw pode ser qualquer comprimento válido de UID RFID
    (4, 7 ou 10 bytes = 8, 14 ou 20 chars hex).
    Quando fornecido, é usado como identificador primário de lookup
    (permite distinguir tags com mesmo B1+B2 de fabricantes diferentes).
    """
    data = request.get_json(silent=True) or {}
    for campo in ["nome", "categoria", "peca_code"]:
        if campo not in data:
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    peca_code = data["peca_code"]

    # uid_raw: usa o UID completo fornecido ou gera a partir do peca_code
    if "uid_raw" in data and data["uid_raw"]:
        try:
            parsed = parse_uid(data["uid_raw"])
            uid_raw = parsed["uid_raw"]
        except UIDParseError as e:
            return jsonify({"erro": str(e)}), 422
    else:
        b1 = (peca_code >> 8) & 0xFF
        b2 = peca_code & 0xFF
        uid_raw = f"{b1:02X}{b2:02X}"

    db = get_db()
    try:
        db.execute(
            """INSERT INTO pecas (peca_code, uid_raw, nome, categoria, quantidade)
               VALUES (?,?,?,?,?)""",
            (peca_code, uid_raw, data["nome"], data["categoria"], data.get("quantidade", 1))
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({
        "mensagem":   "Peça cadastrada com sucesso",
        "peca_code":  peca_code,
        "uid_raw":    uid_raw,
        "nota":       "uid_raw completo usado como identificador primário da tag RFID",
    }), 201


@pecas_bp.route("/pecas/<int:peca_code>", methods=["PUT"])
def editar_peca(peca_code):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    row  = db.execute("SELECT * FROM pecas WHERE peca_code=?", (peca_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Peça não encontrada"}), 404

    campos, valores = [], []
    for campo in ["nome", "categoria", "quantidade"]:
        if campo in data:
            campos.append(f"{campo} = ?"); valores.append(data[campo])
    if "disponivel" in data:
        campos.append("disponivel = ?"); valores.append(1 if data["disponivel"] else 0)
    if "uid_raw" in data and data["uid_raw"]:
        try:
            parsed = parse_uid(data["uid_raw"])
            campos.append("uid_raw = ?"); valores.append(parsed["uid_raw"])
        except UIDParseError as e:
            return jsonify({"erro": str(e)}), 422

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400

    valores.append(peca_code)
    db.execute(f"UPDATE pecas SET {', '.join(campos)} WHERE peca_code=?", valores)
    db.commit()
    return jsonify({"ok": True, "mensagem": "Peça atualizada"})


@pecas_bp.route("/pecas/<int:peca_code>", methods=["DELETE"])
def deletar_peca(peca_code):
    db  = get_db()
    row = db.execute("SELECT * FROM pecas WHERE peca_code=?", (peca_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Peça não encontrada"}), 404

    mov = db.execute(
        "SELECT COUNT(*) as n FROM movimentacoes WHERE peca_peca=?", (peca_code,)
    ).fetchone()
    if mov["n"] > 0:
        return jsonify({"erro": f"Peça possui {mov['n']} movimentação(ões). Não é possível remover."}), 409

    db.execute("DELETE FROM pecas WHERE peca_code=?", (peca_code,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Peça removida"})


@pecas_bp.route("/pecas/uid/<string:uid>", methods=["GET"])
def decodificar_uid(uid):
    try:
        parsed = parse_uid(uid)
    except UIDParseError as e:
        return jsonify({"erro": str(e)}), 422
    return jsonify(parsed)
