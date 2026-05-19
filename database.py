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
"""

import sqlite3

DB_PATH = "voidlog.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        -- ── Unidades (byte B4) ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS unidades (
            codigo      INTEGER PRIMARY KEY,   -- valor do byte B4 (0–255)
            nome        TEXT    NOT NULL UNIQUE
        );

        -- ── Setores (byte B3) ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS setores (
            codigo      INTEGER PRIMARY KEY,   -- valor do byte B3 (0–255)
            nome        TEXT    NOT NULL UNIQUE
        );

        -- ── Ferramentas (bytes B1+B2) ────────────────────────────────
        CREATE TABLE IF NOT EXISTS ferramentas (
            peca_code       INTEGER PRIMARY KEY,  -- B1<<8 | B2  (0–65535)
            uid_raw         TEXT    NOT NULL UNIQUE,
            nome            TEXT    NOT NULL,
            categoria       TEXT    NOT NULL,     -- ex: "Furação", "Corte"
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            quantidade      INTEGER NOT NULL DEFAULT 1,
            disponivel      INTEGER NOT NULL DEFAULT 1  -- 1=livre 0=em uso
        );

        -- ── Operadores (crachá RFID com mesma estrutura de bytes) ───
        CREATE TABLE IF NOT EXISTS operadores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            uid_raw         TEXT    NOT NULL UNIQUE,
            peca_code       INTEGER NOT NULL,     -- identifica o crachá
            setor_codigo    INTEGER NOT NULL REFERENCES setores(codigo),
            unidade_codigo  INTEGER NOT NULL REFERENCES unidades(codigo),
            nome            TEXT    NOT NULL,
            matricula       TEXT    NOT NULL UNIQUE
        );

        -- ── Sessão ativa (operador logado por terminal) ──────────────
        -- Um terminal físico (ESP32) pode ter ID próprio; aqui
        -- simplificamos: um operador ativo por vez por unidade+setor.
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
    conn.close()
    print("[VoidLog] Banco de dados inicializado.")
