"""Onde ficam os arquivos.

- APP: o que vem com o programa (mecânicas, roteiros, símbolos, protocolo). No app instalado é a pasta
  do programa, só leitura (o instalador troca tudo a cada atualização).
- USUARIO: o que é seu (configurações, capturas, relatórios, vozes gravadas, roteiros aprendidos aqui).
  No app instalado é Documentos\\Nebula Overlay; a variável NEBULA_OVERLAY_PASTA troca o lugar.

Rodando do código-fonte, as duas são a pasta do projeto (como sempre foi).
"""

from __future__ import annotations

import os
import sys

NOME = "Nebula Overlay"
INSTALADO = bool(getattr(sys, "frozen", False))
APP = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _documentos() -> str:
    """Pasta Documentos de verdade (pode estar no OneDrive ou em outro disco)."""
    try:
        import ctypes as C
        import uuid
        guid = (C.c_ubyte * 16).from_buffer_copy(uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}").bytes_le)
        p = C.c_wchar_p()
        if C.windll.shell32.SHGetKnownFolderPath(C.byref(guid), 0, None, C.byref(p)) == 0:
            caminho = p.value
            C.windll.ole32.CoTaskMemFree(p)
            if caminho:
                return caminho
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


USUARIO = os.environ.get("NEBULA_OVERLAY_PASTA") or (os.path.join(_documentos(), NOME) if INSTALADO else APP)


def app(*partes: str) -> str:
    return os.path.join(APP, *partes)


def usuario(*partes: str) -> str:
    return os.path.join(USUARIO, *partes)


def pasta_usuario(*partes: str) -> str:
    """Como usuario(), mas cria a pasta se ainda não existir."""
    caminho = usuario(*partes)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def dados_jogo(nome: str) -> str | None:
    """Tabelas do jogo (nomes de NPCs e de skills) são opcionais e não vêm com o programa.
    Quem tiver as suas pode pôr em Documentos\\Nebula Overlay\\dados_jogo (ou em dados/ no código-fonte)."""
    for caminho in (usuario("dados_jogo", nome), app("dados", nome)):
        if os.path.exists(caminho):
            return caminho
    return None
