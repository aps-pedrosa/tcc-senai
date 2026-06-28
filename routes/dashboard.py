"""
routes/dashboard.py — VoidLog v3
GET /api/dashboard/dados
GET /api/sessoes/ativas
GET /api/ping
"""

from flask import Blueprint, request, jsonify
from database import get_db

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "sistema": "VoidLog v3"})


@dashboard_bp.route("/sessoes/ativas", methods=["GET"])
def sessoes_ativas():
    rows = get_db().execute("""
        SELECT s.*, o.nome, o.matricula
        FROM sessoes s
        JOIN operadores o ON o.id = s.operador_id
        WHERE s.ativa = 1
        ORDER BY s.inicio DESC
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@dashboard_bp.route("/dashboard/dados", methods=["GET"])
def dashboard_dados():
    setor   = request.args.get("setor")
    unidade = request.args.get("unidade")

    db = get_db()

    # ── Filtro base ───────────────────────────────────────────────────────
    where, params = [], []
    if setor:
        where.append("mv.setor_codigo = ?");    params.append(int(setor))
    if unidade:
        where.append("mv.unidade_codigo = ?");  params.append(int(unidade))
    w = ("WHERE " + " AND ".join(where)) if where else ""

    # ── Totais ────────────────────────────────────────────────────────────
    totais = db.execute(f"""
        SELECT
            COUNT(*)                                    AS total_movimentacoes,
            SUM(CASE WHEN mv.tipo='retirada'  THEN 1 ELSE 0 END) AS total_retiradas,
            SUM(CASE WHEN mv.tipo='devolucao' THEN 1 ELSE 0 END) AS total_devolucoes
        FROM movimentacoes mv {w}
    """, params).fetchone()

    # ── Equipamentos em uso (disponivel=0, não em manutenção) ────────────
    em_uso = db.execute("""
        SELECT e.*, s.nome AS loc_setor, u.nome AS loc_unidade,
               o.nome AS ultimo_operador, o.matricula AS ultimo_op_mat
        FROM equipamentos e
        LEFT JOIN setores    s ON s.codigo = e.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = e.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = e.ultimo_operador_id
        WHERE e.disponivel = 0 AND e.em_manutencao = 0
        ORDER BY e.ultima_mov DESC
    """).fetchall()

    # ── Em manutenção ─────────────────────────────────────────────────────
    em_manutencao_count = db.execute(
        "SELECT COUNT(*) AS n FROM equipamentos WHERE em_manutencao = 1"
    ).fetchone()["n"]

    # ── Localizações (todos equipamentos) ────────────────────────────────
    localizacoes = db.execute("""
        SELECT e.*,
               s.nome  AS loc_setor_nome,
               u.nome  AS loc_unidade_nome,
               o.nome  AS ultimo_operador,
               o.matricula AS ultimo_operador_mat
        FROM equipamentos e
        LEFT JOIN setores    s ON s.codigo = e.localizacao_setor
        LEFT JOIN unidades   u ON u.codigo = e.localizacao_unidade
        LEFT JOIN operadores o ON o.id     = e.ultimo_operador_id
        ORDER BY e.nome
    """).fetchall()

    # ── Por dia (30 dias) ─────────────────────────────────────────────────
    por_dia = db.execute(f"""
        SELECT DATE(mv.horario) AS dia, COUNT(*) AS total
        FROM movimentacoes mv {w}
        WHERE mv.horario >= DATE('now', '-30 days')
        GROUP BY dia ORDER BY dia
    """, params).fetchall()

    # ── Por unidade ───────────────────────────────────────────────────────
    por_unidade = db.execute(f"""
        SELECT u.nome AS unidade, COUNT(*) AS movimentacoes
        FROM movimentacoes mv {w}
        JOIN unidades u ON u.codigo = mv.unidade_codigo
        GROUP BY u.codigo ORDER BY movimentacoes DESC
    """, params).fetchall()

    # ── Por setor ─────────────────────────────────────────────────────────
    por_setor = db.execute(f"""
        SELECT s.nome AS setor, COUNT(*) AS movimentacoes
        FROM movimentacoes mv {w}
        JOIN setores s ON s.codigo = mv.setor_codigo
        GROUP BY s.codigo ORDER BY movimentacoes DESC
    """, params).fetchall()

    # ── Top equipamentos ──────────────────────────────────────────────────
    top_pecas = db.execute(f"""
        SELECT e.nome, COUNT(*) AS usos
        FROM movimentacoes mv {w}
        JOIN equipamentos e ON e.equipamento_code = mv.equipamento_code
        WHERE mv.tipo = 'retirada'
        GROUP BY e.equipamento_code ORDER BY usos DESC LIMIT 10
    """, params).fetchall()

    return jsonify({
        "totais":         dict(totais) if totais else {},
        "em_uso":         [dict(r) for r in em_uso],
        "em_manutencao":  em_manutencao_count,
        "localizacoes":   [dict(r) for r in localizacoes],
        "por_dia":        [dict(r) for r in por_dia],
        "por_unidade":    [dict(r) for r in por_unidade],
        "por_setor":      [dict(r) for r in por_setor],
        "top_pecas":      [dict(r) for r in top_pecas],
    })
