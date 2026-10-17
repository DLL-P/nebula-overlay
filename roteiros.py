"""Aprende a linha do tempo dos bosses com as capturas gravadas (mecanicas/roteiros.json).

  python roteiros.py                    usa todas as capturas de capturas/
  python roteiros.py capturas/X.pcap …  só as indicadas

Para cada boss: a cadeia de skills (o que vem depois do quê e quantos segundos depois), as
fases por HP e os ciclos de intervalo fixo. Quanto mais runs, melhor a previsão: rode depois
de cada masmorra (ou com dois cliques em roteiros.bat).
"""

from __future__ import annotations

import glob
import os
import sys
from collections import defaultdict

from a2parse.alertas import carregar_mecanicas
from a2parse.analise import Analise
from a2parse.aovivo import Sessao
from a2parse.captura import ler_segmentos
from a2parse.caminhos import usuario
from a2parse.roteiro import CAMINHO_LOCAL, aprender, carregar, precisao_roteiro, salvar


def casts_da_captura(caminho: str, dados: dict) -> dict[str, list]:
    """{boss: [(tempo, skill, HP%)]} de uma captura (uma luta por boss)."""
    s = Sessao(dados, antecipar=0.0)
    lutas: dict[str, list] = defaultdict(list)

    def observar(ts, fluxo, prof, op, payload, res):
        s._observar(ts, fluxo, prof, op, payload, res)
        if op == 0x3802 and res and res[0] == "ok" and res[1]["conjurador"] in s.bosses:
            b = s.bosses[res[1]["conjurador"]]
            lutas[b.nome].append((ts, res[1]["skill"], b.pct))

    s.analise = Analise(observador=observar)
    for seg in ler_segmentos(caminho):
        s.segmento(seg)
    return lutas


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    arquivos = argv or sorted(glob.glob(usuario("capturas", "*.pcap*")))
    arquivos = [a for a in arquivos if os.path.getsize(a) > 1_000_000]       # ignora capturas vazias
    if not arquivos:
        print("Nenhuma captura em capturas/. Jogue uma masmorra com o overlay aberto e rode de novo.")
        return 1
    dados = carregar_mecanicas()
    por_boss: dict[str, list] = defaultdict(list)
    for a in arquivos:
        print(f"Lendo {os.path.basename(a)}…", flush=True)
        for nome, casts in casts_da_captura(a, dados).items():
            if len(casts) >= 10:
                por_boss[nome].append(casts)
    fichas = {b["nome"]: b for mz in dados["masmorras"] for b in mz["bosses"]}
    roteiros = {}
    for nome, runs in por_boss.items():
        ficha = fichas.get(nome, {"nome": nome, "mecanicas": []})
        r = aprender(runs, ficha)
        r["precisao_centro"], r["previsoes_testadas"] = precisao_roteiro(runs, ficha)
        r["precisao_centro"] = round(r["precisao_centro"], 2)
        roteiros[nome] = r
        fases = ", ".join(f"{f['no']} ({f['vez']}ª) a {f['hp']}%" for f in r["fases_hp"]) or "nenhuma"
        print(f"\n{nome}: {len(runs)} runs · {len(r['cadeia'])} elos na cadeia · fases por HP: {fases}"
              f" · ciclos: {r['ciclos'] or 'nenhum'}")
        centro = "sobe para o centro" if r["precisao_centro"] >= 0.75 else "só na lista (precisa de ≥75%)"
        print(f"   previsão por roteiro: {r['precisao_centro']:.0%} certas em {r['previsoes_testadas']} testes → {centro}")
    # boss que já tinha um roteiro aprendido com mais runs (outra máquina, capturas apagadas) fica como estava
    for nome, antigo in carregar().items():
        if antigo.get("runs", 0) > roteiros.get(nome, {}).get("runs", 0):
            roteiros[nome] = antigo
            print(f"\n{nome}: mantido o roteiro anterior ({antigo['runs']} runs; aqui só há "
                  f"{len(por_boss.get(nome, []))}).")
    salvar(roteiros)
    print(f"\nRoteiros salvos em {CAMINHO_LOCAL}. O overlay usa na próxima vez que abrir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
