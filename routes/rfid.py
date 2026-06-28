"""
routes/rfid.py — VoidLog v3
POST /api/rfid — recebe leituras do ESP32.

PAYLOAD:
{
    "uid":            "04A3F21B7C",
    "setor_codigo":   4,
    "unidade_codigo": 2,
    "terminal_id":    "AA:BB:CC:DD:EE:FF"  ← MAC do ESP
}
"""

from flask import Blueprint, request, jsonify, current_app
from database import get_db
from uid_parser import parse_uid, UIDParseError

rfid_bp = Blueprint("rfid", __name__)


@rfid_bp.route("/rfid", methods=["POST"])
def leitura_rfid():
    body = request.get_json(silent=True)
    if not body or "uid" not in body:
        return _erro("JSON inválido. Chave 'uid' ausente.")

    setor_codigo   = body.get("setor_codigo")
    unidade_codigo = body.get("unidade_codigo")
    terminal_id    = body.get("terminal_id", "default")

    if not setor_codigo or not unidade_codigo:
        return _erro("Campos obrigatórios ausentes: setor_codigo, unidade_codigo")

    try:
        setor_codigo   = int(setor_codigo)
        unidade_codigo = int(unidade_codigo)
    except (ValueError, TypeError):
        return _erro("setor_codigo e unidade_codigo devem ser inteiros")

    try:
        uid = parse_uid(body["uid"])
    except UIDParseError as e:
        return _erro(str(e))

    db = get_db()

    setor   = db.execute("SELECT * FROM setores   WHERE codigo=?", (setor_codigo,)).fetchone()
    unidade = db.execute("SELECT * FROM unidades  WHERE codigo=?", (unidade_codigo,)).fetchone()
    if not setor:
        return _erro(f"Setor {setor_codigo} não encontrado."), 404
    if not unidade:
        return _erro(f"Unidade {unidade_codigo} não encontrada."), 404

    ctx = {
        "setor_codigo":   setor_codigo,
        "setor_nome":     setor["nome"],
        "unidade_codigo": unidade_codigo,
        "unidade_nome":   unidade["nome"],
        "terminal_id":    terminal_id,
    }

    # Valida terminal (pelo MAC)
    if terminal_id != "default":
        term = db.execute(
            "SELECT * FROM terminais WHERE terminal_id=?", (terminal_id,)
        ).fetchone()
        if term is None or term["status"] != "aprovado":
            status_msg = term["status"] if term else "não cadastrado"
            return _erro(f"Terminal {terminal_id} não autorizado ({status_msg})."), 403
        # Atualiza ultimo_acesso
        db.execute("UPDATE terminais SET ultimo_acesso=CURRENT_TIMESTAMP WHERE terminal_id=?",
                   (terminal_id,))

    # ── Operador? ─────────────────────────────────────────────────────────
    operador = db.execute(
        "SELECT * FROM operadores WHERE uid_raw = ?", (uid["uid_raw"],)
    ).fetchone()
    if not operador:
        operador = db.execute(
            "SELECT * FROM operadores WHERE equipamento_code = ?", (uid["peca_code"],)
        ).fetchone()

    if operador:
        return _registrar_sessao(db, operador, uid, ctx)

    # ── Equipamento RFID? ─────────────────────────────────────────────────
    equip = db.execute(
        "SELECT * FROM equipamentos WHERE uid_raw = ?", (uid["uid_raw"],)
    ).fetchone()
    if not equip:
        equip = db.execute(
            "SELECT * FROM equipamentos WHERE equipamento_code = ?", (uid["peca_code"],)
        ).fetchone()

    if equip:
        # Bloqueia equipamentos em manutenção
        if equip["em_manutencao"]:
            return jsonify({
                "status": "erro",
                "tipo":   "equipamento",
                "acao":   "bloqueado",
                "msg":    f"Em manutenção: {equip['nome'][:20]}",
                "detalhes": {"equipamento": equip["nome"], "em_manutencao": True}
            }), 403
        return _registrar_movimentacao(db, equip, uid, ctx)

    return _erro(
        f"Tag não cadastrada. uid_raw={uid['uid_raw']} code={uid['peca_code']}"
    ), 404


# ── Sessão de operador ─────────────────────────────────────────────────────

def _registrar_sessao(db, operador, uid, ctx):
    sessao_ativa = db.execute(
        """SELECT * FROM sessoes
           WHERE operador_id=? AND terminal_id=? AND ativa=1
           ORDER BY inicio DESC LIMIT 1""",
        (operador["id"], ctx["terminal_id"])
    ).fetchone()

    primeiro = operador["nome"].split()[0]

    if sessao_ativa:
        db.execute("UPDATE sessoes SET ativa=0 WHERE id=?", (sessao_ativa["id"],))
        db.commit()
        current_app.sse_push("operador", {"acao": "logout", "nome": operador["nome"]})
        return jsonify({
            "status": "ok",
            "tipo":   "operador",
            "acao":   "logout",
            "msg":    f"Tchau, {primeiro}!",
            "operador": {"id": operador["id"], "nome": operador["nome"],
                         "matricula": operador["matricula"]},
            "terminal": ctx,
        })
    else:
        db.execute(
            """INSERT INTO sessoes (operador_id, terminal_id, setor_codigo, unidade_codigo)
               VALUES (?,?,?,?)""",
            (operador["id"], ctx["terminal_id"], ctx["setor_codigo"], ctx["unidade_codigo"])
        )
        db.commit()
        current_app.sse_push("operador", {"acao": "login", "nome": operador["nome"]})
        return jsonify({
            "status": "ok",
            "tipo":   "operador",
            "acao":   "login",
            "msg":    f"Ola, {primeiro}!",
            "operador": {"id": operador["id"], "nome": operador["nome"],
                         "matricula": operador["matricula"]},
            "terminal": ctx,
        })


# ── Movimentação de equipamento ───────────────────────────────────────────

def _registrar_movimentacao(db, equip, uid, ctx):
    sessao = db.execute(
        """SELECT s.*, o.nome as op_nome, o.id as op_id, o.matricula as op_mat
           FROM sessoes s
           JOIN operadores o ON o.id = s.operador_id
           WHERE s.terminal_id=? AND s.ativa=1
           ORDER BY s.inicio DESC LIMIT 1""",
        (ctx["terminal_id"],)
    ).fetchone()

    if not sessao:
        sessao = db.execute(
            """SELECT s.*, o.nome as op_nome, o.id as op_id, o.matricula as op_mat
               FROM sessoes s
               JOIN operadores o ON o.id = s.operador_id
               WHERE s.ativa=1
               ORDER BY s.inicio DESC LIMIT 1"""
        ).fetchone()

    if not sessao:
        return _erro("Nenhum operador identificado. Passe o crachá primeiro."), 403

    tipo      = "devolucao" if equip["disponivel"] == 0 else "retirada"
    nova_disp = 1 if tipo == "devolucao" else 0

    db.execute(
        """INSERT INTO movimentacoes
           (equipamento_code, operador_id, terminal_id, setor_codigo, unidade_codigo, tipo)
           VALUES (?,?,?,?,?,?)""",
        (equip["equipamento_code"], sessao["op_id"],
         ctx["terminal_id"], ctx["setor_codigo"], ctx["unidade_codigo"], tipo)
    )

    db.execute(
        """UPDATE equipamentos SET
               disponivel          = ?,
               localizacao_setor   = ?,
               localizacao_unidade = ?,
               ultimo_operador_id  = ?,
               ultima_mov          = CURRENT_TIMESTAMP
           WHERE equipamento_code = ?""",
        (nova_disp, ctx["setor_codigo"], ctx["unidade_codigo"],
         sessao["op_id"], equip["equipamento_code"])
    )
    db.commit()

    label = "Retirada" if tipo == "retirada" else "Devolvida"
    current_app.sse_push("movimentacao", {
        "tipo":              tipo,
        "equipamento":       equip["nome"],
        "equipamento_code":  equip["equipamento_code"],
        "operador":          sessao["op_nome"],
        "setor":             ctx["setor_nome"],
        "unidade":           ctx["unidade_nome"],
    })
    return jsonify({
        "status": "ok",
        "tipo":   "equipamento",
        "acao":   tipo,
        "msg":    f"{label}: {equip['nome'][:20]}",
        "detalhes": {
            "equipamento":      equip["nome"],
            "categoria":        equip["categoria"],
            "equipamento_code": equip["equipamento_code"],
            "uid_raw":          uid["uid_raw"],
            "operador":         sessao["op_nome"],
            "matricula":        sessao["op_mat"],
            "localizacao": {
                "setor":      ctx["setor_nome"],
                "unidade":    ctx["unidade_nome"],
                "terminal_id": ctx["terminal_id"],
            },
        }
    })


def _erro(msg: str):
    return jsonify({"status": "erro", "tipo": None, "msg": msg})
