"""Meter de jogadores: dano e DPS de cada um na luta do boss.

A luta vai do 1º ao último golpe de jogador no boss (a morte chega segundos depois; sem
golpe por 30 s, a luta fecha: wipe/reset). Nessa janela conta o dano dos jogadores em
qualquer alvo que não seja jogador, então adds entram.
O dano em adds depois do último golpe no boss fica "pendente" e só entra quando o boss
apanha de novo.

Jogador = entidade que usa skill de classe (prefixo 11–19) ou que tem nome conhecido.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .classes import NOME as NOME_CLASSE, classe_da_skill

FIM_SEM_GOLPE = 30.0          # s sem dano no boss: luta encerrada (wipe, reset ou boss fora)


@dataclass
class Luta:
    boss: int
    nome: str
    inicio: float
    fim: float | None = None
    ultimo_no_boss: float = 0.0
    dano: dict = field(default_factory=lambda: defaultdict(int))
    acertos: dict = field(default_factory=lambda: defaultdict(int))
    criticos: dict = field(default_factory=lambda: defaultdict(int))
    pendente: list = field(default_factory=list)     # (origem, dano, crítico) em adds desde o último golpe no boss

    def duracao(self, agora: float) -> float:
        return max(1.0, (self.fim if self.fim is not None else agora) - self.inicio)


class Medidor:
    def __init__(self) -> None:
        self.classes: dict[int, Counter] = defaultdict(Counter)
        self.atual: Luta | None = None
        self.ultima: Luta | None = None
        self.donos_nome: dict[int, str] = {}     # invocação -> nome do dono (do 0x3641)

    def classe_de(self, ent: int) -> str | None:
        c = self.classes.get(ent)
        return c.most_common(1)[0][0] if c else None

    def dano(self, ts: float, c: dict, bosses: dict, eh_jogador) -> None:
        """c: campos de 0x3804/0x3805 (origem, alvo, skill, dano, critico)."""
        origem, alvo, valor = c.get("origem"), c.get("alvo"), c.get("dano") or 0
        cl = classe_da_skill(c.get("skill") or 0) if origem not in bosses else None
        if cl:   # o boss às vezes aparece como origem de efeito de jogador: ele nunca vira "jogador"
            self.classes[origem][cl] += 1
        if not valor or origem == alvo or not (cl or eh_jogador(origem)) or eh_jogador(alvo):
            return   # origem = alvo: invocação "batendo em si mesma" (dreno/expiração dos espíritos do Espiritualista)
        if alvo in bosses:
            l = self.atual
            if l is None or l.fim is not None:
                if l is not None:
                    self.ultima = l
                self.atual = l = Luta(alvo, bosses[alvo].nome, ts)
            if alvo == l.boss:
                l.ultimo_no_boss = ts
        l = self.atual
        if l is None or l.fim is not None:
            return
        golpe = (origem, valor, bool(c.get("critico")))
        if alvo != l.boss:
            l.pendente.append(golpe)
            return
        for o, v, cr in l.pendente + [golpe]:
            l.dano[o] += v
            l.acertos[o] += 1
            l.criticos[o] += cr
        l.pendente.clear()

    def morte(self, ts: float, ent: int) -> None:
        l = self.atual
        if l and l.fim is None and l.boss == ent:
            l.fim = l.ultimo_no_boss or ts
            l.pendente.clear()

    def tick(self, agora: float) -> None:
        l = self.atual
        if l and l.fim is None and l.ultimo_no_boss and agora - l.ultimo_no_boss > FIM_SEM_GOLPE:
            l.fim = l.ultimo_no_boss
            l.pendente.clear()

    def dono(self, ent: int, nomes: dict, jogadores: set[int]) -> int:
        """A quem somar o dano de uma entidade: ela mesma, ou o dono se for invocação.

        1. o 0x3641 trouxe o nome do dono (Clérigo, por exemplo);
        2. senão, pela classe das skills: se só um jogador da luta tem essa classe, é dele
           (as invocações do Mago usam skills 15xxxxxx e vêm sem dono).
        """
        if ent in nomes:
            return ent
        nome = self.donos_nome.get(ent)
        if nome:
            # o ID do jogador muda a cada zona: o mesmo nome pode ter dois IDs; vale o que lutou esta luta
            candidatos = [e for e, n in nomes.items() if n == nome]
            for e in candidatos:
                if e in jogadores:
                    return e
            if candidatos:
                return candidatos[0]
        cl = self.classe_de(ent)
        if cl:
            mesmos = [j for j in jogadores if self.classe_de(j) == cl]
            if len(mesmos) == 1:
                return mesmos[0]
        return ent

    def nomes_pelas_invocacoes(self, l, nomes: dict) -> dict:
        """Nomes que faltam, deduzidos das invocações: o 0x3641 da invocação traz o nome do dono, mas o dono pode
        não ter nome conhecido (você, com o app aberto no meio da masmorra, antes do 0x3633). Se na luta só uma
        entidade sem nome, que não é invocação, tem a classe das invocações daquele dono, é ele."""
        conhecidos = {nomes[e] for e in l.dano if e in nomes}     # só os que lutaram nesta luta (o ID muda por zona)
        classes_do_dono: dict[str, set] = defaultdict(set)
        for e, n in self.donos_nome.items():
            if n not in conhecidos and self.classe_de(e):
                classes_do_dono[n].add(self.classe_de(e))
        if not classes_do_dono:
            return nomes
        sem_nome = [e for e in l.dano if e not in nomes and e not in self.donos_nome]
        novos = dict(nomes)
        for nome, classes in classes_do_dono.items():
            if len(classes) != 1:
                continue
            cl = next(iter(classes))
            # invocações sem o 0x3641 também ficam sem nome: o jogador é a de longe maior (3× a segunda)
            ents = sorted((e for e in sem_nome if self.classe_de(e) == cl and e not in novos), key=lambda e: -l.dano[e])
            if ents and (len(ents) == 1 or l.dano[ents[0]] >= 3 * l.dano[ents[1]]):
                novos[ents[0]] = nome
        return novos

    def estado(self, agora: float, nomes: dict, eu: int | None, status: list[dict] | None = None) -> dict | None:
        """Luta atual (ou a última) pronta para desenhar: linhas ordenadas por dano."""
        l = self.atual
        if l is None:
            return None
        meu_nome = nomes.get(eu) if eu is not None else None
        nomes = self.nomes_pelas_invocacoes(l, nomes)
        dur = l.duracao(agora)
        # invocações somam no dono (sem mexer nos números guardados da luta)
        jogadores = {e for e in l.dano if e in nomes}
        dano, acertos, criticos = defaultdict(int), defaultdict(int), defaultdict(int)
        for e, d in l.dano.items():
            j = self.dono(e, nomes, jogadores)
            dano[j] += d
            acertos[j] += l.acertos[e]
            criticos[j] += l.criticos[e]
        total = sum(dano.values()) or 1
        por_alvo = defaultdict(list)
        for s in status or []:
            if s.get("em") == "alvo" and s.get("alvo") is not None:
                por_alvo[s["alvo"]].append(s["texto"])
        linhas = []
        for ent, d in sorted(dano.items(), key=lambda x: -x[1]):
            nome = nomes.get(ent)
            if not nome and d / total < 0.01:
                continue                       # invocações/armadilhas sem dono conhecido, com dano mínimo
            chave = self.classe_de(ent)
            linhas.append({
                "id": ent, "nome": nome or f"#{ent}", "chave": chave or "", "classe": NOME_CLASSE.get(chave or "", ""),
                "dano": d, "dps": d / dur, "pct": 100 * d / total,
                "voce": ent == eu or (meu_nome is not None and nome == meu_nome),     # você com o ID de outra zona
                "critico": 100 * criticos[ent] / max(1, acertos[ent]), "status": por_alvo.get(ent, []),
            })
        return {"boss": l.nome, "ativa": l.fim is None, "duracao": dur, "total": sum(dano.values()),
                "dps_total": sum(dano.values()) / dur, "linhas": linhas}
