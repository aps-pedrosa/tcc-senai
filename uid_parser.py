"""
uid_parser.py
─────────────────────────────────────────────────────────────────
Decodifica o UID RFID segundo a nova convenção do VoidLog v2:

  NOVA CONVENÇÃO:
  A tag RFID contém APENAS o ID da peça (peca_code).
  Setor e unidade NÃO estão na tag — são informados pelo terminal
  (ESP32) via payload JSON, selecionados pelo funcionário no encoder.

  UID pode ser 4, 7 ou 10 bytes (ISO 14443A):
    Os primeiros 2 bytes (B1+B2) formam o peca_code (0–65535).
    Bytes restantes são preservados como uid_raw (rastreabilidade física).

  Crachás de operador seguem a mesma lógica:
    peca_code = B1+B2 → identifica o operador no banco.
    Setor/unidade vêm do payload do terminal.
"""


class UIDParseError(ValueError):
    pass


def parse_uid(uid_hex: str) -> dict:
    """
    Recebe UID bruto do RC522 (string hex, min 4 chars).
    Extrai peca_code dos primeiros 2 bytes.
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
        "uid_raw":   uid_hex,
        "b1":        f"0x{b1:02X}",
        "b2":        f"0x{b2:02X}",
        "peca_code": peca_code,
    }


def uid_from_peca(peca_code: int) -> str:
    if not (0 <= peca_code <= 0xFFFF):
        raise UIDParseError("peca_code deve estar entre 0 e 65535")
    b1 = (peca_code >> 8) & 0xFF
    b2 = peca_code & 0xFF
    return f"{b1:02X}{b2:02X}"


def uid_from_parts(peca_code: int, setor_codigo: int = 0, unidade_codigo: int = 0,
                   setor_code: int = None, unidade_code: int = None) -> str:
    """Compatibilidade: B3 e B4 zerados, setor/unidade não ficam na tag."""
    if not (0 <= peca_code <= 0xFFFF):
        raise UIDParseError("peca_code deve estar entre 0 e 65535")
    b1 = (peca_code >> 8) & 0xFF
    b2 = peca_code & 0xFF
    return f"{b1:02X}{b2:02X}0000"
