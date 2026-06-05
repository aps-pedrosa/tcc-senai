"""
database.py — VoidLog v2
─────────────────────────────────────────────────────────────────
Mudanças v2:
  - pecas: removidos setor_codigo/unidade_codigo fixos.
    Adicionados: localizacao_setor, localizacao_unidade (posição atual),
    ultimo_operador_id (último responsável), ultima_mov (timestamp).
  - operadores: removidos setor_codigo/unidade_codigo (não pertencem
    a setor fixo — terminal define o contexto).
  - sessoes: terminal_id identifica o ESP32 físico.
  - movimentacoes: setor/unidade registrados no momento da leitura
    (contexto do terminal, não da tag).
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
        -- ── Unidades ────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS unidades (
            codigo  INTEGER PRIMARY KEY,
            nome    TEXT    NOT NULL UNIQUE
        );

        -- ── Setores ─────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS setores (
            codigo  INTEGER PRIMARY KEY,
            nome    TEXT    NOT NULL UNIQUE
        );

        -- ── Peças ──────────────────────────────────────────────
        -- peca_code = B1+B2 do UID (identificação física da tag).
        -- Setor/unidade NÃO são fixos: a peca pode ser usada em
        -- qualquer local. Localização atual é atualizada a cada mov.
        CREATE TABLE IF NOT EXISTS pecas (
            peca_code           INTEGER PRIMARY KEY,
            uid_raw             TEXT    NOT NULL UNIQUE,
            nome                TEXT    NOT NULL,
            categoria           TEXT    NOT NULL,
            quantidade          INTEGER NOT NULL DEFAULT 1,
            peso                REAL,
            disponivel          INTEGER NOT NULL DEFAULT 1,
            -- Localização atual (última movimentação)
            localizacao_setor   INTEGER REFERENCES setores(codigo),
            localizacao_unidade INTEGER REFERENCES unidades(codigo),
            ultimo_operador_id  INTEGER REFERENCES operadores(id),
            ultima_mov          DATETIME
        );

        -- ── Operadores ───────────────────────────────────────────────
        -- Operador identificado pelo uid_raw do crachá (B1+B2 = peca_code).
        -- Não tem setor/unidade fixo — o terminal define o contexto.
        CREATE TABLE IF NOT EXISTS operadores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid_raw     TEXT    NOT NULL UNIQUE,
            peca_code   INTEGER NOT NULL,
            nome        TEXT    NOT NULL,
            matricula   TEXT    NOT NULL UNIQUE
        );

        -- ── Sessões de operador por terminal ─────────────────────────
        -- terminal_id identifica o ESP32 (string livre, ex: "ESP-A1B2C3").
        -- setor/unidade = contexto selecionado no encoder no momento do login.
        CREATE TABLE IF NOT EXISTS sessoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            operador_id     INTEGER NOT NULL REFERENCES operadores(id),
            terminal_id     TEXT    NOT NULL DEFAULT 'default',
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            inicio          DATETIME DEFAULT CURRENT_TIMESTAMP,
            ativa           INTEGER NOT NULL DEFAULT 1
        );

        -- ── Movimentações ────────────────────────────────────────────
        -- setor/unidade = contexto do terminal no momento da leitura.
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            peca_peca INTEGER NOT NULL REFERENCES pecas(peca_code),
            operador_id     INTEGER NOT NULL REFERENCES operadores(id),
            terminal_id     TEXT    NOT NULL DEFAULT 'default',
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            tipo            TEXT    NOT NULL CHECK(tipo IN ('retirada','devolucao')),
            horario         DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Usuários do dashboard web ────────────────────────────────
        CREATE TABLE IF NOT EXISTS usuarios (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT    NOT NULL,
            email       TEXT    NOT NULL UNIQUE,
            senha_hash  TEXT    NOT NULL,
            perfil      TEXT    NOT NULL DEFAULT 'visualizador'
                                CHECK(perfil IN ('admin','operador','visualizador')),
            ativo       INTEGER NOT NULL DEFAULT 1,
            criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultimo_login DATETIME
        );

        -- ── Sessões web ───────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS sessoes_web (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            token       TEXT    NOT NULL UNIQUE,
            criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP,
            expira_em   DATETIME NOT NULL,
            expirado    INTEGER NOT NULL DEFAULT 0
        );

        -- ── Terminais (ESP32) ───────────────────────────────────────
        -- Cada ESP32 se registra automaticamente pelo terminal_id (MAC).
        -- status: 'pendente' | 'aprovado' | 'rejeitado'
        -- Admin aprova/rejeita pelo dashboard. Apenas aprovados recebem config.
        CREATE TABLE IF NOT EXISTS terminais (
            terminal_id     TEXT    PRIMARY KEY,
            apelido         TEXT,
            status          TEXT    NOT NULL DEFAULT 'pendente'
                                    CHECK(status IN ('pendente','aprovado','rejeitado')),
            setor_codigo    INTEGER REFERENCES setores(codigo),
            unidade_codigo  INTEGER REFERENCES unidades(codigo),
            ultimo_acesso   DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address      TEXT,
            firmware_ver    TEXT    DEFAULT '3.0'
        );

        -- ── Seeds ────────────────────────────────────────────────────
        INSERT OR IGNORE INTO unidades VALUES
            (1,'Unidade Centro'),(2,'Unidade BH'),(3,'Unidade Contagem'),
            (4,'Unidade Betim'),(5,'Unidade Ibirité');

        INSERT OR IGNORE INTO setores VALUES
            (1,'Soldagem'),(2,'Corte'),(3,'Usinagem'),(4,'Furação'),
            (5,'Montagem'),(6,'Manutenção'),(7,'Almoxarifado'),(8,'Qualidade');
    """)
    conn.commit()

    # Migrações seguras para bancos existentes
    _migrate(conn)

    # Admin padrão
    admin = conn.execute("SELECT id FROM usuarios WHERE email='admin@voidlog.local'").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO usuarios (nome,email,senha_hash,perfil) VALUES (?,?,?,?)",
            ("Administrador", "admin@voidlog.local", _hash("admin123"), "admin")
        )
        conn.commit()
        print("[VoidLog] Usuário admin criado: admin@voidlog.local / admin123")

    conn.close()
    print("[VoidLog] Banco de dados inicializado.")


def _migrate(conn):
    """
    Migra bancos existentes para o schema v2 sem perder dados.
    Executado automaticamente no init_db().
    """
    conn.execute("PRAGMA foreign_keys = OFF")

    # ── operadores v2: remove setor_codigo/unidade_codigo obrigatórios ──
    cols_o = {r[1] for r in conn.execute("PRAGMA table_info(operadores)")}
    if "setor_codigo" in cols_o:
        conn.execute("""CREATE TABLE IF NOT EXISTS operadores_v2 (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            uid_raw   TEXT    NOT NULL UNIQUE,
            peca_code INTEGER NOT NULL,
            nome      TEXT    NOT NULL,
            matricula TEXT    NOT NULL UNIQUE
        )""")
        conn.execute("INSERT OR IGNORE INTO operadores_v2 (id,uid_raw,peca_code,nome,matricula) SELECT id,uid_raw,peca_code,nome,matricula FROM operadores")
        conn.execute("DROP TABLE operadores")
        conn.execute("ALTER TABLE operadores_v2 RENAME TO operadores")

    # ── pecas v2: remove setor_codigo/unidade_codigo obrigatórios ──
    cols_f = {r[1] for r in conn.execute("PRAGMA table_info(pecas)")}
    if "setor_codigo" in cols_f:
        conn.execute("""CREATE TABLE IF NOT EXISTS pecas_v2 (
            peca_code           INTEGER PRIMARY KEY,
            uid_raw             TEXT    NOT NULL UNIQUE,
            nome                TEXT    NOT NULL,
            categoria           TEXT    NOT NULL,
            quantidade          INTEGER NOT NULL DEFAULT 1,
            disponivel          INTEGER NOT NULL DEFAULT 1,
            localizacao_setor   INTEGER,
            localizacao_unidade INTEGER,
            ultimo_operador_id  INTEGER,
            ultima_mov          DATETIME
        )""")
        conn.execute("""INSERT OR IGNORE INTO pecas_v2
            SELECT peca_code,uid_raw,nome,categoria,quantidade,disponivel,
                   localizacao_setor,localizacao_unidade,ultimo_operador_id,ultima_mov
            FROM pecas""")
        conn.execute("DROP TABLE pecas")
        conn.execute("ALTER TABLE pecas_v2 RENAME TO pecas")
    else:
        # Banco já é v2 — apenas adiciona colunas de localização se faltarem
        for col, typ in [("localizacao_setor","INTEGER"),("localizacao_unidade","INTEGER"),
                         ("ultimo_operador_id","INTEGER"),("ultima_mov","DATETIME"),
                         ("peso","REAL")]:
            if col not in cols_f:
                conn.execute(f"ALTER TABLE pecas ADD COLUMN {col} {typ}")

    # ── sessoes: adiciona terminal_id ────────────────────────────────────
    cols_s = {r[1] for r in conn.execute("PRAGMA table_info(sessoes)")}
    if "terminal_id" not in cols_s:
        conn.execute("ALTER TABLE sessoes ADD COLUMN terminal_id TEXT NOT NULL DEFAULT 'default'")

    # ── movimentacoes: adiciona terminal_id ──────────────────────────────
    cols_m = {r[1] for r in conn.execute("PRAGMA table_info(movimentacoes)")}
    if "terminal_id" not in cols_m:
        conn.execute("ALTER TABLE movimentacoes ADD COLUMN terminal_id TEXT NOT NULL DEFAULT 'default'")

    # ── terminais: garante coluna status ─────────────────────────────────
    cols_t = {r[1] for r in conn.execute("PRAGMA table_info(terminais)")}
    if "status" not in cols_t:
        conn.execute("ALTER TABLE terminais ADD COLUMN status TEXT NOT NULL DEFAULT 'pendente'")
    if "firmware_ver" not in cols_t:
        conn.execute("ALTER TABLE terminais ADD COLUMN firmware_ver TEXT DEFAULT '3.0'")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
