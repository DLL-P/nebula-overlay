"""Avisos de controle em você: ATORDOADO, DERRUBADO, PRESO... com o tempo que falta e a dica da sua classe.

Opcional e desligado por padrão ("Avisos de controle em você" na engrenagem). Vale em qualquer combate,
PvE ou PvP, e só fala do seu personagem: o que o jogo já mostra na sua barra de efeitos. Nada sobre
adversários (recarga, posição, próxima skill) e nada que aperte teclas.

De onde vem (layouts em docs/PROTOCOLO.md, mapeados nas capturas de 2026-10-16 e 2026-10-17):
- 0x382A: efeito aplicado (alvo, instância, ID do efeito, duração em ms, quem aplicou, skill).
- 0x3816: movimento forçado (derrubada, empurrão, puxão); traz o ID do efeito que causou.
- 0x382C: efeito removido (instâncias); motivo 1 = acabou o tempo, 19 = saiu antes (quebrado, morte).

Que efeito é controle: a tabela dados/controles.json (nossa, editável), o 0x3816 e, se existir, o nome
na tabela opcional de skills (dados/skills_pt.json, que não vem com o programa).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .alertas import Alerta
from .caminhos import app, dados_jogo
from .decoders import ErroDecodificacao, Leitor
from .idioma import t

TIPOS = ("atordoamento", "derrubada", "enraizamento", "agarrao", "puxao", "sono", "medo", "silencio", "aereo",
         "controle")
CATEGORIA = {"cor": "roxo", "severidade": "alerta", "som": "bipe_curto_duplo"}    # cor e som do cartão
MIN_S, MAX_S = 0.5, 15.0          # mais curto que isso é solavanco (0,05–0,3 s); mais longo não é controle
ESPERA_MOVIMENTO = 0.5            # s: o 0x3816 chega ~0,05 s depois do 0x382A do mesmo efeito

# nome da skill/efeito (tabela opcional em pt) -> tipo; a primeira que bater vale
PALAVRAS = [
    (r"atordo", "atordoamento"),
    (r"derrub", "derrubada"),
    (r"agarr", "agarrao"),
    (r"\bsono\b|adormec", "sono"),
    (r"\bmedo\b|\bterror\b", "medo"),
    (r"sil[êe]nci", "silencio"),
    (r"conten[çc][ãa]o a[ée]rea|aprisionamento a[ée]reo", "aereo"),
    (r"conten[çc][ãa]o|grilh[ãa]o|enraiz|imobiliz", "enraizamento"),
    (r"petrifica|paralis", "controle"),
]


# ---------------- leitores ----------------

def ler_efeito(p: bytes) -> dict | None:
    """0x382A: varint alvo | u8 1 | u8 flags | varint instância | u32 efeito | i64 duração ms (−1 = sem fim) |
    u64 início | varint origem | u8 nível | [flags & 0x02: u32 skill] | u8 | 3×f32 posição."""
    try:
        r = Leitor(p)
        f = {"alvo": r.varint(5)}
        r.u8()
        flags = r.u8()
        f["inst"] = r.varint(5)
        f["efeito"] = r.u32()
        dur = r.i64()
        f["duracao_ms"] = dur if dur >= 0 else None
        r.u64()
        f["origem"] = r.varint(5)
        f["nivel"] = r.u8()
        f["skill"] = r.u32() if flags & 0x02 else None
        return f
    except ErroDecodificacao:
        return None


def ler_remocao(p: bytes) -> tuple[int, list[int]] | None:
    """0x382C: varint alvo | u8 n | n × (u8 0 | varint instância | u8 motivo). Devolve (alvo, instâncias)."""
    try:
        r = Leitor(p)
        alvo, n = r.varint(5), r.u8()
        insts = []
        for _ in range(n):
            if r.u8() != 0:
                break                 # variante com mais dados por item: o que veio antes já basta
            insts.append(r.varint(5))
            r.u8()
        return alvo, insts
    except ErroDecodificacao:
        return None


def ler_movimento(p: bytes) -> tuple[int, int, int] | None:
    """0x3816: varint alvo | varint origem | u32 efeito × 10 + k | 3×f32 posição | u8 | u8 | u8.
    Devolve (alvo, origem, efeito)."""
    try:
        r = Leitor(p)
        return r.varint(5), r.varint(5), r.u32() // 10
    except ErroDecodificacao:
        return None


# ---------------- tabelas ----------------

def carregar_tabela(caminho: str | None = None) -> dict[int, str]:
    """dados/controles.json: {"efeitos": {ID: {"tipo": ...}}} -> {ID: tipo}."""
    try:
        with open(caminho or app("dados", "controles.json"), encoding="utf-8") as f:
            efeitos = json.load(f).get("efeitos", {})
    except (OSError, ValueError):
        return {}
    return {int(k): v["tipo"] for k, v in efeitos.items() if v.get("tipo") in TIPOS}


def carregar_nomes() -> dict[int, str]:
    """Tabela opcional de nomes de skills em pt (dados/skills_pt.json ou dados_jogo/). Sem ela, vazio."""
    caminho = dados_jogo("skills_pt.json")
    if not caminho:
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def tipo_pelo_nome(nome: str) -> str | None:
    nome = (nome or "").lower()
    return next((tipo for padrao, tipo in PALAVRAS if re.search(padrao, nome)), None)


# ---------------- avisos ----------------

@dataclass
class Controle:
    inst: int
    efeito: int
    skill: int | None
    tipo: str
    inicio: float
    duracao: float | None            # s; None = o pacote não trouxe


class AvisosControle:
    """Decide quais efeitos em você são controle. Não sabe de tela: devolve Controle e a Sessao faz o cartão."""

    def __init__(self, tabela: dict[int, str] | None = None, nomes: dict[int, str] | None = None) -> None:
        self.tabela = carregar_tabela() if tabela is None else tabela
        self._nomes = nomes               # None = carrega na primeira vez que precisar
        self.ativos: dict[int, Controle] = {}
        self.pendentes: dict[int, tuple[float, dict]] = {}    # efeito sem tipo, à espera do 0x3816

    @property
    def nomes(self) -> dict[int, str]:
        if self._nomes is None:
            self._nomes = carregar_nomes()
        return self._nomes

    def limpar(self) -> None:
        self.ativos.clear()
        self.pendentes.clear()

    def _tipo(self, f: dict) -> str | None:
        e = f["efeito"]
        if e in self.tabela:
            return self.tabela[e]
        # efeitos de skill de classe são skill × 10 + n: o nome da skill descreve o efeito
        for chave in (e, e // 10, f.get("skill")):
            tipo = tipo_pelo_nome(self.nomes.get(chave or 0, ""))
            if tipo:
                return tipo
        return None

    def efeito(self, ts: float, f: dict | None, eu: int | None) -> Controle | None:
        """0x382A já lido. Só conta o que outro aplicou em você, com duração de controle (ou sem duração)."""
        if not f or eu is None or f["alvo"] != eu or f["origem"] == eu:
            return None
        dur = f["duracao_ms"] / 1000 if f["duracao_ms"] is not None else None
        if dur is not None and not MIN_S <= dur <= MAX_S:
            return None
        tipo = self._tipo(f)
        if tipo is None:
            self.pendentes = {e: v for e, v in self.pendentes.items() if ts - v[0] <= ESPERA_MOVIMENTO}
            self.pendentes[f["efeito"]] = (ts, f)
            return None
        return self._novo(ts, f, tipo)

    def movimento(self, ts: float, m: tuple[int, int, int] | None, eu: int | None) -> Controle | None:
        """0x3816 em você: o efeito que estava sem tipo vira derrubada."""
        if not m or eu is None or m[0] != eu or m[1] == eu:
            return None
        pend = self.pendentes.pop(m[2], None)
        if not pend or ts - pend[0] > ESPERA_MOVIMENTO:
            return None
        return self._novo(pend[0], pend[1], "derrubada")

    def remocao(self, ts: float, r: tuple[int, list[int]] | None, eu: int | None) -> list[Controle]:
        """0x382C em você: os controles que saíram (no tempo ou antes, quebrados)."""
        if not r or eu is None or r[0] != eu:
            return []
        return [c for c in (self.ativos.pop(i, None) for i in r[1]) if c]

    def _novo(self, ts: float, f: dict, tipo: str) -> Controle:
        dur = f["duracao_ms"] / 1000 if f["duracao_ms"] is not None else None
        c = Controle(f["inst"], f["efeito"], f.get("skill"), tipo, ts, dur)
        self.ativos = {i: x for i, x in self.ativos.items() if x.duracao is None or x.inicio + x.duracao > ts}
        self.ativos[c.inst] = c
        return c


def alerta(c: Controle, dica: str = "") -> Alerta:
    """Cartão: "ATORDOADO" com a contagem do que falta e a dica da classe ("Remoção de Impacto quebra...")."""
    return Alerta(c.inicio, "ativo", "", "controle", t("cc_" + c.tipo), tipo="controle", contagem=c.duracao,
                  nivel="alerta", id=f"controle-{c.inst}", dica=dica)
