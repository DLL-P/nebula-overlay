"""Linha do tempo dos bosses: o que vem a seguir e em quantos segundos.

Quatro fontes, aprendidas das capturas (aprender) e usadas ao vivo (Previsor):

- roteiro: os bosses seguem rotações fixas, mas a ordem só se repete dentro de uma fase. O modelo
  olha as duas últimas skills para prever a próxima (e só a última quando não conhece o par),
  encadeando até ~40 s. Ressincroniza a cada cast. Na avaliação deixando uma run de fora (4 runs da
  Urugugu), acertou 89% das previsões do Auldor a 0–3 s e 76% a 3–6 s.
- fases por HP: algumas mecânicas saem em % fixos (fase do céu do Auldor a 75–78% e 31–33%,
  vórtice a 27–31%, zona do Raur a 61–65%). O tempo até lá vem do ritmo de dano dos últimos ~10 s,
  e a rotação prevista é cortada nesse ponto (a fase interrompe a rotação).
- atordoamento: o medidor 0xE005 (1200 no máximo) desce com o dano; em ~0 o boss fica 5 s parado
  (skill 1000009). O tempo até lá vem do ritmo com que o medidor desce.
- ciclos: skills com intervalo fixo (zona do Raur a cada 57,5 s, variação 0).

Os nós da cadeia são as mecânicas (variações da mesma mecânica, como os dois leques do Auldor,
viram um nó só); skills sem mecânica entram pelo ID.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from statistics import median, pstdev

from .caminhos import app, usuario

CAMINHO = app("mecanicas", "roteiros.json")              # vem com o programa (atualiza junto com ele)
CAMINHO_LOCAL = usuario("mecanicas", "roteiros.json")    # aprendidos nesta máquina (roteiros.py)

ATORDOAMENTO = 1000009
# não entram na cadeia: pulsos/ticks, ataque básico, 2º pacote do atordoamento e "esmaga" (sai junto do agarrão)
IGNORAR = {1504471, 1504451, 1504452, 1504431, 1605131, 1001450, 1504410, 1605070, 1601050}
MIN_CHANCE, MAX_JITTER = 0.5, 1.5


def no_de(skill: int, grupos: dict[int, str]) -> str:
    return grupos.get(skill, str(skill))


def grupos_de(boss: dict) -> dict[int, str]:
    """skill -> id da mecânica (as pessoais ficam de fora: o alvo muda, a rotação não)."""
    g = {}
    for m in boss.get("mecanicas", []):
        gat = m.get("gatilho") or {}
        if gat.get("pessoal"):
            continue
        for s in gat.get("skill_ids") or []:
            g.setdefault(s, m["id"])
    return g


def _sequencia(run: list[tuple[float, int, float]], grupos: dict[int, str]) -> list[tuple[float, str]]:
    seq: list[tuple[float, str]] = []
    for t, s, _hp in run:
        if s in IGNORAR:
            continue
        n = no_de(s, grupos)
        if seq and seq[-1][1] == n and t - seq[-1][0] < 6:
            seq[-1] = (t, n)              # repetição seguida da mesma skill: vale a última
        else:
            seq.append((t, n))
    return seq


def aprender(runs: list[list[tuple[float, int, float]]], boss: dict) -> dict:
    """runs: por luta, os casts do boss como (tempo, skill, HP%). Devolve o roteiro do boss."""
    grupos = grupos_de(boss)
    seqs = [_sequencia(r, grupos) for r in runs]
    cadeia = {}
    for ordem in (1, 2):
        pares, atrasos = defaultdict(Counter), defaultdict(list)
        for sq in seqs:
            for i in range(ordem, len(sq)):
                ctx = "|".join(x[1] for x in sq[i - ordem:i])
                pares[ctx][sq[i][1]] += 1
                atrasos[(ctx, sq[i][1])].append(sq[i][0] - sq[i - 1][0])
        for ctx, cont in pares.items():
            tot = sum(cont.values())
            prox, n = cont.most_common(1)[0]
            ds = atrasos[(ctx, prox)]
            md = median(ds)
            jit = median(abs(d - md) for d in ds)
            if n >= 2 and n / tot >= MIN_CHANCE and jit <= MAX_JITTER:
                cadeia[ctx] = {"proxima": prox, "apos": round(md, 2), "chance": round(n / tot, 2), "vezes": n}
    # fases por HP: a k-ésima vez que a mecânica sai, num HP parecido em todas as runs
    fases = []
    por_no = defaultdict(lambda: defaultdict(list))        # nó -> k -> [HP]
    for r in runs:
        vistos = Counter()
        for t, s, hp in r:
            if s in IGNORAR or s == ATORDOAMENTO:
                continue
            n = no_de(s, grupos)
            if n.isdigit():
                continue                                    # só mecânicas com ficha
            por_no[n][vistos[n]].append(hp)
            vistos[n] += 1
    for n, ks in por_no.items():
        if max(ks) > 2:
            continue                                        # sai muitas vezes: é rotação, não fase
        for k, hps in sorted(ks.items()):
            if len(hps) >= 2 and max(hps) - min(hps) <= 6.0 and len(hps) >= 0.75 * len(runs):
                fases.append({"no": n, "vez": k + 1, "hp": round(max(hps), 1), "variacao": round(max(hps) - min(hps), 1)})
    # numa mesma faixa de HP fica só a 1ª mecânica: as seguintes vêm encadeadas nela (sumiço e mergulho
    # vêm depois do início da fase do céu, e o roteiro já prevê esses)
    fases.sort(key=lambda f: -f["hp"])
    unicas = []
    for f in fases:
        if all(abs(f["hp"] - u["hp"]) > 6.0 for u in unicas):
            unicas.append(f)
    fases = unicas
    # ciclos: intervalo fixo entre casts da mesma skill
    ciclos = {}
    intervalos = defaultdict(list)
    for r in runs:
        ult = {}
        for t, s, _hp in r:
            if s in ult:
                intervalos[s].append(t - ult[s])
            ult[s] = t
    for s, iv in intervalos.items():
        if len(iv) >= 2 and pstdev(iv) <= 1.0 and median(iv) >= 15:
            ciclos[no_de(s, grupos)] = round(median(iv), 2)
    return {"cadeia": cadeia, "fases_hp": fases, "ciclos": ciclos, "runs": len(runs)}


def precisao_roteiro(runs: list[list[tuple[float, int, float]]], boss: dict) -> tuple[float, int]:
    """Testa a própria previsão: aprende com as outras runs, testa em cada uma. Conta as previsões que
    subiriam para o centro (confiança ≥ 0,75, de 1 a 6 s à frente) e quantas se cumpriram (±2 s)."""
    if len(runs) < 3:
        return 0.0, 0
    grupos = grupos_de(boss)
    ok = tot = 0
    for i, teste in enumerate(runs):
        rot = aprender([r for j, r in enumerate(runs) if j != i], boss)
        rot["precisao_centro"] = 1.0              # no teste a trava do centro não vale
        p = Previsor(rot, boss)
        reais = [(t, no_de(s, grupos)) for t, s, _ in teste if s not in IGNORAR]
        vistas = set()
        for t, s, _ in teste:
            p.cast(t, s)
            for x in p.linha(t):
                if x.fonte != "roteiro" or x.confianca < 0.75 or not 1 <= x.eta <= 6:
                    continue
                chave = (x.no, round((t + x.eta) / 3))
                if chave in vistas:
                    continue
                vistas.add(chave)
                tot += 1
                ok += any(n == x.no and abs(tr - (t + x.eta)) <= 2.0 for tr, n in reais)
    return (ok / tot if tot else 0.0), tot


def salvar(roteiros: dict, caminho: str = CAMINHO_LOCAL) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(roteiros, f, ensure_ascii=False, indent=1)


def _ler(caminho: str) -> dict:
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def carregar(caminho: str | None = None) -> dict:
    """Sem caminho: junta os roteiros do programa e os aprendidos aqui; por boss, fica o que viu mais runs."""
    if caminho:
        return _ler(caminho)
    juntos = _ler(CAMINHO)
    for nome, r in _ler(CAMINHO_LOCAL).items():
        if r.get("runs", 0) >= juntos.get(nome, {}).get("runs", 0):
            juntos[nome] = r
    return juntos


# ---------------- ao vivo ----------------

@dataclass
class Previsao:
    eta: float
    no: str
    texto: str
    tipo: str
    confianca: float
    fonte: str            # "roteiro", "hp", "atordoamento", "ciclo"
    exata: bool = False   # sem "~" na tela


@dataclass
class Previsor:
    """Um por boss. Recebe casts, HP e o medidor de atordoamento; devolve a linha do tempo."""
    roteiro: dict
    boss: dict
    horizonte: float = 40.0
    historico: list = field(default_factory=list)            # nós já vistos (para a cadeia de 2ª ordem)
    cadeia_prevista: list = field(default_factory=list)      # (t, nó, chance)
    hp: deque = field(default_factory=lambda: deque(maxlen=120))
    medidor: deque = field(default_factory=lambda: deque(maxlen=120))
    ultimo_ciclo: dict = field(default_factory=dict)          # nó -> t do último cast
    vezes: Counter = field(default_factory=Counter)           # nó -> quantas vezes saiu (fases por HP)

    def __post_init__(self) -> None:
        self.grupos = grupos_de(self.boss)
        self.textos: dict[str, tuple[str, str]] = {}
        for m in self.boss.get("mecanicas", []):
            passos = m.get("sequencia") or ([{"texto": m["alerta"], "tipo": m.get("acao_tipo", "atencao")}] if m.get("alerta") else [])
            if passos:
                self.textos[m["id"]] = (passos[0]["texto"], passos[0].get("tipo", m.get("acao_tipo", "atencao")))

    # entradas
    def cast(self, t: float, skill: int) -> None:
        if skill in IGNORAR:
            return
        n = no_de(skill, self.grupos)
        if skill == ATORDOAMENTO:
            self.medidor.clear()
        self.vezes[n] += 1
        if n in self.roteiro.get("ciclos", {}):
            self.ultimo_ciclo[n] = t
        if self.historico and self.historico[-1] == n:
            pass                                             # repetição: refaz a cadeia a partir deste cast
        else:
            self.historico.append(n)
        self.cadeia_prevista = self._encadear(t)

    def hp_pct(self, t: float, pct: float) -> None:
        self.hp.append((t, pct))

    def atordoamento(self, t: float, atual: int, maximo: int) -> None:
        if self.medidor and atual > self.medidor[-1][1] + 100:
            self.medidor.clear()                             # recarregou depois do atordoamento
        self.medidor.append((t, atual, maximo))

    # cálculo
    def _encadear(self, t: float) -> list[tuple[float, str, float]]:
        cad = self.roteiro.get("cadeia", {})
        h, saida, chance, t0 = list(self.historico), [], 1.0, t
        for _ in range(10):
            o = (cad.get("|".join(h[-2:])) if len(h) >= 2 else None) or cad.get(h[-1]) if h else None
            if not o:
                break
            t += o["apos"]
            chance *= o["chance"]
            if t - t0 > self.horizonte or chance < 0.35:
                break
            saida.append((t, o["proxima"], chance))
            h.append(o["proxima"])
        return saida

    @staticmethod
    def _ritmo(amostras, agora: float, janela: float = 10.0, idx: int = 1) -> float | None:
        """Quanto o valor cai por segundo (positivo = caindo), pelos pontos dos últimos 'janela' s."""
        pts = [(x[0], x[idx]) for x in amostras if agora - x[0] <= janela]
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
            return None
        queda = (pts[0][1] - pts[-1][1]) / (pts[-1][0] - pts[0][0])
        return queda if queda > 0 else None

    def linha(self, agora: float) -> list[Previsao]:
        out: list[Previsao] = []
        corte = None                                          # a próxima fase por HP interrompe a rotação
        # fases por HP
        if self.hp:
            pct = self.hp[-1][1]
            ritmo = self._ritmo(self.hp, agora)
            for f in self.roteiro.get("fases_hp", []):
                if self.vezes[f["no"]] >= f["vez"] or pct <= f["hp"] - 3 or f["no"] not in self.textos:
                    continue
                if self.vezes[f["no"]] != f["vez"] - 1:
                    continue
                if not ritmo:
                    continue
                texto, tipo = self.textos[f["no"]]
                if pct <= f["hp"]:
                    # já passou do limiar: sai quando o boss terminar a ação atual. Iminente, mas sem hora
                    # certa: fica na lista e não sobe para o centro.
                    corte = 0.0
                    out.append(Previsao(0.0, f["no"], texto, tipo, 0.55, "hp"))
                    continue
                eta = (pct - f["hp"]) / ritmo
                if eta > self.horizonte:
                    continue
                corte = eta if corte is None else min(corte, eta)
                # o boss só dispara a fase quando termina a ação atual (1–5 s depois do limiar): a hora
                # exata erra demais para o centro (46% no Auldor); fica na lista
                out.append(Previsao(eta, f["no"], texto, tipo, 0.6, "hp"))
        # atordoamento
        if self.medidor:
            t_m, atual, maximo = self.medidor[-1]
            ritmo = self._ritmo(self.medidor, agora, 12.0, 1)
            if ritmo and atual > 0:
                eta = atual / ritmo
                if eta <= self.horizonte:
                    # no fim do medidor o ritmo recente é o que vale: só aí sobe para o centro
                    perto = atual <= 0.15 * maximo
                    recente = self._ritmo(self.medidor, agora, 5.0, 1) if perto else None
                    if recente:
                        eta = atual / recente
                    # o medidor para de descer quando a party para de bater (fase do céu, zona, troca de alvo):
                    # no teste da run das 20:53 só 0–38% dos "em 4 s" se cumpriram. Fica só na lista (e na barra).
                    out.append(Previsao(eta, "atordoamento", "ATORDOADO: BURST!", "burst", 0.6, "atordoamento"))
        # ciclos fixos
        for n, iv in self.roteiro.get("ciclos", {}).items():
            if n in self.ultimo_ciclo and n in self.textos:
                eta = self.ultimo_ciclo[n] + iv - agora
                if 0 <= eta <= self.horizonte:
                    texto, tipo = self.textos[n]
                    out.append(Previsao(eta, n, texto, tipo, 0.9, "ciclo", exata=True))
        # roteiro (cortado antes da próxima fase por HP)
        for t, n, chance in self.cadeia_prevista:
            eta = t - agora
            if eta < -0.5 or n not in self.textos:
                continue
            if corte is not None and eta > corte:
                continue
            if any(p.no == n and abs(p.eta - eta) < 2.0 for p in out):
                continue
            texto, tipo = self.textos[n]
            if self.roteiro.get("precisao_centro", 0.0) < 0.75:
                chance = min(chance, 0.7)                     # boss ainda pouco previsível: só na lista
            out.append(Previsao(max(0.0, eta), n, texto, tipo, round(chance, 2), "roteiro"))
        return sorted(out, key=lambda p: p.eta)


def medidor_atordoamento(payload: bytes) -> tuple[int, int, int] | None:
    """0xE005 (14 bytes): varint boss | u8 3 | u8 1 | u32 máximo | u32 atual | u8. Devolve (boss, atual, máximo)."""
    import struct
    from .protocolo import ler_varint
    if len(payload) < 12:
        return None
    try:
        r = ler_varint(payload, 0)
    except ValueError:
        return None
    if not r or len(payload) < r[1] + 10:
        return None
    ent, n = r
    maximo, atual = struct.unpack_from("<II", payload, n + 2)
    if not 0 < maximo <= 100000 or atual > maximo:
        return None
    return ent, atual, maximo
