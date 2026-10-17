"""Fontes de eventos para o motor de alertas."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterator

from .analise import Analise


@dataclass(slots=True)
class Evento:
    t: float                  # segundos (tempo do vídeo ou timestamp da captura)
    tipo: str                 # "hp", "dano", "skill", "morte"
    entidade: int = 0         # alvo (hp, dano, morte) ou conjurador (skill)
    valor: float = 0.0        # HP absoluto, HP% (fonte de vídeo), dano ou skill_id
    origem: int = 0           # quem causou o dano
    boss: str | None = None   # só a fonte de vídeo já sabe o nome do boss


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def ler_tempo(s: str) -> float:
    p = s.split(":")
    return float(p[0]) * 60 + float(p[1]) if len(p) == 2 else float(s)


# ---------------- vídeo ----------------

def ler_curva_hp(caminho: str) -> list[tuple[float, float | None]]:
    """Lê o arquivo do medidor de barra: 't m:s hp' por linha (hp vazio = barra fora da tela)."""
    pontos = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            p = linha.split()
            if not p:
                continue
            pontos.append((float(p[0]), float(p[2]) if len(p) > 2 else None))
    return pontos


def suavizar(pontos: list[tuple[float, float | None]], janela: int = 9, desce_max: float = 4.0, sobe_max: float = 2.0):
    """Mediana móvel + limite de velocidade (em pontos de % por segundo).

    A barra medida no vídeo sofre com efeitos de skill passando por cima. O HP
    real de um boss não despenca 20% em meio segundo e nem volta logo depois,
    então quedas e subidas rápidas são tratadas como ruído.
    """
    saida, est, t_ant = [], None, None
    meia = janela // 2
    for i, (t, v) in enumerate(pontos):
        if v is None:
            saida.append((t, None))
            continue
        viz = [x for _, x in pontos[max(0, i - meia):i + meia + 1] if x is not None]
        med = statistics.median(viz)
        if est is None:
            est = med
        else:
            dt = max(0.01, t - t_ant)
            est += max(-desce_max * dt, min(sobe_max * dt, med - est))
        t_ant = t
        saida.append((t, round(est, 1)))
    return saida


def eventos_video(curva: str, lutas: list[dict], sumico_min: float = 1.0) -> Iterator[Evento]:
    """Eventos de HP% por luta, a partir da curva medida e das janelas de cada boss.

    Quando a barra de HP some por pelo menos `sumico_min` segundos no meio da luta,
    emite um evento "sumico" no instante em que ela sumiu (o boss saiu da tela).
    """
    pontos = ler_curva_hp(curva)
    for luta in lutas:
        ini, fim = ler_tempo(luta["inicio"]), ler_tempo(luta["fim"])
        trecho = suavizar([(t, v) for t, v in pontos if ini <= t <= fim])
        visto, sumiu_em = False, None
        for t, v in trecho:
            if v is None:
                if visto and sumiu_em is None:
                    sumiu_em = t
                continue
            if sumiu_em is not None and t - sumiu_em >= sumico_min:
                yield Evento(sumiu_em, "sumico", boss=luta["boss"])
            sumiu_em, visto = None, True
            yield Evento(t, "hp", 0, v, boss=luta["boss"])


# ---------------- captura ----------------

def eventos_pcap(caminho: str, porta: int | None = None) -> list[Evento]:
    """Eventos de HP, dano, skill e morte de uma .pcapng, em ordem de tempo."""
    eventos: list[Evento] = []

    def obs(ts, fluxo, prof, op, payload, resultado):
        if not resultado or resultado[0] != "ok":
            return
        c = resultado[1]
        if op == 0x8D00:
            eventos.append(Evento(ts, "hp", c["entidade"], c["hp"]))
        elif op in (0x3804, 0x3805):
            eventos.append(Evento(ts, "dano", c["alvo"], c["dano"], c["origem"]))
        elif op == 0x3802:
            eventos.append(Evento(ts, "skill", c["conjurador"], c["skill"], c["alvo"]))
        elif op == 0x3642:
            eventos.append(Evento(ts, "morte", c["entidade"]))

    Analise(porta=porta, observador=obs).processar_arquivo(caminho)
    eventos.sort(key=lambda e: e.t)
    return eventos
