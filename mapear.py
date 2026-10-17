"""Mapeia as skills dos bosses de uma captura, para ligar cada mecânica do mecanicas.json a um ID.

  python mapear.py capturas/aovivo_2026-10-20_22-01-13.pcap
  python mapear.py capturas/X.pcap --boss Auldor --linha          linha do tempo de todos os casts
  python mapear.py capturas/X.pcap --video-inicio 01:40:50        hora local em que o vídeo começou:
                                                                 mostra o tempo do vídeo de cada cast

Para cada skill que o boss usa, mostra:
- quantas vezes e quando (tempo da captura e, se der, do vídeo);
- intervalo típico entre casts e o HP do boss no momento;
- em quem mirou (nele mesmo, um jogador, ninguém);
- quantos jogadores levaram dano dela nos 4 s seguintes e o maior golpe:
  um acerto em 1 jogador com dano alto é agarrão/marca, em todos é AoE de sala;
- se já está mapeada no mecanicas.json (e em qual mecânica);
- skills que vêm sempre juntas (A seguida de B em até 15 s), para montar sequências;
- o preparo (0x3809): quanto antes do cast o boss anuncia a skill. Esse é o aviso prévio
  que vai em "preparo_s" no gatilho (ver docs/MAPEAR_BOSS.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import Counter, defaultdict
from statistics import median

from a2parse.alertas import carregar_mecanicas
from a2parse.analise import Analise
from a2parse.aovivo import Sessao, ler_eu
from a2parse.captura import ler_segmentos


def mmss(s: float) -> str:
    sinal = "-" if s < 0 else ""
    s = abs(s)
    return f"{sinal}{int(s // 60)}:{s % 60:05.2f}"


def json_curto(d: dict) -> str:
    return "{" + ", ".join(f'"{k}": {v}' for k, v in d.items()) + "}"


def mapeadas(dados: dict, boss: str) -> dict[int, str]:
    saida = {}
    for mz in dados["masmorras"]:
        for b in mz["bosses"]:
            if b["nome"] != boss:
                continue
            for m in b["mecanicas"]:
                g = m.get("gatilho") or {}
                for s in g.get("skill_ids") or []:
                    saida[s] = m.get("id", m["nome"])
                for p in m.get("sequencia", []):
                    for s in (p.get("sync") or {}).get("ids", []):
                        saida.setdefault(s, m.get("id", m["nome"]) + " (sync)")
    return saida


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Skills dos bosses numa captura.")
    ap.add_argument("captura")
    ap.add_argument("--boss", help="parte do nome do boss")
    ap.add_argument("--linha", action="store_true", help="linha do tempo de todos os casts")
    ap.add_argument("--video-inicio", help="hora local (HH:MM:SS) em que o vídeo começou a gravar")
    ap.add_argument("--json", metavar="ARQ", help="grava os casts (tempo da captura e do vídeo) para extrair quadros")
    args = ap.parse_args()

    dados = carregar_mecanicas()
    sessao = Sessao(dados, burst=False)
    jogadores: set[int] = set()
    casts: dict[int, list] = defaultdict(list)          # boss -> [(ts, skill, alvo)]
    golpes: dict[int, list] = defaultdict(list)         # boss -> [(ts, skill, alvo, dano)]
    preparos: dict[int, list] = defaultdict(list)       # boss -> [(ts, skill)] do 0x3809
    hp_boss: dict[int, list] = defaultdict(list)

    def observar(ts, fluxo, prof, op, payload, resultado):
        sessao._observar(ts, fluxo, prof, op, payload, resultado)
        if op == 0x3633:
            r = ler_eu(payload)
            if r:
                jogadores.add(r[0])
        if not resultado or resultado[0] != "ok":
            return
        c = resultado[1]
        if op == 0x3802 and c["conjurador"] in sessao.bosses:
            casts[c["conjurador"]].append((ts, c["skill"], c["alvo"]))
        elif op == 0x3809 and c["conjurador"] in sessao.bosses:
            preparos[c["conjurador"]].append((ts, c["skill"]))
        elif op == 0x3804 and c.get("origem") in sessao.bosses and c.get("alvo") != c.get("origem"):
            golpes[c["origem"]].append((ts, c["skill"], c["alvo"], c["dano"]))
        elif op == 0x3804 and c.get("alvo") in sessao.bosses:
            jogadores.add(c["origem"])
        elif op == 0x8D00 and c["entidade"] in sessao.bosses:
            hp_boss[c["entidade"]].append((ts, sessao.bosses[c["entidade"]].pct))

    sessao.analise = Analise(observador=observar)
    print("Lendo a captura…")
    t0 = None
    for seg in ler_segmentos(args.captura):
        t0 = t0 or seg.ts
        sessao.segmento(seg)
    jogadores |= set(sessao.nomes)

    desloc_video = None
    if args.video_inicio and t0:
        h, m, s = (int(x) for x in args.video_inicio.split(":"))
        ini = dt.datetime.fromtimestamp(t0)
        desloc_video = (ini.replace(hour=h, minute=m, second=s) - ini).total_seconds()
        print(f"O vídeo começou {desloc_video:+.0f} s depois da captura.")

    def quando(ts: float) -> str:
        t = mmss(ts - t0)
        return f"{t} (vídeo {mmss(ts - t0 - desloc_video)})" if desloc_video is not None else t

    def hp_em(ent: int, ts: float) -> float | None:
        antes = [p for t, p in hp_boss[ent] if t <= ts]
        return antes[-1] if antes else None

    saida_json: dict = {}
    for ent, b in sessao.bosses.items():
        if args.boss and args.boss.lower() not in b.nome.lower():
            continue
        lista = casts.get(ent, [])
        saida_json[b.nome] = [{"t": round(ts - t0, 2), "video": round(ts - t0 - desloc_video, 2) if desloc_video is not None else None,
                               "skill": s, "alvo": "ele" if a == ent else "jogador" if a in jogadores else a}
                              for ts, s, a in lista]
        if not lista:
            continue
        ja = mapeadas(dados, b.nome)
        print(f"\n━━ {b.nome} (entidade {ent}) ━━  {len(lista)} casts, {len(set(s for _, s, _ in lista))} skills")
        print("  skill       ×  1º cast            interv.   HP 1º   alvo          jogadores/cast  maior golpe  preparo      mapeada")
        sugestao = {}
        por_skill: dict[int, list] = defaultdict(list)
        for ts, s, alvo in lista:
            por_skill[s].append((ts, alvo))
        for s, ocorr in sorted(por_skill.items(), key=lambda x: x[1][0][0]):
            tempos = [t for t, _ in ocorr]
            interv = f"{median(b - a for a, b in zip(tempos, tempos[1:])):.0f}s" if len(tempos) > 1 else "—"
            alvos = Counter("ele mesmo" if a == ent else "jogador" if a in jogadores else "nenhum" if not a else "outro"
                            for _, a in ocorr)
            alvo_txt = alvos.most_common(1)[0][0]
            # dano em jogadores nos 4 s seguintes, por skills de ID próximo (o golpe costuma ter o ID do cast ou vizinho)
            atingidos, maior = [], 0
            for t, _ in ocorr:
                hits = [(a, d) for tt, ss, a, d in golpes[ent] if t <= tt <= t + 4 and abs(ss - s) <= 20 and a in jogadores]
                atingidos.append(len({a for a, _ in hits}))
                maior = max([maior] + [d for _, d in hits])
            hp = hp_em(ent, tempos[0])
            # preparo: o último 0x3809 da mesma skill até 6 s antes de cada cast
            atrasos = []
            for t in tempos:
                antes = [tp for tp, sp in preparos[ent] if sp == s and 0 < t - tp <= 6]
                if antes:
                    atrasos.append(t - max(antes))
            prep = "—"
            if atrasos:
                prep = f"{median(atrasos):.2f}s"
                if len(atrasos) < len(tempos):
                    prep += f" {len(atrasos)}/{len(tempos)}"
                elif max(atrasos) - min(atrasos) <= 0.1:
                    sugestao[s] = round(median(atrasos), 2)
            print(f"  {s:<10} {len(ocorr):>3}  {quando(tempos[0]):<18} {interv:>6}  "
                  f"{(f'{hp:.0f}%' if hp is not None else '—'):>6}   {alvo_txt:<12} "
                  f"{(f'{median(atingidos):.0f}' if atingidos else '—'):>8}      {maior:>10,}  {prep:<11}  "
                  f"{ja.get(s, '')}".replace(",", "."))
        if sugestao:
            print("  preparo estável (use em \"preparo_s\"): " + json_curto(sugestao))
        # pares que se repetem: A sempre seguida de B
        pares, atrasos_par = Counter(), defaultdict(list)
        for i, (ta, sa, _) in enumerate(lista):
            vistos = set()
            for tb, sb, _ in lista[i + 1:]:
                if tb - ta > 15:
                    break
                if sb != sa and sb not in vistos:
                    vistos.add(sb)
                    pares[(sa, sb)] += 1
                    atrasos_par[(sa, sb)].append(tb - ta)
        fortes = [(p, n) for p, n in pares.items() if n >= 2 and n >= 0.8 * len(por_skill[p[0]])]
        if fortes:
            print("  sequências (A → B em até 15 s, em ≥80% das vezes):")
            for (a, bb), n in sorted(fortes, key=lambda x: -x[1])[:10]:
                print(f"    {a} → {bb}  ({n}×, +{median(atrasos_par[(a, bb)]):.2f} s)")
        if args.linha:
            print("  linha do tempo:")
            for ts, s, alvo in lista:
                quem = "ele" if alvo == ent else (sessao.nomes.get(alvo) or ("você" if alvo in jogadores else str(alvo)))
                print(f"    {quando(ts):<22} {s:<10} → {quem:<14} {ja.get(s, '')}")
    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(saida_json, f, ensure_ascii=False, indent=1)
        print(f"\nCasts gravados em {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
