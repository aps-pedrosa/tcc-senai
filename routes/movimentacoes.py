"""
routes/movimentacoes.py — VoidLog v3
GET /api/movimentacoes  → lista (filtros: setor, unidade, tipo, operador_id, operador_nome,
                                          equipamento_code, equipamento_nome, equipamento_uid,
                                          data_inicio, data_fim)
GET /api/movimentacoes/exportar?formato=pdf|csv → exporta relatório
"""

from flask import Blueprint, request, jsonify, send_file, session
from database import get_db
from datetime import datetime
import io

movimentacoes_bp = Blueprint("movimentacoes", __name__)


def _build_query(args):
    query = """
        SELECT
            mv.id,
            mv.tipo,
            mv.horario,
            mv.terminal_id,
            e.equipamento_code,
            e.nome          AS equipamento_nome,
            e.uid_raw       AS equipamento_uid,
            e.categoria     AS equipamento_categoria,
            o.id            AS operador_id,
            o.nome          AS operador_nome,
            o.matricula     AS operador_matricula,
            s.nome          AS setor_nome,
            u.nome          AS unidade_nome
        FROM movimentacoes mv
        JOIN equipamentos e  ON e.equipamento_code = mv.equipamento_code
        JOIN operadores   o  ON o.id               = mv.operador_id
        JOIN setores      s  ON s.codigo            = mv.setor_codigo
        JOIN unidades     u  ON u.codigo            = mv.unidade_codigo
        WHERE 1=1
    """
    params = []

    if args.get("setor"):
        query += " AND mv.setor_codigo = ?";          params.append(int(args["setor"]))
    if args.get("unidade"):
        query += " AND mv.unidade_codigo = ?";        params.append(int(args["unidade"]))
    if args.get("tipo"):
        query += " AND mv.tipo = ?";                  params.append(args["tipo"])
    if args.get("operador_id"):
        query += " AND o.id = ?";                     params.append(int(args["operador_id"]))
    if args.get("operador_nome", "").strip():
        query += " AND LOWER(o.nome) LIKE ?";         params.append(f"%{args['operador_nome'].lower()}%")
    if args.get("operador_matricula", "").strip():
        query += " AND LOWER(o.matricula) LIKE ?";    params.append(f"%{args['operador_matricula'].lower()}%")
    if args.get("equipamento_code"):
        query += " AND e.equipamento_code = ?";       params.append(int(args["equipamento_code"]))
    if args.get("equipamento_nome", "").strip():
        query += " AND LOWER(e.nome) LIKE ?";         params.append(f"%{args['equipamento_nome'].lower()}%")
    if args.get("equipamento_uid", "").strip():
        query += " AND UPPER(e.uid_raw) LIKE ?";      params.append(f"%{args['equipamento_uid'].upper()}%")
    if args.get("data_inicio"):
        query += " AND DATE(mv.horario) >= ?";        params.append(args["data_inicio"])
    if args.get("data_fim"):
        query += " AND DATE(mv.horario) <= ?";        params.append(args["data_fim"])

    query += " ORDER BY mv.horario DESC"

    limite = int(args.get("limite", 500))
    query += f" LIMIT {limite}"

    return query, params


@movimentacoes_bp.route("/movimentacoes", methods=["GET"])
def listar_movimentacoes():
    query, params = _build_query(request.args)
    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@movimentacoes_bp.route("/movimentacoes/exportar", methods=["GET"])
def exportar_movimentacoes():
    formato = request.args.get("formato", "csv").lower()
    if formato not in ("pdf", "csv"):
        return jsonify({"erro": "Formato deve ser 'pdf' ou 'csv'"}), 400

    query, params = _build_query(request.args)
    rows = get_db().execute(query, params).fetchall()
    dados = [dict(r) for r in rows]

    # Registra a exportação
    usuario_id = session.get("usuario_id", 1)
    filtros_str = str({k: v for k, v in request.args.items() if k != "formato"})
    db = get_db()
    db.execute(
        "INSERT INTO exportacoes (usuario_id, formato, filtros, total_linhas) VALUES (?,?,?,?)",
        (usuario_id, formato, filtros_str, len(dados))
    )
    db.commit()

    if formato == "csv":
        return _export_csv(dados)
    else:
        return _export_pdf(dados, db, usuario_id)


def _export_csv(dados):
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Tipo", "Horário", "Terminal",
        "Equipamento", "UID", "Categoria",
        "Operador", "Matrícula",
        "Setor", "Unidade"
    ])
    for r in dados:
        writer.writerow([
            r["id"], r["tipo"], r["horario"], r["terminal_id"],
            r["equipamento_nome"], r["equipamento_uid"], r["equipamento_categoria"],
            r["operador_nome"], r["operador_matricula"],
            r["setor_nome"], r["unidade_nome"]
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"voidlog_movimentacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )


def _export_pdf(dados, db, usuario_id):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import cm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    usuario = db.execute("SELECT nome, email FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    usuario_str = f"{usuario['nome']} ({usuario['email']})" if usuario else f"ID {usuario_id}"

    styles = getSampleStyleSheet()
    elements = []

    # Cabeçalho
    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                  fontSize=16, textColor=colors.HexColor("#1a1a2e"))
    elements.append(Paragraph("VoidLog — Relatório de Movimentações", title_style))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | "
        f"Exportado por: {usuario_str} | Total: {len(dados)} registros",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 0.5*cm))

    # Tabela
    header = ["#", "Tipo", "Horário", "Equipamento", "UID", "Operador", "Setor", "Unidade"]
    table_data = [header]
    for r in dados:
        table_data.append([
            str(r["id"]),
            "↑ Retirada" if r["tipo"] == "retirada" else "↓ Devolução",
            str(r["horario"])[:16] if r["horario"] else "—",
            r["equipamento_nome"] or "—",
            r["equipamento_uid"] or "—",
            r["operador_nome"] or "—",
            r["setor_nome"] or "—",
            r["unidade_nome"] or "—",
        ])

    col_widths = [1.2*cm, 2.8*cm, 3.5*cm, 5*cm, 3*cm, 4*cm, 3*cm, 3.5*cm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),  colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",    (0,0), (-1,0),  colors.white),
        ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0),  9),
        ("FONTSIZE",     (0,1), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("LEFTPADDING",  (0,0), (-1,-1), 5),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"voidlog_movimentacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
