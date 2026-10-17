"""Atualização automática pelas versões publicadas no GitHub.

Cada commit no ramo main gera uma versão (GitHub Actions) com o instalador NebulaOverlay-Setup.exe e o
arquivo .sha256 dele. O programa compara a versão dele com a mais nova, baixa o instalador, confere o
SHA-256 e roda o instalador em modo silencioso; o instalador fecha o programa, troca os arquivos e o
abre de novo. Só fala com api.github.com e com os downloads do próprio repositório.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request

from .versao import REPO, VERSAO

API = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALADOR = "NebulaOverlay-Setup.exe"
_AGENTE = {"User-Agent": "NebulaOverlay", "Accept": "application/vnd.github+json"}


def numeros(versao: str) -> tuple[int, ...]:
    """"v2026.10.17.4" → (2026, 10, 17, 4). "dev" → ()."""
    return tuple(int(n) for n in re.findall(r"\d+", versao or ""))


def de_desenvolvimento() -> bool:
    return not numeros(VERSAO)


def mais_nova() -> dict | None:
    """A versão publicada mais nova, se for mais nova que esta: {versao, instalador, sha256, notas}."""
    with urllib.request.urlopen(urllib.request.Request(API, headers=_AGENTE), timeout=8) as r:
        d = json.load(r)
    tag = d.get("tag_name", "")
    if not numeros(tag) or numeros(tag) <= numeros(VERSAO):
        return None
    ativos = {a["name"]: a["browser_download_url"] for a in d.get("assets", [])}
    if INSTALADOR not in ativos or INSTALADOR + ".sha256" not in ativos:
        return None
    return {"versao": tag.lstrip("v"), "instalador": ativos[INSTALADOR], "sha256": ativos[INSTALADOR + ".sha256"],
            "notas": d.get("body", "")}


def _do_repositorio(url: str) -> bool:
    return url.startswith(f"https://github.com/{REPO}/releases/download/")


def baixar(info: dict, progresso=None) -> str:
    """Baixa o instalador para a pasta temporária e confere o SHA-256. Devolve o caminho."""
    if not (_do_repositorio(info["instalador"]) and _do_repositorio(info["sha256"])):
        raise ValueError("endereço de download inesperado")
    with urllib.request.urlopen(urllib.request.Request(info["sha256"], headers=_AGENTE), timeout=15) as r:
        esperado = r.read().decode("ascii", "replace").split()[0].strip().lower()
    destino = os.path.join(tempfile.gettempdir(), f"NebulaOverlay-Setup-{info['versao']}.exe")
    h = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(info["instalador"], headers=_AGENTE), timeout=30) as r, \
            open(destino, "wb") as f:
        total, feito = int(r.headers.get("Content-Length") or 0), 0
        while True:
            bloco = r.read(1 << 16)
            if not bloco:
                break
            f.write(bloco)
            h.update(bloco)
            feito += len(bloco)
            if progresso and total:
                progresso(feito / total)
    if h.hexdigest() != esperado:
        os.remove(destino)
        raise ValueError("o arquivo baixado não confere (SHA-256)")
    return destino


def instalar(instalador: str) -> None:
    """Roda o instalador em modo silencioso, solto deste processo (ele fecha este programa e o reabre)."""
    DETACHED, SEM_JANELA = 0x00000008, 0x08000000
    subprocess.Popen([instalador, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     creationflags=DETACHED | SEM_JANELA, close_fds=True)
