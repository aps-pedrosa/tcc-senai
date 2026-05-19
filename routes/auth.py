"""
routes/auth.py
─────────────────────────────────────────────────────────────────
Sistema de autenticação do VoidLog.

POST /api/auth/login    → autentica usuário, retorna token de sessão
POST /api/auth/logout   → encerra sessão
GET  /api/auth/me       → retorna dados do usuário logado
GET  /api/usuarios      → lista usuários (admin only)
POST /api/usuarios      → cria usuário (admin only)
PUT  /api/usuarios/<id> → edita usuário (admin only)
DELETE /api/usuarios/<id> → remove usuário (admin only)
"""

import hashlib
import secrets
import functools
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from database import get_db

auth_bp = Blueprint("auth", __name__)

# ── Helpers ────────────────────────────────────────────────────────

def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()

def requer_login(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Auth-Token") or request.cookies.get("voidlog_token")
        if not token:
            return jsonify({"erro": "Não autenticado"}), 401
        db = get_db()
        sess = db.execute(
            """SELECT s.*, u.id as uid, u.nome, u.email, u.perfil, u.ativo
               FROM sessoes_web s JOIN usuarios u ON u.id = s.usuario_id
               WHERE s.token = ? AND s.expirado = 0
               AND s.expira_em > CURRENT_TIMESTAMP""",
            (token,)
        ).fetchone()
        if not sess:
            return jsonify({"erro": "Sessão inválida ou expirada"}), 401
        request.usuario = dict(sess)
        return f(*args, **kwargs)
    return decorated

def requer_admin(f):
    @functools.wraps(f)
    @requer_login
    def decorated(*args, **kwargs):
        if request.usuario.get("perfil") != "admin":
            return jsonify({"erro": "Acesso negado. Requer perfil admin."}), 403
        return f(*args, **kwargs)
    return decorated

# ── Login ──────────────────────────────────────────────────────────

@auth_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    senha = data.get("senha", "")

    if not email or not senha:
        return jsonify({"erro": "Email e senha são obrigatórios"}), 400

    db = get_db()
    usuario = db.execute(
        "SELECT * FROM usuarios WHERE email = ? AND ativo = 1",
        (email,)
    ).fetchone()

    if not usuario or usuario["senha_hash"] != hash_senha(senha):
        return jsonify({"erro": "Credenciais inválidas"}), 401

    token = secrets.token_hex(32)
    expira = datetime.now() + timedelta(hours=8)

    db.execute(
        """INSERT INTO sessoes_web (usuario_id, token, expira_em)
           VALUES (?, ?, ?)""",
        (usuario["id"], token, expira.isoformat())
    )
    db.execute(
        "UPDATE usuarios SET ultimo_login = CURRENT_TIMESTAMP WHERE id = ?",
        (usuario["id"],)
    )
    db.commit()

    resp = jsonify({
        "ok": True,
        "token": token,
        "usuario": {
            "id":     usuario["id"],
            "nome":   usuario["nome"],
            "email":  usuario["email"],
            "perfil": usuario["perfil"],
        }
    })
    resp.set_cookie("voidlog_token", token, httponly=True, samesite="Lax", max_age=28800)
    return resp

# ── Logout ─────────────────────────────────────────────────────────

@auth_bp.route("/auth/logout", methods=["POST"])
@requer_login
def logout():
    token = request.headers.get("X-Auth-Token") or request.cookies.get("voidlog_token")
    db = get_db()
    db.execute("UPDATE sessoes_web SET expirado = 1 WHERE token = ?", (token,))
    db.commit()
    resp = jsonify({"ok": True})
    resp.delete_cookie("voidlog_token")
    return resp

# ── Me ─────────────────────────────────────────────────────────────

@auth_bp.route("/auth/me", methods=["GET"])
@requer_login
def me():
    u = request.usuario
    return jsonify({
        "id":           u["uid"],
        "nome":         u["nome"],
        "email":        u["email"],
        "perfil":       u["perfil"],
    })

# ── CRUD de Usuários (admin only) ──────────────────────────────────

@auth_bp.route("/usuarios", methods=["GET"])
@requer_admin
def listar_usuarios():
    rows = get_db().execute(
        "SELECT id, nome, email, perfil, ativo, criado_em, ultimo_login FROM usuarios ORDER BY nome"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@auth_bp.route("/usuarios", methods=["POST"])
@requer_admin
def criar_usuario():
    data = request.get_json(silent=True) or {}
    for campo in ["nome", "email", "senha", "perfil"]:
        if campo not in data:
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    if data["perfil"] not in ("admin", "operador", "visualizador"):
        return jsonify({"erro": "Perfil inválido. Use: admin, operador, visualizador"}), 422

    db = get_db()
    try:
        db.execute(
            """INSERT INTO usuarios (nome, email, senha_hash, perfil)
               VALUES (?, ?, ?, ?)""",
            (data["nome"], data["email"].lower(), hash_senha(data["senha"]), data["perfil"])
        )
        db.commit()
    except Exception as e:
        return jsonify({"erro": str(e)}), 409

    return jsonify({"ok": True, "mensagem": f"Usuário {data['nome']} criado com sucesso"}), 201


@auth_bp.route("/usuarios/<int:uid>", methods=["PUT"])
@requer_admin
def editar_usuario(uid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if not usuario:
        return jsonify({"erro": "Usuário não encontrado"}), 404

    campos = []
    valores = []
    if "nome" in data:
        campos.append("nome = ?"); valores.append(data["nome"])
    if "email" in data:
        campos.append("email = ?"); valores.append(data["email"].lower())
    if "perfil" in data:
        if data["perfil"] not in ("admin", "operador", "visualizador"):
            return jsonify({"erro": "Perfil inválido"}), 422
        campos.append("perfil = ?"); valores.append(data["perfil"])
    if "ativo" in data:
        campos.append("ativo = ?"); valores.append(1 if data["ativo"] else 0)
    if "senha" in data and data["senha"]:
        campos.append("senha_hash = ?"); valores.append(hash_senha(data["senha"]))

    if not campos:
        return jsonify({"erro": "Nada para atualizar"}), 400

    valores.append(uid)
    db.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id = ?", valores)
    db.commit()
    return jsonify({"ok": True, "mensagem": "Usuário atualizado"})


@auth_bp.route("/usuarios/<int:uid>", methods=["DELETE"])
@requer_admin
def deletar_usuario(uid):
    if uid == request.usuario["uid"]:
        return jsonify({"erro": "Você não pode remover sua própria conta"}), 400
    db = get_db()
    db.execute("UPDATE usuarios SET ativo = 0 WHERE id = ?", (uid,))
    db.commit()
    return jsonify({"ok": True, "mensagem": "Usuário desativado"})
