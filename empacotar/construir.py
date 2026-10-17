"""Gera o app e o instalador do Nebula Overlay.

  python empacotar/construir.py                        app em dist/NebulaOverlay (versão "dev")
  python empacotar/construir.py --versao 2026.10.17.3  idem, com versão, e o instalador se houver Inno Setup

Saída: dist/NebulaOverlay/ (o app), dist/NebulaOverlay-Setup.exe e dist/NebulaOverlay-Setup.exe.sha256.
O GitHub Actions (.github/workflows/lancar.yml) roda isto a cada commit no main e publica a versão.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DIST = os.path.join(RAIZ, "dist")
VERSAO_PY = os.path.join(RAIZ, "a2parse", "versao.py")


def achar_iscc() -> str | None:
    candidatos = [shutil.which("ISCC"), shutil.which("iscc")]
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            candidatos += glob.glob(os.path.join(base, "Inno Setup*", "ISCC.exe"))
    return next((c for c in candidatos if c and os.path.exists(c)), None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--versao", help="ex.: 2026.10.17.3 (sem: dev, e sem instalador)")
    ap.add_argument("--sem-instalador", action="store_true")
    args = ap.parse_args()
    if args.versao and not re.fullmatch(r"\d+(\.\d+){1,3}", args.versao):
        sys.exit("Versão inválida: use números separados por ponto (ex.: 2026.10.17.3).")

    original = open(VERSAO_PY, encoding="utf-8").read()
    if args.versao:
        open(VERSAO_PY, "w", encoding="utf-8").write(
            re.sub(r'^VERSAO = ".*"$', f'VERSAO = "{args.versao}"', original, flags=re.M))
    try:
        trabalho = os.path.join(os.environ.get("TEMP", DIST), "nebula_overlay_build")
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST,
                        "--workpath", trabalho, os.path.join(AQUI, "NebulaOverlay.spec")], check=True)
    finally:
        open(VERSAO_PY, "w", encoding="utf-8").write(original)      # o código-fonte continua "dev"

    if not args.versao or args.sem_instalador:
        print(f"App em {os.path.join(DIST, 'NebulaOverlay')} (sem instalador).")
        return 0
    iscc = achar_iscc()
    if not iscc:
        print("Inno Setup não encontrado: só o app foi gerado (instale o Inno Setup 6 para gerar o instalador).")
        return 0
    subprocess.run([iscc, f"/DVersao={args.versao}", os.path.join(AQUI, "NebulaOverlay.iss")], check=True)
    instalador = os.path.join(DIST, "NebulaOverlay-Setup.exe")
    h = hashlib.sha256(open(instalador, "rb").read()).hexdigest()
    with open(instalador + ".sha256", "w", encoding="ascii") as f:
        f.write(f"{h}  NebulaOverlay-Setup.exe\n")
    print(f"Instalador: {instalador} ({os.path.getsize(instalador) / 1e6:.1f} MB)\nSHA-256: {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
