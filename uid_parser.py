"""
uid_parser.py
─────────────────────────────────────────────────────────────────
Responsável por decodificar os 4 bytes do UID RFID segundo a
convenção do VoidLog:

  Byte 1 (B1)  ┐
               ├─► ID da peça/ferramenta  (2 bytes → 16 bits)
  Byte 2 (B2)  ┘
  Byte 3 (B3)  ──► Código do setor        (1 byte  →  8 bits)
  Byte 4 (B4)  ──► Código da unidade      (1 byte  →  8 bits)

Exemplo de UID: "A34F21BC"
  B1 = 0xA3  │
  B2 = 0x4F  │ → peca_code = 0xA34F = 41807
  B3 = 0x21  → setor_code  = 0x21  = 33  → "Usinagem"
  B4 = 0xBC  → unidade_code = 0xBC = 188  → "Unidade BH"
"""


# ── Tabelas de mapeamento ──────────────────────────────────────────

SETORES = {
    0x01: "Soldagem",
    0x02: "Corte",
    0x03: "Usinagem",
    0x04: "Furação",
    0x05: "Montagem",
    0x06: "Manutenção",
    0x07: "Almoxarifado",
    0x08: "Qualidade",
}

UNIDADES = {
    0x01: "Unidade Centro",
    0x02: "Unidade BH",
    0x03: "Unidade Contagem",
    0x04: "Unidade Betim",
    0x05: "Unidade Ibirité",
}


# ── Parser principal ───────────────────────────────────────────────

class UIDParseError(ValueError):
    """UID inválido ou fora do padrão esperado."""
    pass


def parse_uid(uid_hex: str) -> dict:
    """
    Recebe uma string hexadecimal de 8 chars (ex: "A34F21BC")
    e retorna um dicionário com os campos decodificados.

    Levanta UIDParseError se o UID for inválido.
    """
    uid_hex = uid_hex.strip().upper().replace(" ", "")

    if len(uid_hex) != 8:
        raise UIDParseError(
            f"UID deve ter exatamente 8 caracteres hex (4 bytes). "
            f"Recebido: '{uid_hex}' ({len(uid_hex)} chars)"
        )

    try:
        b1 = int(uid_hex[0:2], 16)
        b2 = int(uid_hex[2:4], 16)
        b3 = int(uid_hex[4:6], 16)
        b4 = int(uid_hex[6:8], 16)
    except ValueError:
        raise UIDParseError(f"UID contém caracteres não-hexadecimais: '{uid_hex}'")

    peca_code    = (b1 << 8) | b2          # 2 bytes → inteiro 0–65535
    setor_code   = b3                       # 1 byte  → inteiro 0–255
    unidade_code = b4                       # 1 byte  → inteiro 0–255

    setor_nome   = SETORES.get(setor_code,   f"Setor desconhecido (0x{b3:02X})")
    unidade_nome = UNIDADES.get(unidade_code, f"Unidade desconhecida (0x{b4:02X})")

    return {
        "uid_raw":      uid_hex,
        "b1":           f"0x{b1:02X}",
        "b2":           f"0x{b2:02X}",
        "b3":           f"0x{b3:02X}",
        "b4":           f"0x{b4:02X}",
        "peca_code":    peca_code,          # chave da ferramenta no banco
        "setor_code":   setor_code,
        "setor_nome":   setor_nome,
        "unidade_code": unidade_code,
        "unidade_nome": unidade_nome,
    }


def uid_from_parts(peca_code: int, setor_codigo: int, unidade_codigo: int, setor_code: int = None, unidade_code: int = None) -> str:
    setor_code   = setor_code   if setor_code   is not None else setor_codigo
    unidade_code = unidade_code if unidade_code is not None else unidade_codigo
    """
    Utilitário inverso: gera o UID a partir das partes.
    Útil para cadastrar ferramentas via interface web.

    peca_code    → 0–65535  (2 bytes)
    setor_code   → 0–255    (1 byte)
    unidade_code → 0–255    (1 byte)
    """
    if not (0 <= peca_code <= 0xFFFF):
        raise UIDParseError("peca_code deve estar entre 0 e 65535")
    if not (0 <= setor_code <= 0xFF):
        raise UIDParseError("setor_codigo deve estar entre 0 e 255")
    if not (0 <= unidade_code <= 0xFF):
        raise UIDParseError("unidade_codigo deve estar entre 0 e 255")

    b1 = (peca_code >> 8) & 0xFF
    b2 = peca_code & 0xFF
    return f"{b1:02X}{b2:02X}{setor_code:02X}{unidade_code:02X}"
