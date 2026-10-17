"""Pacote de contribuição: os dados de luta de uma captura, sem nomes, para mandar ao projeto.

O que vai (run.json): bosses (nome, código do mob, masmorra), início e fim de cada luta, a curva de HP, o medidor
de atordoamento, cada skill do boss com o tempo, o alvo e o preparo (0x3809), quantos jogadores cada skill acertou
e o maior golpe, a classe de cada jogador e o dano de cada um no boss.

O que NÃO vai: nomes de personagens, chat, servidor, guilda, IDs de conta ou de entidade, CP/GS. Os jogadores
viram "J1", "J2"... (você é "voce"), na ordem em que aparecem. A captura bruta só entra se a pessoa marcar
(ela tem nomes e chat), e nunca é publicada.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import zipfile
from collections import defaultdict
from statistics import median

from .alertas import carregar_mecanicas
from .analise import Analise
from .aovivo import Sessao, ler_spawn
from .caminhos import pasta_usuario
from .captura import ler_segmentos
from .versao import VERSAO

FORMATO = "nebula-run/1"


def _masmorra_de(dados: dict, boss: str) -> str:
    return next((mz["nome"] for mz in dados["masmorras"] for b in mz["bosses"] if b["nome"] == boss), "")


def exportar(captura: str, progresso=None) -> dict:
    """Lê a captura e devolve o run.json (dict), sem nenhum dado pessoal."""
    dados = carregar_mecanicas()
    s = Sessao(dados, burst=False)
    t0 = [None]
    anon: dict[int, str] = {}
    classes: dict[str, str] = {}
    casts, golpes, preparos = defaultdict(list), defaultdict(list), defaultdict(list)
    hp, atord, dano = defaultdict(list), defaultdict(list), defaultdict(lambda: defaultdict(int))
    visto: dict[int, list] = {}
    mobs: dict[int, int] = {}                       # entidade -> código do mob

    def rotulo(ent: int) -> str:
        """Jogador -> "voce" ou "J1", "J2"... (invocação conta para o dono, como no painel)."""
        dono = s.medidor.dono(ent, s.nomes, set(s.nomes))
        if dono not in anon:
            eu = dono == s.eu or (s.meu_nome and s.nomes.get(dono) == s.meu_nome)
            anon[dono] = "voce" if eu else f"J{sum(1 for v in anon.values() if v != 'voce') + 1}"
        return anon[dono]

    def observar(ts, fluxo, prof, op, payload, res):
        s._observar(ts, fluxo, prof, op, payload, res)
        if op == 0x3641:
            r = ler_spawn(bytes(payload))
            if r:
                mobs[r[0]] = r[1]
        if not res or res[0] != "ok":
            return
        c = res[1]
        if op == 0x3802 and c["conjurador"] in s.bosses:
            casts[c["conjurador"]].append((ts, c["skill"], c["alvo"]))
        elif op == 0x3809 and c["conjurador"] in s.bosses:
            preparos[c["conjurador"]].append((ts, c["skill"]))
        elif op == 0x3804 and c.get("origem") in s.bosses and c.get("alvo") != c.get("origem"):
            golpes[c["origem"]].append((ts, c["skill"], c["alvo"], c["dano"]))
        elif op in (0x3804, 0x3805) and c.get("alvo") in s.bosses and c.get("origem") not in s.bosses:
            dano[c["alvo"]][c["origem"]] += c["dano"]          # rótulos no fim, quando já se sabe quem é dono de quê
        elif op == 0x8D00 and c["entidade"] in s.bosses:
            b = s.bosses[c["entidade"]]
            pct = round(b.pct, 1)
            if not hp[c["entidade"]] or abs(hp[c["entidade"]][-1][1] - pct) >= 0.5:
                hp[c["entidade"]].append((ts, pct))
        if op == 0x3802 and c["conjurador"] in s.bosses or op == 0x8D00 and c.get("entidade") in s.bosses:
            ent = c.get("conjurador", c.get("entidade"))
            visto.setdefault(ent, [ts, ts])[1] = ts

    s.analise = Analise(observador=observar)
    n = 0
    for seg in ler_segmentos(captura):
        t0[0] = t0[0] or seg.ts
        s.segmento(seg)
        n += 1
        if progresso and n % 20000 == 0:
            progresso(n)
        b = s.boss_atual()                          # medidor de atordoamento (fica no estado do boss)
        if b and b.atordoamento and (not atord[b.entidade] or atord[b.entidade][-1][1:] != list(b.atordoamento)):
            atord[b.entidade].append([seg.ts, *b.atordoamento])
    if t0[0] is None:
        raise ValueError("captura vazia")
    ini = t0[0]
    dano_rotulado: dict[int, dict] = {}
    for boss, por_ent in dano.items():
        soma: dict[str, int] = defaultdict(int)
        for ent, v in sorted(por_ent.items(), key=lambda kv: -kv[1]):
            quem = rotulo(ent)
            soma[quem] += v
            classe = s.medidor.classe_de(s.medidor.dono(ent, s.nomes, set(s.nomes))) or s.medidor.classe_de(ent)
            if classe:
                classes.setdefault(quem, classe)
        dano_rotulado[boss] = soma

    def alvo_txt(alvo: int, boss: int) -> str:
        if alvo == boss:
            return "boss"
        return anon.get(alvo) or ("voce" if alvo == s.eu else "outro")

    bosses = []
    for ent, b in s.bosses.items():
        if ent not in visto:
            continue
        com, fim = visto[ent]
        lista_prep = list(preparos[ent])
        saida_casts = []
        for ts, skill, alvo in casts[ent]:
            prep = next((p for p in lista_prep if p[1] == skill and 0 <= ts - p[0] < 6), None)
            if prep:
                lista_prep.remove(prep)
            saida_casts.append({"t": round(ts - com, 2), "skill": skill, "alvo": alvo_txt(alvo, ent),
                                "preparo_s": round(ts - prep[0], 2) if prep else None})
        por_skill: dict[int, dict] = {}
        for skill in {g[1] for g in golpes[ent]}:
            gs = [g for g in golpes[ent] if g[1] == skill]
            por_cast = defaultdict(set)
            for ts, _, alvo, _ in gs:
                por_cast[round(ts)].add(alvo)
            por_skill[str(skill)] = {"acertos": len(gs), "maior": max(g[3] for g in gs),
                                     "jogadores_por_vez": median(len(v) for v in por_cast.values())}
        bosses.append({
            "nome": b.nome, "mob": mobs.get(ent),
            "masmorra": _masmorra_de(dados, b.nome), "inicio_s": round(com - ini, 1), "fim_s": round(fim - ini, 1),
            "morto": b.morto, "hp": [[round(t - com, 1), p] for t, p in hp[ent]],
            "atordoamento": [[round(t - com, 1), a, m] for t, a, m in atord[ent]],
            "casts": saida_casts, "golpes": por_skill,
            "dano": dict(sorted(dano_rotulado.get(ent, {}).items(), key=lambda kv: -kv[1])),
        })
    return {
        "formato": FORMATO, "versao_app": VERSAO, "data": dt.date.fromtimestamp(ini).isoformat(),
        "duracao_s": round(s.ultimo_ts - ini, 1) if s.ultimo_ts else 0,
        "voce": {"classe": s.minha_classe, "papel": s.meu_papel},
        "jogadores": {j: {"classe": c} for j, c in sorted(classes.items())},
        "bosses": sorted(bosses, key=lambda b: b["inicio_s"]),
    }


def _slug(texto: str) -> str:
    import unicodedata
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:40] or "run"


def empacotar(captura: str | None, relato: dict, incluir_captura: bool = False, progresso=None) -> str:
    """Gera Documentos/Nebula Overlay/contribuicoes/nebula_<conteúdo>_<data>.zip. Devolve o caminho."""
    run = exportar(captura, progresso) if captura else None
    conteudo = relato.get("conteudo") or (run["bosses"][0]["masmorra"] if run and run["bosses"] else "") or "relato"
    nome = f"nebula_{_slug(conteudo)}_{dt.datetime.now():%Y-%m-%d_%H-%M}.zip"
    caminho = os.path.join(pasta_usuario("contribuicoes"), nome)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("relato.json", json.dumps(dict(relato, versao_app=VERSAO), ensure_ascii=False, indent=1))
        if run:
            z.writestr("run.json", json.dumps(run, ensure_ascii=False, indent=1))
        if captura and incluir_captura:
            z.write(captura, os.path.basename(captura))
    return caminho
