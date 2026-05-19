"""
database.py
─────────────────────────────────────────────────────────────────
Cria e expõe a conexão com o SQLite.

Tabelas:
  unidades      → mapeamento do byte B4
  setores       → mapeamento do byte B3
  ferramentas   → identificadas pelo peca_code (B1+B2)
  operadores    → crachás RFID (mesma estrutura de bytes)
  sessoes       → operador ativo por unidade/setor
  movimentacoes → histórico completo de retiradas e devoluções
  usuarios      → contas de acesso ao dashboard web
  sessoes_web   → tokens de autenticação do dashboard
"""

import sqlite3
import hashlib

DB_PATH = "voidlog.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def init_db():
    conn = get_db()
    conn.executescript("""
        -- ── Unidades (byte B4) ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS unidades (
            codigo      INTEGER PRIMARY KEY,
            nome        TEXT    NOT NULL UNIQUE
        );

        -- ── Setores (byte B3) ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS setores (
            codigo      INTEGER PRIMARY KEY,
            nome        TEXT    NOT NULL UNIQUE
        );

        -- ── Ferramentas (bytes B1+B2) ────────────────────────────────
        CREATE TABLE IF NOT EXISTS ferramentas (
            peca_code       INTEGER PRIMARY KEY,
            uid_raw         TEXT    NOT NULL UNIQUE,
            nome            TEXT    NOT NULL,
            categoria       TEXT    NOT NULL,
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            quantidade      INTEGER NOT NULL DEFAULT 1,
            disponivel      INTEGER NOT NULL DEFAULT 1
        );

        -- ── Operadores (crachá RFID) ─────────────────────────────────
        CREATE TABLE IF NOT EXISTS operadores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            uid_raw         TEXT    NOT NULL UNIQUE,
            peca_code       INTEGER NOT NULL,
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            nome            TEXT    NOT NULL,
            matricula       TEXT    NOT NULL UNIQUE
        );

        -- ── Sessão ativa de operador por terminal ────────────────────
        CREATE TABLE IF NOT EXISTS sessoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            operador_id     INTEGER NOT NULL REFERENCES operadores(id),
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            inicio          DATETIME DEFAULT CURRENT_TIMESTAMP,
            ativa           INTEGER NOT NULL DEFAULT 1
        );

        -- ── Movimentações ────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ferramenta_peca INTEGER NOT NULL REFERENCES ferramentas(peca_code),
            operador_id     INTEGER NOT NULL REFERENCES operadores(id),
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            tipo            TEXT    NOT NULL CHECK(tipo IN ('retirada','devolucao')),
            horario         DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Usuários do dashboard web ────────────────────────────────
        CREATE TABLE IF NOT EXISTS usuarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nome            TEXT    NOT NULL,
            email           TEXT    NOT NULL UNIQUE,
            senha_hash      TEXT    NOT NULL,
            perfil          TEXT    NOT NULL DEFAULT 'visualizador'
                                    CHECK(perfil IN ('admin','operador','visualizador')),
            ativo           INTEGER NOT NULL DEFAULT 1,
            criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultimo_login    DATETIME
        );

        -- ── Sessões web (tokens de autenticação) ─────────────────────
        CREATE TABLE IF NOT EXISTS sessoes_web (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
            token           TEXT    NOT NULL UNIQUE,
            criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
            expira_em       DATETIME NOT NULL,
            expirado        INTEGER NOT NULL DEFAULT 0
        );

        -- ── Dados iniciais de unidades ───────────────────────────────
        INSERT OR IGNORE INTO unidades VALUES
            (1, 'Unidade Centro'),
            (2, 'Unidade BH'),
            (3, 'Unidade Contagem'),
            (4, 'Unidade Betim'),
            (5, 'Unidade Ibirité');

        -- ── Dados iniciais de setores ────────────────────────────────
        INSERT OR IGNORE INTO setores VALUES
            (1,  'Soldagem'),
            (2,  'Corte'),
            (3,  'Usinagem'),
            (4,  'Furação'),
            (5,  'Montagem'),
            (6,  'Manutenção'),
            (7,  'Almoxarifado'),
            (8,  'Qualidade');
    """)
    conn.commit()

    # Cria usuário admin padrão se não existir
    admin = conn.execute("SELECT id FROM usuarios WHERE email = 'admin@voidlog.local'").fetchone()
    if not admin:
        conn.execute(
            """INSERT INTO usuarios (nome, email, senha_hash, perfil)
               VALUES (?, ?, ?, ?)""",
            ("Administrador", "admin@voidlog.local", _hash("admin123"), "admin")
        )
        conn.commit()
        print("[VoidLog] Usuário admin criado: admin@voidlog.local / admin123")

    conn.close()
    print("[VoidLog] Banco de dados inicializado.")
