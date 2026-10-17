"""Voz curta: palavras de ordem pré-gravadas em voz/<idioma>/*.wav (português, inglês e espanhol).

  python voz.py --listar            vozes instaladas no Windows
  python voz.py                     grava os áudios com a voz pt-BR do Windows (só os que faltam)
  python voz.py --refazer           grava tudo de novo (por exemplo, depois de trocar de voz)
  python voz.py --testar            toca todas as frases em sequência
  python voz.py --idioma en-US      o mesmo em inglês (pasta voz/en-US, voz inglesa do Windows)
  python voz.py --idioma es         o mesmo em espanhol (qualquer voz espanhola do Windows)

Por que pré-gravado: a fala sai na hora (sem esperar o sintetizador) e cada alerta vira uma
ordem de 1 a 3 palavras ("Sai!", "Empilha!", "Para de bater!"), em vez de uma frase longa.

A voz pt-BR vem do pacote de fala do Windows (Configurações → Hora e idioma → Fala →
Adicionar vozes → Português (Brasil)). Para usar a sua própria voz, grave um .wav com o
mesmo nome do arquivo em voz/ (por exemplo voz/sair.wav): arquivos que já existem não são
sobrescritos, só com --refazer.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

from a2parse.caminhos import usuario

PASTA_BASE = usuario("voz")
IDIOMA_PADRAO = "pt-BR"


def pasta_de(idioma: str = IDIOMA_PADRAO) -> str:
    return os.path.join(PASTA_BASE, idioma)


PASTA = pasta_de()

# chave do arquivo -> o que a voz fala
FRASES = {
    "sair": "Sai!",
    "sair_voce": "Em você! Sai!",
    "empilhar": "Empilha!",
    "empilhar_voce": "Em você! Fica parado!",
    "espalhar": "Espalha!",
    "pular": "Pula!",
    "esquivar": "Esquiva!",
    "borda": "Posição!",
    "atras": "Atrás dele!",
    "esconder": "Esconde!",
    "parar_dano": "Para de bater!",
    "stagger": "Quebra!",
    "matar_alvo": "Mata o add!",
    "enrage": "Enrage!",
    "burst": "Burst!",
    "segurar_burst": "Segura o burst!",
    "debuff": "Limpa!",
    "vira": "Vira ele!",
    "defesa": "Defesa!",
    "meio": "Pro meio!",
    "engajar": "Engaje!",
    "sai_zona": "Sai da zona!",
    "um": "Um",
    "dois": "Dois",
    "tres": "Três",
}

FRASES_EN = {
    "sair": "Move out!",
    "sair_voce": "On you! Move out!",
    "empilhar": "Stack!",
    "empilhar_voce": "On you! Stay put!",
    "espalhar": "Spread!",
    "pular": "Jump!",
    "esquivar": "Dodge!",
    "borda": "Position!",
    "atras": "Get behind!",
    "esconder": "Hide!",
    "parar_dano": "Stop attacking!",
    "stagger": "Break!",
    "matar_alvo": "Kill the add!",
    "enrage": "Enrage!",
    "burst": "Burst now!",
    "segurar_burst": "Hold burst!",
    "debuff": "Cleanse!",
    "vira": "Turn him!",
    "defesa": "Defense!",
    "meio": "To the middle!",
    "engajar": "Engage!",
    "sai_zona": "Leave the zone!",
    "um": "One",
    "dois": "Two",
    "tres": "Three",
}

FRASES_ES = {
    "sair": "¡Sal!",
    "sair_voce": "¡En ti! ¡Sal!",
    "empilhar": "¡Agrúpense!",
    "empilhar_voce": "¡En ti! ¡Quieto!",
    "espalhar": "¡Dispérsense!",
    "pular": "¡Salta!",
    "esquivar": "¡Esquiva!",
    "borda": "¡Posición!",
    "atras": "¡Detrás!",
    "esconder": "¡Escóndete!",
    "parar_dano": "¡Deja de golpear!",
    "stagger": "¡Rómpelo!",
    "matar_alvo": "¡Mata al add!",
    "enrage": "¡Enrage!",
    "burst": "¡Burst!",
    "segurar_burst": "¡Guarda el burst!",
    "debuff": "¡Limpia!",
    "vira": "¡Gíralo!",
    "defesa": "¡Defensa!",
    "meio": "¡Al centro!",
    "engajar": "¡Engancha!",
    "sai_zona": "¡Sal de la zona!",
    "um": "Uno",
    "dois": "Dos",
    "tres": "Tres",
}

FRASES_POR_IDIOMA = {"pt-BR": FRASES, "en-US": FRASES_EN, "es": FRASES_ES}
VOZ_DO_IDIOMA = {"pt": "pt-BR", "en": "en-US", "es": "es"}      # idioma da interface -> voz padrão


def frases_de(idioma: str) -> dict[str, str]:
    return FRASES_POR_IDIOMA.get(idioma) or FRASES_POR_IDIOMA.get(VOZ_DO_IDIOMA.get(idioma[:2], ""), FRASES)

# tipo de ação do alerta -> chave da frase (o que não está aqui não fala: avisos "info")
POR_TIPO = {t: t for t in ("sair", "empilhar", "espalhar", "pular", "esquivar", "borda", "atras", "esconder",
                           "parar_dano", "stagger", "matar_alvo", "enrage", "burst", "segurar_burst", "debuff",
                           "engajar")}


def chave_de(alerta) -> str | None:
    """Qual frase curta um alerta fala. "voz_curta" na mecânica (ou no passo) tem prioridade."""
    if getattr(alerta, "voz_curta", ""):
        return alerta.voz_curta
    chave = POR_TIPO.get(alerta.tipo)
    if chave and "VOCÊ" in (alerta.texto or "").upper() and f"{chave}_voce" in FRASES:
        return f"{chave}_voce"        # "POÇA EM VOCÊ: SAI" -> "Em você! Sai!"
    return chave


# ---------------- gravação com a voz do Windows ----------------

_PS = r'''
$ErrorActionPreference = 'Stop'
$itens = Get-Content -Raw -Encoding UTF8 $env:VOZ_ITENS | ConvertFrom-Json
$saida = $env:VOZ_SAIDA; $idioma = $env:VOZ_IDIOMA; $quer = $env:VOZ_NOME
$listar = $env:VOZ_LISTAR -eq '1'
$feito = $false
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime] | Out-Null
  [Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null
  $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
      $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  function Esperar($op, [Type]$t) { $k = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $k.Wait(-1) | Out-Null; $k.Result }
  $todas = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
  if ($listar) { $todas | ForEach-Object { "moderna | " + $_.DisplayName + " | " + $_.Language } }
  $v = $todas | Where-Object { $_.Language -like "$idioma*" -and (-not $quer -or $_.DisplayName -like "*$quer*") } | Select-Object -First 1
  if ($v -and -not $listar) {
    $s = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
    $s.Voice = $v
    try { $s.Options.SpeakingRate = [double]$env:VOZ_VELOCIDADE } catch {}
    foreach ($i in $itens) {
      $st = Esperar ($s.SynthesizeTextToStreamAsync($i.texto)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
      $r = New-Object Windows.Storage.Streams.DataReader($st.GetInputStreamAt(0))
      $n = Esperar ($r.LoadAsync([uint32]$st.Size)) ([uint32])
      $b = New-Object byte[] $n; $r.ReadBytes($b)
      [IO.File]::WriteAllBytes((Join-Path $saida ($i.chave + '.wav')), $b)
    }
    "OK " + $v.DisplayName; $feito = $true
  }
} catch { if ($listar) { "moderna | (nenhuma: " + $_.Exception.Message.Trim() + ")" } }
if (-not $feito) {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  if ($listar) { $s.GetInstalledVoices() | ForEach-Object { "antiga | " + $_.VoiceInfo.Name + " | " + $_.VoiceInfo.Culture.Name }; exit 0 }
  $v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like "$idioma*" -and (-not $quer -or $_.VoiceInfo.Name -like "*$quer*") } | Select-Object -First 1
  if (-not $v) { "SEM_VOZ"; exit 2 }
  $s.SelectVoice($v.VoiceInfo.Name)
  $s.Rate = [int](([double]$env:VOZ_VELOCIDADE - 1) * 10)
  foreach ($i in $itens) { $s.SetOutputToWaveFile((Join-Path $saida ($i.chave + '.wav'))); $s.Speak($i.texto) }
  $s.SetOutputToNull()
  "OK " + $v.VoiceInfo.Name
}
'''


def _powershell(itens: list[dict], saida: str, idioma: str, nome: str, velocidade: float, listar: bool) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        arq = os.path.join(tmp, "itens.json")
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(itens, f, ensure_ascii=False)
        amb = dict(os.environ, VOZ_ITENS=arq, VOZ_SAIDA=saida, VOZ_IDIOMA=idioma, VOZ_NOME=nome or "",
                   VOZ_VELOCIDADE=str(velocidade), VOZ_LISTAR="1" if listar else "0")
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS],
                           env=amb, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=0x08000000)      # sem janela de console (app instalado)
        return r.returncode, (r.stdout + r.stderr).strip()


def listar_vozes() -> str:
    return _powershell([], tempfile.gettempdir(), "", "", 1.0, True)[1]


def gravar(pasta: str | None = None, refazer: bool = False, idioma: str = IDIOMA_PADRAO, nome: str = "",
           velocidade: float = 1.15) -> tuple[bool, str]:
    """Grava as frases que faltam daquele idioma. Devolve (ok, mensagem)."""
    pasta = pasta or pasta_de(idioma)
    os.makedirs(pasta, exist_ok=True)
    itens = [{"chave": k, "texto": t} for k, t in frases_de(idioma).items()
             if refazer or not os.path.exists(os.path.join(pasta, f"{k}.wav"))]
    if not itens:
        return True, "todas as frases já estão gravadas"
    cod, saida = _powershell(itens, pasta, idioma, nome, velocidade, False)
    if cod == 2 or "SEM_VOZ" in saida:
        return False, (f"SEM_VOZ: não há voz {idioma} instalada no Windows (Configurações → Hora e idioma → Fala). "
                       f"Ou grave você mesmo os arquivos em {pasta}.")
    if cod != 0 or "OK" not in saida:
        return False, f"o Windows não conseguiu gravar: {saida[-300:]}"
    return True, f"{len(itens)} frases gravadas com {saida.split('OK', 1)[1].strip()}"


# ---------------- tocar ----------------

class VozCurta:
    """Toca as palavras de ordem na hora (winsound, assíncrono: uma fala nova corta a anterior)."""

    def __init__(self, pasta: str | None = None, idioma: str = IDIOMA_PADRAO) -> None:
        pasta = pasta or pasta_de(idioma)
        self.pasta = pasta
        self.arquivos = {k: os.path.join(pasta, f"{k}.wav") for k in FRASES
                         if os.path.exists(os.path.join(pasta, f"{k}.wav"))}

    @property
    def pronta(self) -> bool:
        return all(k in self.arquivos for k in ("sair", "empilhar", "um", "dois", "tres"))

    def falar(self, chave: str | None) -> bool:
        caminho = self.arquivos.get(chave or "")
        if not caminho:
            return False
        try:
            import winsound
            winsound.PlaySound(caminho, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return True
        except Exception:
            return False

    def contagem(self, ate: float) -> None:
        """Fala "três, dois, um" terminando em 'ate' (time.monotonic)."""
        def _c():
            for n, chave in ((3, "tres"), (2, "dois"), (1, "um")):
                espera = ate - n - time.monotonic()
                if espera < -0.5:
                    continue                  # esse número já passou
                if espera > 0:
                    time.sleep(espera)
                self.falar(chave)
        threading.Thread(target=_c, daemon=True).start()


def preparar(idioma: str = IDIOMA_PADRAO, avisar=print) -> VozCurta | None:
    """Para o overlay: garante os áudios do idioma (gravando os que faltam) e devolve o tocador, ou None."""
    v = VozCurta(idioma=idioma)
    if not v.pronta or set(frases_de(idioma)) - set(v.arquivos):   # frases novas: grava só as que faltam
        ok, msg = gravar(idioma=idioma)
        avisar(f"Voz ({idioma}): {msg}")
        v = VozCurta(idioma=idioma)
    return v if v.pronta else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Palavras de ordem do overlay (pt-BR, en-US, es).")
    ap.add_argument("--listar", action="store_true", help="vozes instaladas no Windows")
    ap.add_argument("--refazer", action="store_true", help="grava tudo de novo, mesmo o que já existe")
    ap.add_argument("--voz", default="", help="parte do nome da voz (ex.: Maria, Daniel)")
    ap.add_argument("--idioma", default=IDIOMA_PADRAO, choices=sorted(FRASES_POR_IDIOMA), help="pt-BR, en-US ou es")
    ap.add_argument("--velocidade", type=float, default=1.15, help="1 = normal")
    ap.add_argument("--pasta", default=None, help="padrão: voz/<idioma>")
    ap.add_argument("--testar", action="store_true", help="toca todas as frases")
    args = ap.parse_args()
    if args.listar:
        print(listar_vozes())
        return 0
    if args.testar:
        v = VozCurta(args.pasta, args.idioma)
        if not v.arquivos:
            print(f"Nenhum áudio em {v.pasta}: grave antes (python voz.py --idioma {args.idioma}).")
        for k, t in frases_de(args.idioma).items():
            print(f"{k:14s} {t}")
            if v.falar(k):
                time.sleep(1.1)
        return 0
    ok, msg = gravar(args.pasta, args.refazer, args.idioma, args.voz, args.velocidade)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
