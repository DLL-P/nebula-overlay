"""Bipes dos alertas (quando a voz está desligada ou não há áudio para aquela ação)."""

from __future__ import annotations

import threading

SOM = {  # (frequência Hz, duração ms) por som da categoria
    "dois_tons_subindo": [(523, 140), (784, 200)], "dois_tons_descendo": [(784, 140), (523, 200)],
    "bipe_curto": [(880, 110)], "bipe_curto_duplo": [(880, 90), (880, 90)],
    "alarme": [(988, 110)] * 3, "tambor": [(220, 250), (220, 250)], "sino": [(1318, 350)], "clique": [(1500, 40)],
}


def tocar(som: str) -> None:
    try:
        import winsound
    except ImportError:
        return

    def _t():
        for f, ms in SOM.get(som, SOM["clique"]):
            winsound.Beep(f, ms)
    threading.Thread(target=_t, daemon=True).start()
