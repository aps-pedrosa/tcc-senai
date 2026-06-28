"""
routes/manutencao.py — VoidLog v3
GET  /api/manutencao                  → histórico (filtros: equipamento_code, nome, uid)
POST /api/manutencao/entrada          → entra em manutenção (terminal ou web)
POST /api/manutencao/saida            → sai de manutenção
GET  /api/manutencao/status           → lista equipamentos em manutenção
POST /api/manutencao/terminal         → recebe evento do ESP de manutenção
"""

from flask import Blueprint, request, jsonify
from database import get_db
from datetime import datetime

manutencao_bp = Blueprint("manutencao", __name__)


@manutencao_bp.route("/manutencao", methods=["GET"])
def listar_historico():
    equipamento_code = request.args.get("equipamento_code")
    nome_q  = request.args.get("nome", "").strip()
    uid_q   = request.args.get("uid", "").strip().upper()

    query = """
        SELECT m.*, e.nome AS equipamento_nome, e.uid_raw, e.categoria
        FROM manutencoes m
        JOIN equipamentos e ON e.equipamento_code = m.equipamento_code
        WHERE 1=1
    """
    params = []
    if equipamento_code:
        query += " AND m.equipamento_code = ?"; params.append(int(equipamento_code))
    if nome_q:
        query += " AND LOWER(e.nome) LIKE ?"; params.append(f"%{nome_q.lower()}%")
    if uid_q:
        query += " AND UPPER(e.uid_raw) LIKE ?"; params.append(f"%{uid_q}%")
    query += " ORDER BY m.horario DESC"

    rows = get_db().execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@manutencao_bp.route("/manutencao/status", methods=["GET"])
def equipamentos_em_manutencao():
    rows = get_db().execute("""
        SELECT e.*,
               s.nome AS loc_setor_nome,
               u.nome AS loc_unidade_nome,
               (SELECT horario FROM manutencoes WHERE equipamento_code=e.equipamento_code AND tipo='entrada'
                ORDER BY horario DESC LIMIT 1) AS entrada_em
        FROM equipamentos e
        LEFT JOIN setores  s ON s.codigo = e.localizacao_setor
        LEFT JOIN unidades u ON u.codigo = e.localizacao_unidade
        WHERE e.em_manutencao = 1
        ORDER BY e.nome
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@manutencao_bp.route("/manutencao/entrada", methods=["POST"])
def entrada_manutencao():
    data = request.get_json(silent=True) or {}
    equipamento_code = data.get("equipamento_code")
    if not equipamento_code:
        return jsonify({"erro": "equipamento_code obrigatório"}), 400

    db  = get_db()
    row = db.execute("SELECT * FROM equipamentos WHERE equipamento_code=?", (equipamento_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Equipamento não encontrado"}), 404
    if row["em_manutencao"]:
        return jsonify({"erro": "Equipamento já em manutenção"}), 409

    db.execute("UPDATE equipamentos SET em_manutencao=1, disponivel=0 WHERE equipamento_code=?", (equipamento_code,))
    db.execute("""INSERT INTO manutencoes (equipamento_code, tipo, descricao, tecnico, terminal_id)
                  VALUES (?,?,?,?,?)""",
               (equipamento_code, "entrada",
                data.get("descricao", ""), data.get("tecnico", ""),
                data.get("terminal_id", "web")))
    db.commit()

    _enviar_alerta_manutencao(db, row["nome"], "entrada", data.get("descricao", ""))
    return jsonify({"ok": True, "mensagem": f"Equipamento '{row['nome']}' entrou em manutenção"})


@manutencao_bp.route("/manutencao/saida", methods=["POST"])
def saida_manutencao():
    data = request.get_json(silent=True) or {}
    equipamento_code = data.get("equipamento_code")
    if not equipamento_code:
        return jsonify({"erro": "equipamento_code obrigatório"}), 400

    db  = get_db()
    row = db.execute("SELECT * FROM equipamentos WHERE equipamento_code=?", (equipamento_code,)).fetchone()
    if not row:
        return jsonify({"erro": "Equipamento não encontrado"}), 404
    if not row["em_manutencao"]:
        return jsonify({"erro": "Equipamento não está em manutenção"}), 409

    db.execute("UPDATE equipamentos SET em_manutencao=0, disponivel=1 WHERE equipamento_code=?", (equipamento_code,))
    db.execute("""INSERT INTO manutencoes (equipamento_code, tipo, descricao, tecnico, terminal_id)
                  VALUES (?,?,?,?,?)""",
               (equipamento_code, "saida",
                data.get("descricao", ""), data.get("tecnico", ""),
                data.get("terminal_id", "web")))
    db.commit()

    _enviar_alerta_manutencao(db, row["nome"], "saida", data.get("descricao", ""))
    return jsonify({"ok": True, "mensagem": f"Equipamento '{row['nome']}' saiu de manutenção"})


@manutencao_bp.route("/manutencao/terminal", methods=["POST"])
def evento_terminal_manutencao():
    """
    Endpoint chamado pelo ESP32 de manutenção quando lê um UID.
    Payload: { terminal_id, uid_raw, tipo: 'entrada'|'saida', descricao, tecnico }
    """
    data = request.get_json(silent=True) or {}
    terminal_id = data.get("terminal_id", "")
    uid_raw     = (data.get("uid_raw") or "").upper().replace(":", "").replace(" ", "")
    tipo        = data.get("tipo", "entrada")

    if not terminal_id or not uid_raw:
        return jsonify({"erro": "terminal_id e uid_raw obrigatórios"}), 400

    db = get_db()

    # Valida terminal
    terminal = db.execute("SELECT * FROM terminais WHERE terminal_id=?", (terminal_id,)).fetchone()
    if not terminal:
        return jsonify({"erro": "Terminal não cadastrado"}), 403
    if terminal["status"] != "aprovado":
        return jsonify({"erro": "Terminal não aprovado"}), 403
    if terminal["tipo"] != "manutencao":
        return jsonify({"erro": "Terminal não é do tipo manutenção"}), 403

    db.execute("UPDATE terminais SET ultimo_acesso=CURRENT_TIMESTAMP WHERE terminal_id=?", (terminal_id,))

    # Localiza equipamento
    equip = db.execute("SELECT * FROM equipamentos WHERE UPPER(uid_raw)=?", (uid_raw,)).fetchone()
    if not equip:
        return jsonify({"erro": "Equipamento não encontrado para este UID", "uid_raw": uid_raw}), 404

    equipamento_code = equip["equipamento_code"]

    if tipo == "entrada":
        if equip["em_manutencao"]:
            return jsonify({"aviso": "Equipamento já em manutenção", "nome": equip["nome"]}), 200
        db.execute("UPDATE equipamentos SET em_manutencao=1, disponivel=0 WHERE equipamento_code=?",
                   (equipamento_code,))
        db.execute("""INSERT INTO manutencoes (equipamento_code,tipo,descricao,tecnico,terminal_id)
                      VALUES (?,?,?,?,?)""",
                   (equipamento_code, "entrada",
                    data.get("descricao", ""), data.get("tecnico", ""), terminal_id))
        db.commit()
        return jsonify({"ok": True, "acao": "entrada", "nome": equip["nome"]})

    elif tipo == "saida":
        if not equip["em_manutencao"]:
            return jsonify({"aviso": "Equipamento não estava em manutenção", "nome": equip["nome"]}), 200
        db.execute("UPDATE equipamentos SET em_manutencao=0, disponivel=1 WHERE equipamento_code=?",
                   (equipamento_code,))
        db.execute("""INSERT INTO manutencoes (equipamento_code,tipo,descricao,tecnico,terminal_id)
                      VALUES (?,?,?,?,?)""",
                   (equipamento_code, "saida",
                    data.get("descricao", ""), data.get("tecnico", ""), terminal_id))
        db.commit()
        return jsonify({"ok": True, "acao": "saida", "nome": equip["nome"]})

    else:
        # Toggle automático
        if equip["em_manutencao"]:
            db.execute("UPDATE equipamentos SET em_manutencao=0, disponivel=1 WHERE equipamento_code=?",
                       (equipamento_code,))
            acao = "saida"
        else:
            db.execute("UPDATE equipamentos SET em_manutencao=1, disponivel=0 WHERE equipamento_code=?",
                       (equipamento_code,))
            acao = "entrada"

        db.execute("""INSERT INTO manutencoes (equipamento_code,tipo,descricao,tecnico,terminal_id)
                      VALUES (?,?,?,?,?)""",
                   (equipamento_code, acao,
                    data.get("descricao", ""), data.get("tecnico", ""), terminal_id))
        db.commit()
        return jsonify({"ok": True, "acao": acao, "nome": equip["nome"]})


def _enviar_alerta_manutencao(db, nome_equip, tipo, descricao):
    try:
        cfg = {r["chave"]: r["valor"] for r in db.execute("SELECT chave,valor FROM configuracoes")}
        if cfg.get("email_alertas_habilitado") != "1":
            return
        destino = cfg.get("email_destino", "")
        if not destino:
            return
        from email_service import enviar_email
        assunto = f"[VoidLog] Equipamento '{nome_equip}' {'entrou em' if tipo=='entrada' else 'saiu de'} manutenção"
        corpo   = f"Equipamento: {nome_equip}\nEvento: {tipo}\nDescrição: {descricao or '—'}\nHorário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        enviar_email(cfg, destino, assunto, corpo)
    except Exception:
        pass
