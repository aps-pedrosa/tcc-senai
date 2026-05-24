"""
uid_parser.py
─────────────────────────────────────────────────────────────────
Decodifica o UID RFID segundo a convenção do VoidLog v2.

  CONVENÇÃO DE IDENTIFICAÇÃO:
  A tag RFID é identificada pelo seu UID COMPLETO (todos os bytes),
  armazenado em uid_raw. Isso evita colisões entre tags de fabricantes
  diferentes que possam compartilhar os mesmos B1+B2.

  O peca_code (B1+B2) continua existindo como código numérico de
  referência da peça (útil para barcodes e cadastro manual), mas o
  lookup principal de crachás e peças RFID é feito pelo uid_raw completo.

  UID pode ser 4, 7 ou 10 bytes (ISO 14443A):
    uid_raw  = hex completo de todos os bytes (ex: "04A3F21B" para 4 bytes)
    peca_code = (B1 << 8) | B2  →  0–65535

  Crachás de operador seguem a mesma lógica:
    uid_raw completo identifica o operador no banco.
    Setor/unidade vêm do payload do terminal.
"""


class UIDParseError(ValueError):
    pass


def parse_uid(uid_hex: str) -> dict:
    """
    Recebe UID bruto do RC522 (string hex, mínimo 4 chars / 2 bytes).
    Retorna uid_raw completo, peca_code (B1+B2), e bytes individuais B1/B2.
    O uid_raw é o identificador primário — contém TODOS os bytes do UID.
    """
    uid_hex = uid_hex.strip().upper().replace(" ", "").replace(":", "")

    if len(uid_hex) < 4:
        raise UIDParseError(
            f"UID muito curto. Mínimo 4 chars hex (2 bytes). "
            f"Recebido: '{uid_hex}' ({len(uid_hex)} chars)"
        )
    if len(uid_hex) % 2 != 0:
        raise UIDParseError(f"UID com número ímpar de caracteres: '{uid_hex}'")

    try:
        b1 = int(uid_hex[0:2], 16)
        b2 = int(uid_hex[2:4], 16)
    except ValueError:
        raise UIDParseError(f"UID contém caracteres não-hexadecimais: '{uid_hex}'")

    peca_code = (b1 << 8) | b2

    return {
        "uid_raw":   uid_hex,          # UID completo — identificador primário
        "b1":        f"0x{b1:02X}",
        "b2":        f"0x{b2:02X}",
        "peca_code": peca_code,        # B1+B2 — referência numérica da peça
        "num_bytes": len(uid_hex) // 2,
    }


def uid_from_peca(peca_code: int) -> str:
    """Gera UID mínimo (4 bytes) a partir de peca_code. Útil para cadastro manual."""
    if not (0 <= peca_code <= 0xFFFF):
        raise UIDParseError("peca_code deve estar entre 0 e 65535")
    b1 = (peca_code >> 8) & 0xFF
    b2 = peca_code & 0xFF
    return f"{b1:02X}{b2:02X}"


def uid_from_parts(peca_code: int, setor_codigo: int = 0, unidade_codigo: int = 0,
                   setor_code: int = None, unidade_code: int = None) -> str:
    """Compatibilidade retroativa: gera UID de 4 bytes com B3+B4 zerados."""
    if not (0 <= peca_code <= 0xFFFF):
        raise UIDParseError("peca_code deve estar entre 0 e 65535")
    b1 = (peca_code >> 8) & 0xFF
    b2 = peca_code & 0xFF
    return f"{b1:02X}{b2:02X}0000"
