"""
routes/auth.py — VoidLog v3
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/auth/logs          → histórico de logins (admin)
GET  /api/auth/exportacoes   → histórico de exportações (admin)
GET  /api/configuracoes      → configurações do sistema
PUT  /api/configuracoes      → salva configurações
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, session
from database import get_db

auth_bp = Blueprint("auth", __name__)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _get_cfg(db):
    return {r["chave"]: r["valor"] for r in db.execute("SELECT chave,valor FROM configuracoes")}


def _require_admin():
    if session.get("perfil") != "admin":
        return jsonify({"erro": "Acesso negado"}), 403
    return None


# ── Login / Logout ───────────────────────────────────────────────────────────

@auth_bp.route("/auth/login", methods=["POST"])
def login():
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""
    ip    = request.headers.get("X-Forwarded-For", request.remote_addr or "")

    db  = get_db()
    row = db.execute(
        "SELECT * FROM usuarios WHERE email=? AND ativo=1", (email,)
    ).fetchone()

    if not row or row["senha_hash"] != _hash(senha):
        # Log falha
        db.execute(
            "INSERT INTO logs_login (usuario_id, email, sucesso, ip_address) VALUES (?,?,0,?)",
            (row["id"] if row else None, email, ip)
        )
        db.commit()
        return jsonify({"erro": "Credenciais inválidas"}), 401

    # Log sucesso
    db.execute(
        "INSERT INTO logs_login (usuario_id, email, sucesso, ip_address) VALUES (?,?,1,?)",
        (row["id"], email, ip)
    )
    db.execute(
        "UPDATE usuarios SET ultimo_login=? WHERE id=?",
        (datetime.now().isoformat(), row["id"])
    )
    db.commit()

    session["usuario_id"] = row["id"]
    session["nome"]       = row["nome"]
    session["email"]      = email
    session["perfil"]     = row["perfil"]

    # Alerta de login por e-mail
    cfg = _get_cfg(db)
    if cfg.get("email_alertas_habilitado") == "1" and cfg.get("email_alertas_login") == "1":
        try:
            from email_service import enviar_email
            destino = cfg.get("email_destino", "")
            if destino:
                enviar_email(cfg, destino,
                    f"[VoidLog] Login de {row['nome']}",
                    f"Usuário: {row['nome']} ({email})\nIP: {ip}\nHorário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        except Exception:
            pass

    return jsonify({"ok": True, "nome": row["nome"], "perfil": row["perfil"]})


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/auth/me", methods=["GET"])
def me():
    if "usuario_id" not in session:
        return jsonify({"autenticado": False}), 401
    return jsonify({
        "autenticado": True,
        "id":     session["usuario_id"],
        "nome":   session.get("nome"),
        "email":  session.get("email"),
        "perfil": session.get("perfil"),
    })


# ── Logs de login ─────────────────────────────────────────────────────────────

@auth_bp.route("/auth/logs", methods=["GET"])
def logs_login():
    err = _require_admin()
    if err: return err

    rows = get_db().execute("""
        SELECT l.*, u.nome AS usuario_nome
        FROM logs_login l
        LEFT JOIN usuarios u ON u.id = l.usuario_id
        ORDER BY l.horario DESC
        LIMIT 200
    """).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Histórico de exportações ─────────────────────────────────────────────────

@auth_bp.route("/auth/exportacoes", methods=["GET"])
def historico_exportacoes():
    err = _require_admin()
    if err: return err

    rows = get_db().execute("""
        SELECT e.*, u.nome AS usuario_nome, u.email AS usuario_email
        FROM exportacoes e
        LEFT JOIN usuarios u ON u.id = e.usuario_id
        ORDER BY e.horario DESC
        LIMIT 200
    """).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Configurações ─────────────────────────────────────────────────────────────

@auth_bp.route("/configuracoes", methods=["GET"])
def get_configuracoes():
    err = _require_admin()
    if err: return err
    cfg = _get_cfg(get_db())
    # não expõe senha
    cfg.pop("email_smtp_pass", None)
    return jsonify(cfg)


@auth_bp.route("/configuracoes", methods=["PUT"])
def set_configuracoes():
    err = _require_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    db   = get_db()
    for chave, valor in data.items():
        db.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?,?)",
            (chave, str(valor))
        )
    db.commit()
    return jsonify({"ok": True})


# ── Usuários web ──────────────────────────────────────────────────────────────

@auth_bp.route("/usuarios", methods=["GET"])
def listar_usuarios():
    err = _require_admin()
    if err: return err
    rows = get_db().execute(
        "SELECT id,nome,email,perfil,ativo,criado_em,ultimo_login FROM usuarios ORDER BY nome"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@auth_bp.route("/usuarios", methods=["POST"])
def criar_usuario():
    err = _require_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    for campo in ["nome", "email", "senha"]:
        if not data.get(campo):
            return jsonify({"erro": f"{campo} obrigatório"}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO usuarios (nome,email,senha_hash,perfil) VALUES (?,?,?,?)",
            (data["nome"], data["email"].lower(),
             _hash(data["senha"]), data.get("perfil", "visualizador"))
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409
    return jsonify({"ok": True}), 201


@auth_bp.route("/usuarios/<int:uid>", methods=["PUT"])
def editar_usuario(uid):
    err = _require_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    db   = get_db()
    campos, valores = [], []
    for campo in ["nome", "perfil"]:
        if campo in data:
            campos.append(f"{campo}=?"); valores.append(data[campo])
    if "senha" in data and data["senha"]:
        campos.append("senha_hash=?"); valores.append(_hash(data["senha"]))
    if "ativo" in data:
        campos.append("ativo=?"); valores.append(1 if data["ativo"] else 0)

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400
    valores.append(uid)
    db.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id=?", valores)
    db.commit()
    return jsonify({"ok": True})
