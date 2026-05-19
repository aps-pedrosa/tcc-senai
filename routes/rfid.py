"""
routes/rfid.py
─────────────────────────────────────────────────────────────────
Rota POST /api/rfid  — recebe leituras do ESP32.

Fluxo:
  1. Recebe o UID de 4 bytes do ESP32
  2. Faz o parse dos bytes (peca_code / setor / unidade)
  3. Identifica se é CRACHÁ de operador ou TAG de ferramenta
  4. Se for crachá  → abre/encerra sessão do operador
  5. Se for ferramenta → registra retirada ou devolução
  6. Retorna JSON com mensagem para exibir no LCD do ESP32
"""

from flask import Blueprint, request, jsonify
from database import get_db
from uid_parser import parse_uid, UIDParseError

rfid_bp = Blueprint("rfid", __name__)


# ── Rota principal ─────────────────────────────────────────────────

@rfid_bp.route("/rfid", methods=["POST"])
def leitura_rfid():
    """
    Payload esperado do ESP32:
    {
        "uid": "A34F21BC"
    }

    Resposta para o ESP32 exibir no LCD:
    {
        "status": "ok" | "erro",
        "tipo":   "operador" | "ferramenta" | null,
        "msg":    "Texto curto para o LCD (max 32 chars)"
    }
    """
    body = request.get_json(silent=True)
    if not body or "uid" not in body:
        return _erro("JSON inválido. Chave 'uid' ausente.")

    # ── 1. Parse dos bytes ─────────────────────────────────────────
    try:
        uid = parse_uid(body["uid"])
    except UIDParseError as e:
        return _erro(str(e))

    db = get_db()

    # ── 2. É crachá de operador? ───────────────────────────────────
    operador = db.execute(
        "SELECT * FROM operadores WHERE uid_raw = ?", (uid["uid_raw"],)
    ).fetchone()

    if operador:
        return _registrar_sessao(db, operador, uid)

    # ── 3. É tag de ferramenta? ────────────────────────────────────
    ferramenta = db.execute(
        "SELECT * FROM ferramentas WHERE peca_code = ?", (uid["peca_code"],)
    ).fetchone()

    if ferramenta:
        return _registrar_movimentacao(db, ferramenta, uid)

    # ── 4. UID não cadastrado ──────────────────────────────────────
    return _erro(
        f"Tag não cadastrada. "
        f"Peça={uid['peca_code']} "
        f"Setor={uid['setor_nome']} "
        f"Unidade={uid['unidade_nome']}"
    ), 404


# ── Funções auxiliares ─────────────────────────────────────────────

def _registrar_sessao(db, operador, uid):
    """Abre sessão se não houver, ou encerra a sessão ativa."""
    sessao_ativa = db.execute(
        """SELECT * FROM sessoes
           WHERE operador_id = ? AND ativa = 1
           ORDER BY inicio DESC LIMIT 1""",
        (operador["id"],)
    ).fetchone()

    if sessao_ativa:
        # Encerra sessão (logout)
        db.execute(
            "UPDATE sessoes SET ativa = 0 WHERE id = ?",
            (sessao_ativa["id"],)
        )
        db.commit()
        return jsonify({
            "status": "ok",
            "tipo":   "operador",
            "msg":    f"Tchau, {operador['nome'].split()[0]}!",
            "acao":   "logout",
            "operador": {
                "id":       operador["id"],
                "nome":     operador["nome"],
                "matricula": operador["matricula"],
                "setor":    uid["setor_nome"],
                "unidade":  uid["unidade_nome"],
            }
        })
    else:
        # Abre nova sessão (login)
        db.execute(
            """INSERT INTO sessoes (operador_id, setor_codigo, unidade_codigo)
               VALUES (?, ?, ?)""",
            (operador["id"], uid["setor_code"], uid["unidade_code"])
        )
        db.commit()
        return jsonify({
            "status": "ok",
            "tipo":   "operador",
            "msg":    f"Ola, {operador['nome'].split()[0]}!",
            "acao":   "login",
            "operador": {
                "id":        operador["id"],
                "nome":      operador["nome"],
                "matricula": operador["matricula"],
                "setor":     uid["setor_nome"],
                "unidade":   uid["unidade_nome"],
            }
        })


def _registrar_movimentacao(db, ferramenta, uid):
    """Registra retirada ou devolução de uma ferramenta."""

    # Valida se setor/unidade do UID batem com o cadastro da ferramenta
    if ferramenta["setor_codigo"] != uid["setor_code"]:
        return _erro(
            f"Setor incorreto! "
            f"Ferramenta pertence ao setor código {ferramenta['setor_codigo']}, "
            f"mas o UID indica {uid['setor_nome']}."
        ), 409

    if ferramenta["unidade_codigo"] != uid["unidade_code"]:
        return _erro(
            f"Unidade incorreta! "
            f"Ferramenta pertence à unidade código {ferramenta['unidade_codigo']}, "
            f"mas o UID indica {uid['unidade_nome']}."
        ), 409

    # Busca operador com sessão ativa no mesmo setor/unidade
    sessao = db.execute(
        """SELECT s.*, o.nome as op_nome, o.id as op_id
           FROM sessoes s
           JOIN operadores o ON o.id = s.operador_id
           WHERE s.setor_codigo   = ?
             AND s.unidade_codigo = ?
             AND s.ativa = 1
           ORDER BY s.inicio DESC LIMIT 1""",
        (uid["setor_code"], uid["unidade_code"])
    ).fetchone()

    if not sessao:
        print(sessao)
        return _erro("Nenhum operador identificado. Passe o cracha primeiro."), 403

    # Define tipo da movimentação
    tipo = "devolucao" if ferramenta["disponivel"] == 0 else "retirada"
    nova_disp = 1 if tipo == "devolucao" else 0

    # Grava movimentação
    db.execute(
        """INSERT INTO movimentacoes
               (ferramenta_peca, operador_id, setor_codigo, unidade_codigo, tipo)
           VALUES (?, ?, ?, ?, ?)""",
        (
            ferramenta["peca_code"],
            sessao["op_id"],
            uid["setor_code"],
            uid["unidade_code"],
            tipo,
        )
    )

    # Atualiza disponibilidade
    db.execute(
        "UPDATE ferramentas SET disponivel = ? WHERE peca_code = ?",
        (nova_disp, ferramenta["peca_code"])
    )
    db.commit()

    emoji = "Retirada" if tipo == "retirada" else "Devolvida"
    return jsonify({
        "status": "ok",
        "tipo":   "ferramenta",
        "acao":   tipo,
        "msg":    f"{emoji}: {ferramenta['nome'][:20]}",
        "detalhes": {
            "ferramenta":  ferramenta["nome"],
            "categoria":   ferramenta["categoria"],
            "peca_code":   ferramenta["peca_code"],
            "operador":    sessao["op_nome"],
            "setor":       uid["setor_nome"],
            "unidade":     uid["unidade_nome"],
            "uid_bytes": {
                "B1+B2 (peca)":    f"{uid['b1']} {uid['b2']} → {uid['peca_code']}",
                "B3 (setor)":      f"{uid['b3']} → {uid['setor_nome']}",
                "B4 (unidade)":    f"{uid['b4']} → {uid['unidade_nome']}",
            }
        }
    })


def _erro(msg: str):
    return jsonify({"status": "erro", "tipo": None, "msg": msg})
