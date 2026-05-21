"""
routes/movimentacoes.py — VoidLog v2
─────────────────────────────────────────────────────────────────
Histórico agora inclui terminal_id e localização no momento da leitura.
Dashboard mostra localização atual das pecas.
"""

from flask import Blueprint, request, jsonify
from database import get_db

mov_bp = Blueprint("movimentacoes", __name__)


@mov_bp.route("/movimentacoes", methods=["GET"])
def listar_movimentacoes():
    setor    = request.args.get("setor")
    unidade  = request.args.get("unidade")
    tipo     = request.args.get("tipo")
    data_ini = request.args.get("data_ini")
    data_fim = request.args.get("data_fim")
    limit    = int(request.args.get("limit", 100))

    query = """
        SELECT
            m.id, m.tipo, m.horario, m.terminal_id,
            f.nome        AS peca,
            f.categoria,
            f.uid_raw,
            f.peca_code,
            o.nome        AS operador,
            o.matricula,
            s.nome        AS setor,
            u.nome        AS unidade
        FROM movimentacoes m
        JOIN pecas f ON f.peca_code  = m.peca_peca
        JOIN operadores  o ON o.id         = m.operador_id
        JOIN setores     s ON s.codigo     = m.setor_codigo
        JOIN unidades    u ON u.codigo     = m.unidade_codigo
        WHERE 1=1
    """
    params = []
    if setor:    query += " AND m.setor_codigo=?";    params.append(int(setor))
    if unidade:  query += " AND m.unidade_codigo=?";  params.append(int(unidade))
    if tipo:     query += " AND m.tipo=?";            params.append(tipo)
    if data_ini: query += " AND DATE(m.horario)>=?";  params.append(data_ini)
    if data_fim: query += " AND DATE(m.horario)<=?";  params.append(data_fim)

    query += " ORDER BY m.horario DESC LIMIT ?"
    params.append(limit)

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@mov_bp.route("/dashboard/dados", methods=["GET"])
def dados_dashboard():
    setor   = request.args.get("setor")
    unidade = request.args.get("unidade")
    db      = get_db()

    f, fp = "", []
    if setor:   f += " AND m.setor_codigo=?";   fp.append(int(setor))
    if unidade: f += " AND m.unidade_codigo=?";  fp.append(int(unidade))

    totais = db.execute(f"""
        SELECT
            COUNT(*)                                            AS total_movimentacoes,
            SUM(CASE WHEN tipo='retirada'  THEN 1 ELSE 0 END) AS total_retiradas,
            SUM(CASE WHEN tipo='devolucao' THEN 1 ELSE 0 END) AS total_devolucoes
        FROM movimentacoes m WHERE 1=1 {f}
    """, fp).fetchone()

    top_pecas = db.execute(f"""
        SELECT f.nome, f.categoria, COUNT(*) AS usos
        FROM movimentacoes m
        JOIN pecas f ON f.peca_code = m.peca_peca
        WHERE m.tipo='retirada' {f}
        GROUP BY m.peca_peca ORDER BY usos DESC LIMIT 10
    """, fp).fetchall()

    por_setor = db.execute(f"""
        SELECT s.nome AS setor, s.codigo, COUNT(*) AS movimentacoes
        FROM movimentacoes m JOIN setores s ON s.codigo=m.setor_codigo
        WHERE 1=1 {f} GROUP BY m.setor_codigo ORDER BY movimentacoes DESC
    """, fp).fetchall()

    por_unidade = db.execute(f"""
        SELECT u.nome AS unidade, u.codigo, COUNT(*) AS movimentacoes
        FROM movimentacoes m JOIN unidades u ON u.codigo=m.unidade_codigo
        WHERE 1=1 {f} GROUP BY m.unidade_codigo ORDER BY movimentacoes DESC
    """, fp).fetchall()

    por_dia = db.execute(f"""
        SELECT DATE(m.horario) AS dia, COUNT(*) AS total
        FROM movimentacoes m
        WHERE m.horario >= DATE('now','-30 days') {f}
        GROUP BY dia ORDER BY dia ASC
    """, fp).fetchall()

    # Peças em uso com localização atual e último operador
    em_uso = db.execute("""
        SELECT
            f.nome, f.categoria, f.uid_raw, f.peca_code,
            f.ultima_mov,
            s.nome  AS loc_setor,
            u.nome  AS loc_unidade,
            o.nome  AS ultimo_operador,
            o.matricula AS ultimo_operador_mat
        FROM pecas f
        LEFT JOIN setores    s ON s.codigo = f.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = f.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = f.ultimo_operador_id
        WHERE f.disponivel = 0
        ORDER BY f.ultima_mov DESC
    """).fetchall()

    # Localização atual de TODAS as pecas (para tabela de localização)
    localizacoes = db.execute("""
        SELECT
            f.peca_code, f.nome, f.categoria, f.uid_raw,
            f.disponivel, f.ultima_mov,
            s.nome  AS loc_setor,
            u.nome  AS loc_unidade,
            o.nome  AS ultimo_operador,
            o.matricula AS ultimo_operador_mat
        FROM pecas f
        LEFT JOIN setores    s ON s.codigo = f.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = f.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = f.ultimo_operador_id
        ORDER BY f.ultima_mov DESC NULLS LAST
    """).fetchall()

    return jsonify({
        "totais":          dict(totais),
        "top_pecas": [dict(r) for r in top_pecas],
        "por_setor":       [dict(r) for r in por_setor],
        "por_unidade":     [dict(r) for r in por_unidade],
        "por_dia":         [dict(r) for r in por_dia],
        "em_uso":          [dict(r) for r in em_uso],
        "localizacoes":    [dict(r) for r in localizacoes],
    })


@mov_bp.route("/alertas", methods=["GET"])
def alertas():
    setor   = request.args.get("setor")
    unidade = request.args.get("unidade")

    query = """
        SELECT
            f.nome, f.categoria, f.peca_code, f.uid_raw,
            f.quantidade, f.disponivel, f.ultima_mov,
            s.nome  AS loc_setor,
            u.nome  AS loc_unidade,
            o.nome  AS ultimo_operador,
            o.matricula AS ultimo_operador_mat
        FROM pecas f
        LEFT JOIN setores    s ON s.codigo = f.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = f.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = f.ultimo_operador_id
        WHERE f.disponivel = 0
    """
    params = []
    if setor:   query += " AND f.localizacao_setor=?";   params.append(int(setor))
    if unidade: query += " AND f.localizacao_unidade=?"; params.append(int(unidade))

    rows = get_db().execute(query, params).fetchall()
    return jsonify({"total_alertas": len(rows), "pecas": [dict(r) for r in rows]})
