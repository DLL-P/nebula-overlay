"""Relatório pós-run: o seu desempenho em cada boss de uma captura.

  python relatorio.py capturas/aovivo_2026-10-17_21-10-05.pcap
  python relatorio.py capturas/X.pcap --boss Auldor        só um boss
  python relatorio.py capturas/X.pcap --sem-salvar          não grava o resumo em relatorios/

Para cada boss:
- duração da luta, seu DPS e a sua fatia do dano total no boss;
- dano por skill (nomes em português), com acertos, críticos, costas e dano duplo;
- pausas: trechos de mais de 2,5 s em que você não causou dano. Quando ninguém
  conseguia bater (boss sumido, explosão), a pausa é da mecânica; senão, é sua
  e mostra qual alerta estava na tela;
- burst: quanto você bateu nos 10 s depois de cada "BURST AGORA", comparado
  com a sua média.

O resumo vai para relatorios/, e a próxima run do mesmo boss é comparada com a anterior.
A sua classe e o seu personagem são detectados sozinhos, como no overlay.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

from a2parse.alertas import carregar_mecanicas
from a2parse.analise import Analise
from a2parse.aovivo import Sessao, ler_eu
from a2parse.caminhos import dados_jogo, usuario
from a2parse.captura import ler_segmentos

PASTA = usuario("relatorios")
PAUSA_MIN = 2.5          # s sem dano seu para contar como pausa
JANELA_BURST = 10.0


def carregar_nomes_skill() -> dict[int, str]:
    """Nomes das skills: tabela opcional (dados_jogo). Sem ela, o relatório mostra o ID da skill."""
    for arq in ("skills_pt.json", "skills.json"):
        caminho = dados_jogo(arq)
        if not caminho:
            continue
        try:
            with open(caminho, encoding="utf-8") as f:
                return {int(k): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            continue
    return {}


def nome_skill(nomes: dict[int, str], skill: int) -> str:
    for base in (skill, skill // 10 * 10, skill // 100 * 100, skill // 1000 * 1000, skill // 10000 * 10000):
        if base in nomes and nomes[base] != "???":
            return nomes[base]
    return f"skill {skill}"


def mmss(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def processar(caminho: str) -> tuple[Sessao, set[int], list[dict]]:
    sessao = Sessao(carregar_mecanicas())
    meus: set[int] = set()

    def observar(ts, fluxo, prof, op, payload, resultado):
        if op == 0x3633:
            r = ler_eu(payload)
            if r:
                meus.add(r[0])
        sessao._observar(ts, fluxo, prof, op, payload, resultado)

    sessao.analise = Analise(observador=observar)          # lista completa de danos, não o deque do ao vivo
    for seg in ler_segmentos(caminho):
        sessao.segmento(seg)
    return sessao, meus, list(sessao.analise.eventos_dano)


def pausas(tempos: list[float], ini: float, fim: float) -> list[tuple[float, float]]:
    pts = [ini] + sorted(tempos) + [fim]
    return [(a, b) for a, b in zip(pts, pts[1:]) if b - a >= PAUSA_MIN]


def sobreposicao(a: tuple[float, float], lista: list[tuple[float, float]]) -> float:
    return sum(max(0.0, min(a[1], b[1]) - max(a[0], b[0])) for b in lista)


def analisar_boss(sessao: Sessao, meus: set[int], danos: list[dict], ent: int, nomes: dict[int, str]) -> dict | None:
    b = sessao.bosses[ent]
    no_boss = [d for d in danos if d.get("alvo") == ent and d.get("dano")]
    if not no_boss:
        return None
    ini, fim = no_boss[0]["ts"], no_boss[-1]["ts"]
    dur = max(1.0, fim - ini)
    meu = [d for d in no_boss if d.get("origem") in meus]
    total, total_meu = sum(d["dano"] for d in no_boss), sum(d["dano"] for d in meu)

    por_skill: dict[str, dict] = defaultdict(lambda: {"dano": 0, "acertos": 0, "criticos": 0, "costas": 0, "duplos": 0})
    for d in meu:
        s = por_skill[nome_skill(nomes, d["skill"])]
        s["dano"] += d["dano"]
        s["acertos"] += 1
        s["criticos"] += bool(d.get("critico"))
        s["costas"] += bool(d.get("costas"))
        s["duplos"] += bool(d.get("double"))

    # pausas: quando ninguém batia, é mecânica; quando só você parou, é sua.
    # Só acertos diretos contam: DoT segue pingando com o boss sumido.
    diretos = [d for d in no_boss if d.get("tipo") == "dano"]
    todos = pausas([d["ts"] for d in diretos], ini, fim)
    minhas = []
    for p in pausas([d["ts"] for d in diretos if d.get("origem") in meus], ini, fim):
        mec = sobreposicao(p, todos)
        sua = (p[1] - p[0]) - mec
        na_tela = [a.texto for a in sessao.alertas
                   if a.boss == b.nome and a.fase == "ativo" and p[0] - 3 <= a.t <= p[1]]
        minhas.append({"de": p[0] - ini, "ate": p[1] - ini, "mecanica": round(mec, 1), "sua": round(sua, 1),
                       "alertas": list(dict.fromkeys(na_tela))[:3]})

    dps_meu = total_meu / dur
    bursts = []
    for a in sessao.alertas:
        if a.boss == b.nome and a.tipo == "burst" and ini <= a.t <= fim:
            na_janela = sum(d["dano"] for d in meu if a.t <= d["ts"] < a.t + JANELA_BURST)
            bursts.append({"t": a.t - ini, "dano": na_janela,
                           "vs_media": round(na_janela / (dps_meu * JANELA_BURST), 2) if dps_meu else 0})

    acertos = len(meu) or 1
    return {
        "boss": b.nome, "duracao": round(dur, 1), "dano_total": total, "dano_seu": total_meu,
        "dps_seu": round(dps_meu), "fatia": round(100 * total_meu / total, 1) if total else 0,
        "critico_pct": round(100 * sum(bool(d.get("critico")) for d in meu) / acertos, 1),
        "costas_pct": round(100 * sum(bool(d.get("costas")) for d in meu) / acertos, 1),
        "skills": sorted(({"nome": k, **v} for k, v in por_skill.items()), key=lambda x: -x["dano"]),
        "pausas": minhas,
        "pausa_sua_total": round(sum(p["sua"] for p in minhas), 1),
        "pausa_mecanica_total": round(sum(p["mecanica"] for p in minhas), 1),
        "bursts": bursts,
    }


def anterior(boss: str, captura: str) -> dict | None:
    candidatos = []
    for arq in glob.glob(os.path.join(PASTA, "*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        if r.get("captura") == os.path.basename(captura):
            continue
        for luta in r.get("lutas", []):
            if luta["boss"] == boss and r.get("classe") is not None:
                candidatos.append((r.get("gerado", ""), r.get("classe"), luta))
    return max(candidatos, key=lambda x: x[0]) if candidatos else None


def imprimir(r: dict, classe: str, ant: tuple | None) -> None:
    print(f"\n━━ {r['boss']} ━━  {mmss(r['duracao'])} de luta")
    linha = f"  Seu dano: {r['dano_seu']:,}  ·  DPS {r['dps_seu']:,}  ·  {r['fatia']}% do dano no boss"
    print(linha.replace(",", "."))
    print(f"  Crítico {r['critico_pct']}%  ·  costas {r['costas_pct']}%")
    if ant:
        _, classe_ant, la = ant
        if classe_ant == classe:
            d_dps = r["dps_seu"] - la["dps_seu"]
            d_p = r["pausa_sua_total"] - la["pausa_sua_total"]
            print(f"  vs. run anterior: DPS {d_dps:+,} ({100 * d_dps / max(1, la['dps_seu']):+.0f}%), "
                  f"pausas suas {d_p:+.1f} s, luta {r['duracao'] - la['duracao']:+.1f} s".replace(",", "."))
    print("\n  Skill                                   dano     %   acertos  crít  costas")
    for s in r["skills"][:12]:
        pct = 100 * s["dano"] / max(1, r["dano_seu"])
        print(f"  {s['nome'][:36]:36s} {s['dano']:>10,}  {pct:4.1f}  {s['acertos']:>6}  {100 * s['criticos'] / s['acertos']:3.0f}%  "
              f"{100 * s['costas'] / s['acertos']:3.0f}%".replace(",", "."))
    print(f"\n  Pausas: {r['pausa_sua_total']} s suas · {r['pausa_mecanica_total']} s de mecânica (ninguém conseguia bater)")
    for p in sorted(r["pausas"], key=lambda p: -p["sua"])[:6]:
        if p["sua"] < 1.0:
            continue
        motivo = f"  na tela: {', '.join(p['alertas'])}" if p["alertas"] else ""
        print(f"    {mmss(p['de'])}–{mmss(p['ate'])}  {p['sua']:.1f} s parado{motivo}")
    if r["bursts"]:
        print("\n  Burst depois de \"BURST AGORA\" (10 s, comparado com a sua média):")
        for bu in r["bursts"]:
            veredito = "bom" if bu["vs_media"] >= 1.3 else "fraco: guarde as skills fortes para esta hora" if bu["vs_media"] < 1.0 else "ok"
            print(f"    {mmss(bu['t'])}  {bu['vs_media']:.2f}× a média  → {veredito}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Relatório pós-run por boss.")
    ap.add_argument("captura", nargs="?", help="padrão: a captura mais recente de capturas/")
    ap.add_argument("--boss", help="parte do nome do boss")
    ap.add_argument("--sem-salvar", action="store_true")
    args = ap.parse_args(argv)
    if not args.captura:
        import glob
        caps = sorted(glob.glob(usuario("capturas", "*.pcap")), key=os.path.getmtime)
        if not caps:
            print("Nenhuma captura em capturas/. Jogue uma masmorra com o overlay aberto.")
            return 1
        args.captura = caps[-1]
        print(f"Captura: {os.path.basename(args.captura)}")

    print("Lendo a captura…")
    sessao, meus, danos = processar(args.captura)
    nomes = carregar_nomes_skill()
    if not meus:
        print("Não achei o seu personagem (0x3633) nesta captura: comece a gravar antes de entrar na masmorra.")
        return 1
    classe = sessao.minha_classe
    print(f"Você: {sessao.meu_nome} · {sessao.estado(0)['classe'] or 'classe ?'}")
    lutas = []
    for ent, b in sessao.bosses.items():
        if args.boss and args.boss.lower() not in b.nome.lower():
            continue
        r = analisar_boss(sessao, meus, danos, ent, nomes)
        if r and r["dano_seu"]:
            imprimir(r, classe, anterior(r["boss"], args.captura))
            lutas.append(r)
    if not lutas:
        print("Nenhuma luta de boss com dano seu nesta captura.")
        return 1
    if not args.sem_salvar:
        import datetime as dt
        os.makedirs(PASTA, exist_ok=True)
        nome = os.path.splitext(os.path.basename(args.captura))[0]
        caminho = os.path.join(PASTA, f"{nome}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"captura": os.path.basename(args.captura), "gerado": dt.datetime.now().isoformat(timespec="seconds"),
                       "personagem": sessao.meu_nome, "classe": classe, "lutas": lutas}, f, ensure_ascii=False, indent=1)
        print(f"\nResumo salvo em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
