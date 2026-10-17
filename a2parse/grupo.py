"""Perfil dos jogadores do grupo: classe, nível, GS (gear score) e CP (poder de combate).

Vem na lista do grupo (0x9702, a cada mudança no grupo ou na sala) e quando alguém entra na sala (0x970B).
Cada jogador:

  u8 0x1E | u8 posição | u32 ID | u16 0 | u16 servidor | u8 tamanho + nome (UTF-8) | u32 classe | u32 nível |
  u32 GS | [u8 opcional] | u16 servidor (de novo) | u16 | u8 | u64 CP | u64 | u8 | u8

O byte opcional depois do GS só aparece em alguns jogadores; o servidor repetido logo depois serve de âncora.
O CP é o mesmo número que o jogo mostra no perfil (o "maior" do 0x3656 para você).
"""

from __future__ import annotations

import re
import struct

from .classes import PC_CLASSES

_REGISTRO = re.compile(rb"\x1e[\x00-\x0f](.{4})\x00\x00(..)([\x01-\x30])", re.S)


def ler_perfis(p: bytes) -> list[dict]:
    """Jogadores de um 0x9702 / 0x970B, na ordem do grupo. Registro que não fecha é ignorado."""
    saida, vistos = [], set()
    for m in _REGISTRO.finditer(p):
        n, i = m.group(3)[0], m.end()
        try:
            nome = p[i:i + n].decode("utf-8")
            classe_id, nivel, gs = struct.unpack_from("<III", p, i + n)
        except (UnicodeDecodeError, struct.error):
            continue
        if not nome.isprintable() or classe_id not in PC_CLASSES or not 1 <= nivel <= 99 or not 0 < gs < 100_000:
            continue
        j = i + n + 12
        servidor = m.group(2)
        k = j if p[j:j + 2] == servidor else j + 1 if p[j + 1:j + 3] == servidor else None
        if k is None:
            continue
        try:
            (cp,) = struct.unpack_from("<Q", p, k + 5)
        except struct.error:
            continue
        if not 0 < cp < 100_000_000 or nome in vistos:
            continue
        vistos.add(nome)
        saida.append({"nome": nome, "id": struct.unpack("<I", m.group(1))[0], "servidor": struct.unpack("<H", servidor)[0],
                      "classe": PC_CLASSES[classe_id], "nivel": nivel, "gs": gs, "cp": cp})
    return saida
