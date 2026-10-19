"""Gera as vozes que vêm com o app (voz_padrao/<voz>/*.wav) com o Piper (https://github.com/rhasspy/piper, MIT).

  python empacotar/gerar_vozes.py --piper C:/caminho/piper.exe --modelos C:/pasta/com/os/.onnx

As frases saem da seção "voz" de cada idiomas/<código>.json; a voz de cada idioma está em VOZES abaixo.
Para um idioma novo: baixe um modelo de licença livre (veja o MODEL_CARD em huggingface.co/rhasspy/piper-voices),
acrescente-o em VOZES e em voz_padrao/CREDITOS.md, e rode de novo.
"""

from __future__ import annotations

import argparse
import array
import json
import os
import subprocess
import sys
import tempfile
import wave

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

# código da voz no app -> modelo do Piper (dados de licença livre; créditos em voz_padrao/CREDITOS.md)
VOZES = {
    "pt-BR": "pt_BR-faber-medium",
    "en-US": "en_US-joe-medium",
    "es": "es_MX-claude-high",
}
VELOCIDADE = 0.85      # length_scale do Piper: < 1 fala mais rápido (aviso de combate)
PICO = 0.85            # o Piper normaliza no máximo; um pouco abaixo evita estourar no fone


def ajustar_volume(caminho: str) -> None:
    with wave.open(caminho) as w:
        params, a = w.getparams(), array.array("h", w.readframes(w.getnframes()))
    maior = max((abs(x) for x in a), default=0)
    if maior:
        fator = PICO * 32767 / maior
        a = array.array("h", (int(x * fator) for x in a))
    with wave.open(caminho, "wb") as w:
        w.setparams(params)
        w.writeframes(a.tobytes())


def main() -> int:
    from a2parse import idioma
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--piper", required=True, help="piper.exe")
    ap.add_argument("--modelos", required=True, help="pasta com os .onnx e .onnx.json")
    ap.add_argument("--faltando", action="store_true", help="só as frases que ainda não têm áudio (o Piper varia a cada geração)")
    args = ap.parse_args()
    for voz, modelo in VOZES.items():
        saida = os.path.join(RAIZ, "voz_padrao", voz)
        os.makedirs(saida, exist_ok=True)
        frases = idioma.frases(voz)
        if args.faltando:
            frases = {k: t for k, t in frases.items() if not os.path.exists(os.path.join(saida, f"{k}.wav"))}
            if not frases:
                continue
        linhas = "\n".join(json.dumps({"text": t, "output_file": os.path.join(saida, f"{k}.wav")}, ensure_ascii=False)
                           for k, t in frases.items())
        with tempfile.TemporaryDirectory():
            r = subprocess.run([args.piper, "--model", os.path.join(args.modelos, modelo + ".onnx"), "--json-input",
                                "--length_scale", str(VELOCIDADE), "--sentence_silence", "0.05"],
                               input=linhas.encode("utf-8"), capture_output=True)
        if r.returncode:
            sys.exit(f"Piper falhou em {modelo}: {r.stderr.decode(errors='replace')[-300:]}")
        for k in frases:
            ajustar_volume(os.path.join(saida, f"{k}.wav"))
        print(f"{voz}: {len(frases)} frases com {modelo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
