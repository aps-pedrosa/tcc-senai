"""
routes/equipamentos.py — VoidLog v3
GET  /api/equipamentos                → lista todos (filtros: setor, unidade, disponivel, nome, categoria, uid)
GET  /api/equipamentos/<code>         → detalhe
POST /api/equipamentos                → cadastra
PUT  /api/equipamentos/<code>         → edita
DELETE /api/equipamentos/<code>       → remove
GET  /api/equipamentos/categorias     → lista categorias
GET  /api/equipamentos/uid/<uid>      → decodifica UID
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, uid_from_parts, UIDParseError

equipamentos_bp = Blueprint("equipamentos", __name__)


@equipamentos_bp.route("/equipamentos/categorias", methods=["GET"])
def listar_categorias():
    rows = get_db().execute(
        "SELECT DISTINCT categoria FROM equipamentos WHERE categoria IS NOT NULL ORDER BY categoria"
    ).fetchall()
    return jsonify([r["categoria"] for r in rows])


@equipamentos_bp.route("/equipamentos", methods=["GET"])
def listar_equipamentos():
    setor      = request.args.get("setor")
    unidade    = request.args.get("unidade")
    disponivel = request.args.get("disponivel")
    nome       = request.args.get("nome", "").strip()
    categoria  = request.args.get("categoria", "").strip()
    uid_q      = request.args.get("uid", "").strip().upper()
    manutencao = request.args.get("em_manutencao")

    query = """
        SELECT
            e.*,
            s.nome  AS loc_setor_nome,
            u.nome  AS loc_unidade_nome,
            o.nome  AS ultimo_operador_nome,
            o.matricula AS ultimo_operador_mat
        FROM equipamentos e
        LEFT JOIN setores    s ON s.codigo = e.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = e.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = e.ultimo_operador_id
        WHERE 1=1
    """
    params = []
    if setor:
        query += " AND e.localizacao_setor = ?";    params.append(int(setor))
    if unidade:
        query += " AND e.localizacao_unidade = ?";  params.append(int(unidade))
    if disponivel is not None and disponivel != "":
        query += " AND e.disponivel = ?";           params.append(int(disponivel))
    if nome:
        query += " AND LOWER(e.nome) LIKE ?";       params.append(f"%{nome.lower()}%")
    if categoria:
        query += " AND LOWER(e.categoria) LIKE ?";  params.append(f"%{categoria.lower()}%")
    if uid_q:
        query += " AND UPPER(e.uid_raw) LIKE ?";    params.append(f"%{uid_q}%")
    if manutencao is not None and manutencao != "":
        query += " AND e.em_manutencao = ?";        params.append(int(manutencao))

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@equipamentos_bp.route("/equipamentos/<int:equipamento_code>", methods=["GET"])
def detalhe_equipamento(equipamento_code):
    row = get_db().execute(
        """SELECT e.*,
                  s.nome  AS loc_setor_nome,
                  u.nome  AS loc_unidade_nome,
                  o.nome  AS ultimo_operador_nome,
                  o.matricula AS ultimo_operador_mat
           FROM equipamentos e
           LEFT JOIN setores    s ON s.codigo = e.localizacao_setor
           LEFT JOIN unidades   u ON u.codigo = e.localizacao_unidade
           LEFT JOIN operadores o ON o.id     = e.ultimo_operador_id
           WHERE e.equipamento_code = ?""",
        (equipamento_code,)
    ).fetchone()
    if not row:
        return jsonify({"erro": "Equipamento não encontrado"}), 404
    return jsonify(dict(row))


@equipamentos_bp.route("/equipamentos", methods=["POST"])
def cadastrar_equipamento():
    data = request.get_json(silent=True) or {}
    for campo in ["nome", "categoria", "equipamento_code"]:
        if campo not in data:
            # Compatibilidade: aceita peca_code também
            if campo == "equipamento_code" and "peca_code" in data:
                data["equipamento_code"] = data["peca_code"]
            else:
                return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    equipamento_code = data["equipamento_code"]

    if "uid_raw" in data and data["uid_raw"]:
        try:
            parsed = parse_uid(data["uid_raw"])
            uid_raw = parsed["uid_raw"]
        except UIDParseError as e:
            return jsonify({"erro": str(e)}), 422
    else:
        b1 = (equipamento_code >> 8) & 0xFF
        b2 = equipamento_code & 0xFF
        uid_raw = f"{b1:02X}{b2:02X}"

    db = get_db()
    try:
        db.execute(
            """INSERT INTO equipamentos
               (equipamento_code, uid_raw, nome, categoria, descricao, quantidade, peso)
               VALUES (?,?,?,?,?,?,?)""",
            (equipamento_code, uid_raw, data["nome"], data["categoria"],
             data.get("descricao"), data.get("quantidade", 1), data.get("peso"))
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({
        "mensagem":          "Equipamento cadastrado com sucesso",
        "equipamento_code":  equipamento_code,
        "uid_raw":           uid_raw,
    }), 201


@equipamentos_bp.route("/equipamentos/<int:equipamento_code>", methods=["PUT"])
def editar_equipamento(equipamento_code):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    row  = db.execute("SELECT * FROM equipamentos WHERE equipamento_code=?", (equipamento_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Equipamento não encontrado"}), 404

    campos, valores = [], []
    for campo in ["nome", "categoria", "descricao", "quantidade", "peso"]:
        if campo in data:
            campos.append(f"{campo} = ?"); valores.append(data[campo])
    if "disponivel" in data:
        campos.append("disponivel = ?"); valores.append(1 if data["disponivel"] else 0)
    if "em_manutencao" in data:
        campos.append("em_manutencao = ?"); valores.append(1 if data["em_manutencao"] else 0)
    if "uid_raw" in data and data["uid_raw"]:
        try:
            parsed = parse_uid(data["uid_raw"])
            campos.append("uid_raw = ?"); valores.append(parsed["uid_raw"])
        except UIDParseError as e:
            return jsonify({"erro": str(e)}), 422

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400

    valores.append(equipamento_code)
    db.execute(f"UPDATE equipamentos SET {', '.join(campos)} WHERE equipamento_code=?", valores)
    db.commit()
    return jsonify({"ok": True, "mensagem": "Equipamento atualizado"})


@equipamentos_bp.route("/equipamentos/<int:equipamento_code>", methods=["DELETE"])
def deletar_equipamento(equipamento_code):
    db  = get_db()
    row = db.execute("SELECT * FROM equipamentos WHERE equipamento_code=?", (equipamento_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Equipamento não encontrado"}), 404

    mov = db.execute(
        "SELECT COUNT(*) as n FROM movimentacoes WHERE equipamento_code=?", (equipamento_code,)
    ).fetchone()
    if mov["n"] > 0:
        return jsonify({"erro": f"Equipamento possui {mov['n']} movimentação(ões). Não é possível remover."}), 409

    db.execute("DELETE FROM equipamentos WHERE equipamento_code=?", (equipamento_code,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Equipamento removido"})


@equipamentos_bp.route("/equipamentos/uid/<string:uid>", methods=["GET"])
def decodificar_uid(uid):
    try:
        parsed = parse_uid(uid)
    except UIDParseError as e:
        return jsonify({"erro": str(e)}), 422
    return jsonify(parsed)


# ── Rotas de compatibilidade /api/pecas → /api/equipamentos ──────────────
pecas_compat_bp = Blueprint("pecas_compat", __name__)

@pecas_compat_bp.route("/pecas/categorias", methods=["GET"])
def compat_categorias():
    return listar_categorias()

@pecas_compat_bp.route("/pecas", methods=["GET"])
def compat_listar():
    return listar_equipamentos()

@pecas_compat_bp.route("/pecas/<int:code>", methods=["GET"])
def compat_detalhe(code):
    return detalhe_equipamento(code)

@pecas_compat_bp.route("/pecas", methods=["POST"])
def compat_cadastrar():
    return cadastrar_equipamento()

@pecas_compat_bp.route("/pecas/<int:code>", methods=["PUT"])
def compat_editar(code):
    return editar_equipamento(code)

@pecas_compat_bp.route("/pecas/<int:code>", methods=["DELETE"])
def compat_deletar(code):
    return deletar_equipamento(code)

@pecas_compat_bp.route("/pecas/uid/<string:uid>", methods=["GET"])
def compat_uid(uid):
    return decodificar_uid(uid)
