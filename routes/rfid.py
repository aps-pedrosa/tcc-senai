"""
routes/rfid.py — VoidLog v2
─────────────────────────────────────────────────────────────────
POST /api/rfid — recebe leituras do ESP32.

PAYLOAD (v2):
{
    "uid":            "04A3F21B7C",  ← UID COMPLETO lido pelo RC522 (todos os bytes)
    "setor_codigo":   4,             ← selecionado no encoder do terminal
    "unidade_codigo": 2,             ← selecionado no encoder do terminal
    "terminal_id":    "ESP-A1B2C3"  ← opcional, ID do ESP32
}

Fluxo:
  1. Parse do UID → uid_raw = UID completo, peca_code = B1+B2
  2. Setor e unidade vêm do payload (não da tag)
  3. Identifica crachá ou peça:
       a) Busca por uid_raw EXATO no banco (lookup primário — UID completo)
       b) Fallback: busca por peca_code (compatibilidade barcodes / cadastro manual)
  4. Crachá  → abre/encerra sessão do operador naquele terminal
  5. Peça    → registra retirada ou devolução com localização atual
  6. Atualiza localização atual e último operador da peça
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, UIDParseError

rfid_bp = Blueprint("rfid", __name__)


@rfid_bp.route("/rfid", methods=["POST"])
def leitura_rfid():
    body = request.get_json(silent=True)
    if not body or "uid" not in body:
        return _erro("JSON inválido. Chave 'uid' ausente.")

    # ── Valida setor e unidade do terminal ────────────────────────
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

    # ── Parse do UID ──────────────────────────────────────────────
    try:
        uid = parse_uid(body["uid"])
    except UIDParseError as e:
        return _erro(str(e))

    db = get_db()

    # ── Valida setor e unidade no banco ───────────────────────────
    setor   = db.execute("SELECT * FROM setores   WHERE codigo=?", (setor_codigo,)).fetchone()
    unidade = db.execute("SELECT * FROM unidades  WHERE codigo=?", (unidade_codigo,)).fetchone()
    if not setor:
        return _erro(f"Setor {setor_codigo} não encontrado no banco."), 404
    if not unidade:
        return _erro(f"Unidade {unidade_codigo} não encontrada no banco."), 404

    ctx = {
        "setor_codigo":   setor_codigo,
        "setor_nome":     setor["nome"],
        "unidade_codigo": unidade_codigo,
        "unidade_nome":   unidade["nome"],
        "terminal_id":    terminal_id,
    }

    # ── É crachá de operador? ─────────────────────────────────────
    # Lookup primário: uid_raw completo (todos os bytes)
    operador = db.execute(
        "SELECT * FROM operadores WHERE uid_raw = ?", (uid["uid_raw"],)
    ).fetchone()

    # Fallback: peca_code (compatibilidade com barcodes e UIDs antigos)
    if not operador:
        operador = db.execute(
            "SELECT * FROM operadores WHERE peca_code = ?", (uid["peca_code"],)
        ).fetchone()

    if operador:
        return _registrar_sessao(db, operador, uid, ctx)

    # ── É peça RFID? ─────────────────────────────────────────────
    # Lookup primário: uid_raw completo
    peca = db.execute(
        "SELECT * FROM pecas WHERE uid_raw = ?", (uid["uid_raw"],)
    ).fetchone()

    # Fallback: peca_code (compatibilidade com barcodes e cadastro manual)
    if not peca:
        peca = db.execute(
            "SELECT * FROM pecas WHERE peca_code = ?", (uid["peca_code"],)
        ).fetchone()

    if peca:
        return _registrar_movimentacao(db, peca, uid, ctx)

    # ── UID não cadastrado ────────────────────────────────────────
    return _erro(
        f"Tag não cadastrada. uid_raw={uid['uid_raw']} peca_code={uid['peca_code']}"
    ), 404


# ── Sessão de operador ────────────────────────────────────────────

def _registrar_sessao(db, operador, uid, ctx):
    """Abre ou encerra sessão do operador no terminal informado."""
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
        return jsonify({
            "status": "ok",
            "tipo":   "operador",
            "acao":   "logout",
            "msg":    f"Tchau, {primeiro}!",
            "operador": {
                "id":        operador["id"],
                "nome":      operador["nome"],
                "matricula": operador["matricula"],
            },
            "terminal": ctx,
        })
    else:
        db.execute(
            """INSERT INTO sessoes
               (operador_id, terminal_id, setor_codigo, unidade_codigo)
               VALUES (?,?,?,?)""",
            (operador["id"], ctx["terminal_id"], ctx["setor_codigo"], ctx["unidade_codigo"])
        )
        db.commit()
        return jsonify({
            "status": "ok",
            "tipo":   "operador",
            "acao":   "login",
            "msg":    f"Ola, {primeiro}!",
            "operador": {
                "id":        operador["id"],
                "nome":      operador["nome"],
                "matricula": operador["matricula"],
            },
            "terminal": ctx,
        })


# ── Movimentação de peça ──────────────────────────────────────────

def _registrar_movimentacao(db, peca, uid, ctx):
    """Registra retirada ou devolução usando o contexto do terminal."""

    # Busca sessão ativa no mesmo terminal
    sessao = db.execute(
        """SELECT s.*, o.nome as op_nome, o.id as op_id, o.matricula as op_mat
           FROM sessoes s
           JOIN operadores o ON o.id = s.operador_id
           WHERE s.terminal_id=? AND s.ativa=1
           ORDER BY s.inicio DESC LIMIT 1""",
        (ctx["terminal_id"],)
    ).fetchone()

    # Fallback: qualquer sessão ativa
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

    tipo      = "devolucao" if peca["disponivel"] == 0 else "retirada"
    nova_disp = 1 if tipo == "devolucao" else 0

    # Grava movimentação com contexto do terminal
    db.execute(
        """INSERT INTO movimentacoes
           (peca_peca, operador_id, terminal_id, setor_codigo, unidade_codigo, tipo)
           VALUES (?,?,?,?,?,?)""",
        (
            peca["peca_code"],
            sessao["op_id"],
            ctx["terminal_id"],
            ctx["setor_codigo"],
            ctx["unidade_codigo"],
            tipo,
        )
    )

    # Atualiza disponibilidade + localização atual + último operador
    db.execute(
        """UPDATE pecas SET
               disponivel          = ?,
               localizacao_setor   = ?,
               localizacao_unidade = ?,
               ultimo_operador_id  = ?,
               ultima_mov          = CURRENT_TIMESTAMP
           WHERE peca_code = ?""",
        (
            nova_disp,
            ctx["setor_codigo"],
            ctx["unidade_codigo"],
            sessao["op_id"],
            peca["peca_code"],
        )
    )
    db.commit()

    label = "Retirada" if tipo == "retirada" else "Devolvida"
    return jsonify({
        "status": "ok",
        "tipo":   "peca",
        "acao":   tipo,
        "msg":    f"{label}: {peca['nome'][:20]}",
        "detalhes": {
            "peca":      peca["nome"],
            "categoria": peca["categoria"],
            "peca_code": peca["peca_code"],
            "uid_raw":   uid["uid_raw"],
            "operador":  sessao["op_nome"],
            "matricula": sessao["op_mat"],
            "localizacao": {
                "setor":      ctx["setor_nome"],
                "unidade":    ctx["unidade_nome"],
                "terminal_id": ctx["terminal_id"],
            },
        }
    })


def _erro(msg: str):
    return jsonify({"status": "erro", "tipo": None, "msg": msg})
