"""
routes/movimentacoes.py
─────────────────────────────────────────────────────────────────
GET /api/movimentacoes           → histórico (filtros: setor, unidade, tipo, data)
GET /api/dashboard/dados         → totais para os gráficos do frontend
GET /api/alertas                 → ferramentas com estoque crítico
"""

from flask import Blueprint, request, jsonify
from database import get_db

mov_bp = Blueprint("movimentacoes", __name__)


# ── Histórico de movimentações ─────────────────────────────────────

@mov_bp.route("/movimentacoes", methods=["GET"])
def listar_movimentacoes():
    """
    Query params opcionais:
      setor     → código do setor   (byte B3)
      unidade   → código da unidade (byte B4)
      tipo      → 'retirada' ou 'devolucao'
      data_ini  → YYYY-MM-DD
      data_fim  → YYYY-MM-DD
      limit     → padrão 100
    """
    setor    = request.args.get("setor")
    unidade  = request.args.get("unidade")
    tipo     = request.args.get("tipo")
    data_ini = request.args.get("data_ini")
    data_fim = request.args.get("data_fim")
    limit    = int(request.args.get("limit", 100))

    query = """
        SELECT
            m.id,
            m.tipo,
            m.horario,
            f.nome         AS ferramenta,
            f.categoria,
            f.uid_raw,
            f.peca_code,
            o.nome         AS operador,
            o.matricula,
            s.nome         AS setor,
            u.nome         AS unidade,
            -- Breakdown dos bytes no retorno
            hex(f.setor_codigo)   AS byte_B3_hex,
            hex(f.unidade_codigo) AS byte_B4_hex
        FROM movimentacoes m
        JOIN ferramentas f ON f.peca_code     = m.ferramenta_peca
        JOIN operadores  o ON o.id            = m.operador_id
        JOIN setores     s ON s.codigo        = m.setor_codigo
        JOIN unidades    u ON u.codigo        = m.unidade_codigo
        WHERE 1=1
    """
    params = []

    if setor:
        query += " AND m.setor_codigo = ?"
        params.append(int(setor))
    if unidade:
        query += " AND m.unidade_codigo = ?"
        params.append(int(unidade))
    if tipo:
        query += " AND m.tipo = ?"
        params.append(tipo)
    if data_ini:
        query += " AND DATE(m.horario) >= ?"
        params.append(data_ini)
    if data_fim:
        query += " AND DATE(m.horario) <= ?"
        params.append(data_fim)

    query += " ORDER BY m.horario DESC LIMIT ?"
    params.append(limit)

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Dashboard ──────────────────────────────────────────────────────

@mov_bp.route("/dashboard/dados", methods=["GET"])
def dados_dashboard():
    """
    Retorna os totais consolidados para os gráficos do frontend.
    Tudo filtrado por setor (B3) e unidade (B4) quando informados.
    """
    setor   = request.args.get("setor")
    unidade = request.args.get("unidade")
    db      = get_db()

    filtro_sql    = ""
    filtro_params = []
    if setor:
        filtro_sql += " AND m.setor_codigo = ?"
        filtro_params.append(int(setor))
    if unidade:
        filtro_sql += " AND m.unidade_codigo = ?"
        filtro_params.append(int(unidade))

    # Totais gerais
    totais = db.execute(f"""
        SELECT
            COUNT(*)                                              AS total_movimentacoes,
            SUM(CASE WHEN tipo='retirada'  THEN 1 ELSE 0 END)   AS total_retiradas,
            SUM(CASE WHEN tipo='devolucao' THEN 1 ELSE 0 END)   AS total_devolucoes
        FROM movimentacoes m WHERE 1=1 {filtro_sql}
    """, filtro_params).fetchone()

    # Top ferramentas mais usadas
    top_ferramentas = db.execute(f"""
        SELECT f.nome, f.categoria, COUNT(*) AS usos
        FROM movimentacoes m
        JOIN ferramentas f ON f.peca_code = m.ferramenta_peca
        WHERE m.tipo = 'retirada' {filtro_sql}
        GROUP BY m.ferramenta_peca
        ORDER BY usos DESC
        LIMIT 10
    """, filtro_params).fetchall()

    # Consumo por setor (byte B3)
    por_setor = db.execute(f"""
        SELECT s.nome AS setor, s.codigo, COUNT(*) AS movimentacoes
        FROM movimentacoes m
        JOIN setores s ON s.codigo = m.setor_codigo
        WHERE 1=1 {filtro_sql}
        GROUP BY m.setor_codigo
        ORDER BY movimentacoes DESC
    """, filtro_params).fetchall()

    # Consumo por unidade (byte B4)
    por_unidade = db.execute(f"""
        SELECT u.nome AS unidade, u.codigo, COUNT(*) AS movimentacoes
        FROM movimentacoes m
        JOIN unidades u ON u.codigo = m.unidade_codigo
        WHERE 1=1 {filtro_sql}
        GROUP BY m.unidade_codigo
        ORDER BY movimentacoes DESC
    """, filtro_params).fetchall()

    # Movimentações por dia (últimos 30 dias)
    por_dia = db.execute(f"""
        SELECT DATE(m.horario) AS dia, COUNT(*) AS total
        FROM movimentacoes m
        WHERE m.horario >= DATE('now', '-30 days') {filtro_sql}
        GROUP BY dia
        ORDER BY dia ASC
    """, filtro_params).fetchall()

    # Ferramentas atualmente em uso
    em_uso = db.execute("""
        SELECT f.nome, f.categoria, f.uid_raw,
               s.nome AS setor, u.nome AS unidade
        FROM ferramentas f
        JOIN setores  s ON s.codigo = f.setor_codigo
        JOIN unidades u ON u.codigo = f.unidade_codigo
        WHERE f.disponivel = 0
    """).fetchall()

    return jsonify({
        "totais":          dict(totais),
        "top_ferramentas": [dict(r) for r in top_ferramentas],
        "por_setor":       [dict(r) for r in por_setor],
        "por_unidade":     [dict(r) for r in por_unidade],
        "por_dia":         [dict(r) for r in por_dia],
        "em_uso":          [dict(r) for r in em_uso],
    })


# ── Alertas de estoque crítico ─────────────────────────────────────

@mov_bp.route("/alertas", methods=["GET"])
def alertas():
    """
    Retorna ferramentas com disponibilidade zerada ou abaixo de 1.
    Filtra por setor (B3) e/ou unidade (B4) se informado.
    """
    setor   = request.args.get("setor")
    unidade = request.args.get("unidade")

    query = """
        SELECT f.nome, f.categoria, f.peca_code, f.uid_raw,
               f.quantidade, f.disponivel,
               s.nome AS setor, s.codigo AS setor_codigo,
               u.nome AS unidade, u.codigo AS unidade_codigo,
               hex(f.setor_codigo)   AS byte_B3,
               hex(f.unidade_codigo) AS byte_B4
        FROM ferramentas f
        JOIN setores  s ON s.codigo = f.setor_codigo
        JOIN unidades u ON u.codigo = f.unidade_codigo
        WHERE f.disponivel = 0
    """
    params = []
    if setor:
        query += " AND f.setor_codigo = ?"
        params.append(int(setor))
    if unidade:
        query += " AND f.unidade_codigo = ?"
        params.append(int(unidade))

    rows = get_db().execute(query, params).fetchall()
    return jsonify({
        "total_alertas": len(rows),
        "ferramentas":   [dict(r) for r in rows],
    })
