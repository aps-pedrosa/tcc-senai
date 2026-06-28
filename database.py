"""
database.py — VoidLog v3
─────────────────────────────────────────────────────────────────
Mudanças v3:
  - Renomeação: "peça" → "equipamento" em todo o sistema
  - equipamentos: adicionado campo 'descricao' e 'em_manutencao'
  - manutencoes: nova tabela de histórico de manutenções
  - exportacoes: histórico de exportações de relatórios
  - logs_login: registro de logins do dashboard web
  - configuracoes: tabela de configurações do sistema (email, alertas)
  - terminais: adicionado tipo 'manutencao'
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

        -- ── Equipamentos ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS equipamentos (
            equipamento_code    INTEGER PRIMARY KEY,
            uid_raw             TEXT    NOT NULL UNIQUE,
            nome                TEXT    NOT NULL,
            categoria           TEXT    NOT NULL,
            descricao           TEXT,
            quantidade          INTEGER NOT NULL DEFAULT 1,
            peso                REAL,
            disponivel          INTEGER NOT NULL DEFAULT 1,
            em_manutencao       INTEGER NOT NULL DEFAULT 0,
            localizacao_setor   INTEGER REFERENCES setores(codigo),
            localizacao_unidade INTEGER REFERENCES unidades(codigo),
            ultimo_operador_id  INTEGER REFERENCES operadores(id),
            ultima_mov          DATETIME
        );

        -- ── Operadores ───────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS operadores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid_raw     TEXT    NOT NULL UNIQUE,
            equipamento_code INTEGER NOT NULL,
            nome        TEXT    NOT NULL,
            matricula   TEXT    NOT NULL UNIQUE
        );

        -- ── Sessões de operador por terminal ─────────────────────────
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
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            equipamento_code    INTEGER NOT NULL REFERENCES equipamentos(equipamento_code),
            operador_id         INTEGER NOT NULL REFERENCES operadores(id),
            terminal_id         TEXT    NOT NULL DEFAULT 'default',
            setor_codigo        INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo      INTEGER NOT NULL REFERENCES unidades(codigo),
            tipo                TEXT    NOT NULL CHECK(tipo IN ('retirada','devolucao')),
            horario             DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Manutenções ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS manutencoes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            equipamento_code    INTEGER NOT NULL REFERENCES equipamentos(equipamento_code),
            tipo                TEXT    NOT NULL CHECK(tipo IN ('entrada','saida')),
            descricao           TEXT,
            tecnico             TEXT,
            terminal_id         TEXT    NOT NULL DEFAULT 'default',
            horario             DATETIME DEFAULT CURRENT_TIMESTAMP
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

        -- ── Logs de login web ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS logs_login (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER REFERENCES usuarios(id),
            email       TEXT    NOT NULL,
            sucesso     INTEGER NOT NULL DEFAULT 1,
            ip_address  TEXT,
            horario     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Terminais (ESP32) ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS terminais (
            terminal_id     TEXT    PRIMARY KEY,
            apelido         TEXT,
            tipo            TEXT    NOT NULL DEFAULT 'normal'
                                    CHECK(tipo IN ('normal','manutencao')),
            status          TEXT    NOT NULL DEFAULT 'pendente'
                                    CHECK(status IN ('pendente','aprovado','rejeitado')),
            setor_codigo    INTEGER REFERENCES setores(codigo),
            unidade_codigo  INTEGER REFERENCES unidades(codigo),
            ultimo_acesso   DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address      TEXT,
            firmware_ver    TEXT    DEFAULT '3.0'
        );

        -- ── Exportações ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS exportacoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            formato     TEXT    NOT NULL CHECK(formato IN ('pdf','csv')),
            filtros     TEXT,
            total_linhas INTEGER,
            horario     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ── Configurações do sistema ─────────────────────────────────
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave   TEXT PRIMARY KEY,
            valor   TEXT
        );

        -- ── Seeds ────────────────────────────────────────────────────
        INSERT OR IGNORE INTO unidades VALUES
            (1,'Unidade Centro'),(2,'Unidade BH'),(3,'Unidade Contagem'),
            (4,'Unidade Betim'),(5,'Unidade Ibirité');

        INSERT OR IGNORE INTO setores VALUES
            (1,'Soldagem'),(2,'Corte'),(3,'Usinagem'),(4,'Furação'),
            (5,'Montagem'),(6,'Manutenção'),(7,'Almoxarifado'),(8,'Qualidade');

        INSERT OR IGNORE INTO configuracoes VALUES
            ('email_alertas_habilitado','0'),
            ('email_alertas_login','0'),
            ('email_smtp_host',''),
            ('email_smtp_port','587'),
            ('email_smtp_user',''),
            ('email_smtp_pass',''),
            ('email_destino','');
    """)
    conn.commit()

    _migrate(conn)

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
    conn.execute("PRAGMA foreign_keys = OFF")

    existing_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # ── Migra pecas → equipamentos ────────────────────────────────────────
    if "pecas" in existing_tables and "equipamentos" not in existing_tables:
        cols_p = {r[1] for r in conn.execute("PRAGMA table_info(pecas)")}
        conn.execute("""CREATE TABLE IF NOT EXISTS equipamentos (
            equipamento_code    INTEGER PRIMARY KEY,
            uid_raw             TEXT    NOT NULL UNIQUE,
            nome                TEXT    NOT NULL,
            categoria           TEXT    NOT NULL,
            descricao           TEXT,
            quantidade          INTEGER NOT NULL DEFAULT 1,
            peso                REAL,
            disponivel          INTEGER NOT NULL DEFAULT 1,
            em_manutencao       INTEGER NOT NULL DEFAULT 0,
            localizacao_setor   INTEGER,
            localizacao_unidade INTEGER,
            ultimo_operador_id  INTEGER,
            ultima_mov          DATETIME
        )""")
        # Tenta mapear coluna peca_code ou equipamento_code
        src_code = "peca_code" if "peca_code" in cols_p else "equipamento_code"
        conn.execute(f"""INSERT OR IGNORE INTO equipamentos
            (equipamento_code,uid_raw,nome,categoria,quantidade,disponivel,
             localizacao_setor,localizacao_unidade,ultimo_operador_id,ultima_mov)
            SELECT {src_code},uid_raw,nome,categoria,quantidade,disponivel,
                   localizacao_setor,localizacao_unidade,ultimo_operador_id,ultima_mov
            FROM pecas""")

    # ── Migra movimentacoes peca_peca → equipamento_code ────────────────
    if "movimentacoes" in existing_tables:
        cols_m = {r[1] for r in conn.execute("PRAGMA table_info(movimentacoes)")}
        if "peca_peca" in cols_m and "equipamento_code" not in cols_m:
            conn.execute("ALTER TABLE movimentacoes ADD COLUMN equipamento_code INTEGER")
            conn.execute("UPDATE movimentacoes SET equipamento_code = peca_peca")
        if "terminal_id" not in cols_m:
            conn.execute("ALTER TABLE movimentacoes ADD COLUMN terminal_id TEXT NOT NULL DEFAULT 'default'")

    # ── Migra operadores peca_code → equipamento_code ───────────────────
    if "operadores" in existing_tables:
        cols_o = {r[1] for r in conn.execute("PRAGMA table_info(operadores)")}
        if "peca_code" in cols_o and "equipamento_code" not in cols_o:
            conn.execute("ALTER TABLE operadores ADD COLUMN equipamento_code INTEGER")
            conn.execute("UPDATE operadores SET equipamento_code = peca_code")
        if "setor_codigo" in cols_o:
            conn.execute("""CREATE TABLE IF NOT EXISTS operadores_v2 (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                uid_raw   TEXT    NOT NULL UNIQUE,
                equipamento_code INTEGER NOT NULL,
                nome      TEXT    NOT NULL,
                matricula TEXT    NOT NULL UNIQUE
            )""")
            conn.execute("""INSERT OR IGNORE INTO operadores_v2 (id,uid_raw,equipamento_code,nome,matricula)
                SELECT id,uid_raw,COALESCE(equipamento_code,peca_code,0),nome,matricula FROM operadores""")
            conn.execute("DROP TABLE operadores")
            conn.execute("ALTER TABLE operadores_v2 RENAME TO operadores")

    # ── Colunas novas em equipamentos ────────────────────────────────────
    if "equipamentos" in existing_tables:
        cols_e = {r[1] for r in conn.execute("PRAGMA table_info(equipamentos)")}
        for col, typ in [("descricao","TEXT"),("em_manutencao","INTEGER NOT NULL DEFAULT 0"),
                         ("peso","REAL"),("localizacao_setor","INTEGER"),
                         ("localizacao_unidade","INTEGER"),("ultimo_operador_id","INTEGER"),
                         ("ultima_mov","DATETIME")]:
            if col not in cols_e:
                conn.execute(f"ALTER TABLE equipamentos ADD COLUMN {col} {typ}")

    # ── Tabela manutencoes ───────────────────────────────────────────────
    if "manutencoes" not in existing_tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS manutencoes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            equipamento_code    INTEGER NOT NULL,
            tipo                TEXT    NOT NULL CHECK(tipo IN ('entrada','saida')),
            descricao           TEXT,
            tecnico             TEXT,
            terminal_id         TEXT    NOT NULL DEFAULT 'default',
            horario             DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

    # ── Tabela exportacoes ───────────────────────────────────────────────
    if "exportacoes" not in existing_tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS exportacoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL,
            formato     TEXT    NOT NULL CHECK(formato IN ('pdf','csv')),
            filtros     TEXT,
            total_linhas INTEGER,
            horario     DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

    # ── Tabela logs_login ────────────────────────────────────────────────
    if "logs_login" not in existing_tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS logs_login (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER,
            email       TEXT    NOT NULL,
            sucesso     INTEGER NOT NULL DEFAULT 1,
            ip_address  TEXT,
            horario     DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

    # ── Tabela configuracoes ─────────────────────────────────────────────
    if "configuracoes" not in existing_tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS configuracoes (
            chave   TEXT PRIMARY KEY,
            valor   TEXT
        )""")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_alertas_habilitado','0')")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_alertas_login','0')")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_smtp_host','')")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_smtp_port','587')")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_smtp_user','')")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_smtp_pass','')")
    conn.execute("INSERT OR IGNORE INTO configuracoes VALUES ('email_destino','')")

    # ── Coluna tipo em terminais ─────────────────────────────────────────
    if "terminais" in existing_tables:
        cols_t = {r[1] for r in conn.execute("PRAGMA table_info(terminais)")}
        if "tipo" not in cols_t:
            conn.execute("ALTER TABLE terminais ADD COLUMN tipo TEXT NOT NULL DEFAULT 'normal'")
        if "status" not in cols_t:
            conn.execute("ALTER TABLE terminais ADD COLUMN status TEXT NOT NULL DEFAULT 'pendente'")
        if "firmware_ver" not in cols_t:
            conn.execute("ALTER TABLE terminais ADD COLUMN firmware_ver TEXT DEFAULT '3.0'")

    # ── Coluna em sessoes ────────────────────────────────────────────────
    if "sessoes" in existing_tables:
        cols_s = {r[1] for r in conn.execute("PRAGMA table_info(sessoes)")}
        if "terminal_id" not in cols_s:
            conn.execute("ALTER TABLE sessoes ADD COLUMN terminal_id TEXT NOT NULL DEFAULT 'default'")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
