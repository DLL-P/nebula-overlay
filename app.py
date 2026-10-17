"""Ponto de entrada do NebulaOverlay.exe (PyInstaller): um executável para o app e as ferramentas.

  NebulaOverlay.exe [opções]            o app (o mesmo que python overlay.py)
  NebulaOverlay.exe roteiros            reaprende a linha do tempo dos bosses (roteiros.py)
  NebulaOverlay.exe relatorio [captura] relatório pós-run (relatorio.py; padrão: a captura mais recente)
  NebulaOverlay.exe voz [--testar]      grava/toca as frases de voz (voz.py)
  NebulaOverlay.exe mapear …            tabela de skills de um boss (mapear.py)

O app instalado não tem console: o que ele escreveria vai para nebula.log, na pasta do usuário
(Documentos/Nebula Overlay).
"""

from __future__ import annotations

import importlib
import sys

FERRAMENTAS = ("roteiros", "relatorio", "voz", "mapear")


def _log_em_arquivo() -> None:
    """Sem console (app instalado), print e erros vão para nebula.log, na pasta do usuário."""
    if sys.stdout is not None:
        return
    from a2parse.caminhos import pasta_usuario
    import os
    caminho = os.path.join(pasta_usuario(), "nebula.log")
    try:
        if os.path.getsize(caminho) > 2_000_000:          # não deixa o log crescer sem fim
            os.replace(caminho, caminho + ".1")
    except OSError:
        pass
    sys.stdout = sys.stderr = open(caminho, "a", encoding="utf-8", buffering=1)


def main() -> int:
    _log_em_arquivo()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    nome = sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1] in FERRAMENTAS else "overlay"
    return importlib.import_module(nome).main() or 0


if __name__ == "__main__":
    sys.exit(main())
