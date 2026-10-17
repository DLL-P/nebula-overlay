"""Junta captura, remontagem, framer e decoders, e acumula as estatísticas."""

from __future__ import annotations

import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .captura import FIN, RST, SYN, Remontador, ler_segmentos
from .decoders import DECODERS, Descartada, ErroDecodificacao
from .protocolo import BLOCO, MAX_PROFUNDIDADE, OPCODES, FramerFluxo, mensagens_do_bloco


@dataclass
class EstadoFluxo:
    chave: tuple
    remontador: Remontador = field(default_factory=Remontador)
    framer: FramerFluxo = field(default_factory=FramerFluxo)
    bytes: int = 0
    mensagens: int = 0
    conhecidas: int = 0
    primeiro_ts: float = 0.0
    ultimo_ts: float = 0.0

    @property
    def parece_jogo(self) -> bool:
        return self.conhecidas >= 5 and self.conhecidas >= 0.5 * self.mensagens


@dataclass
class Fonte:
    dano: int = 0
    dano_dot: int = 0
    hits: int = 0
    criticos: int = 0
    costas: int = 0
    frente: int = 0
    parry: int = 0
    perfect: int = 0
    double: int = 0
    multi_hit: int = 0
    primeiro: float = 0.0
    ultimo: float = 0.0
    skills: Counter = field(default_factory=Counter)
    hits_por_skill: Counter = field(default_factory=Counter)


class Analise:
    def __init__(self, porta: int | None = None, observador=None) -> None:
        self.porta = porta
        self.observador = observador  # chamado como observador(ts, fluxo, profundidade, opcode, payload, resultado)
        self.fluxos: dict[tuple, EstadoFluxo] = {}
        self.opcodes = Counter()
        self.bytes_opcode = Counter()
        self.descartadas = Counter()
        self.erros = Counter()
        self.exemplo_erro: dict[int, str] = {}
        self.fontes: dict[int, Fonte] = defaultdict(Fonte)
        self.alvos: Counter = Counter()
        self.hp_max: dict[int, int] = {}
        self.hp_atual: dict[int, int] = {}
        self.mortes: dict[int, float] = {}
        self.casts: list[tuple[float, int, int, int, int]] = []  # ts, conjurador, skill, alvo, cooldown
        self.combat_power: list[tuple[float, int, int]] = []
        self.eventos_dano: list[dict] = []
        self.blocos = 0
        self.bytes_descomprimidos = 0
        self.bytes_comprimidos = 0

    # ---------- entrada ----------
    def processar_arquivo(self, caminho: str) -> None:
        for seg in ler_segmentos(caminho):
            if self.porta is not None and self.porta not in (seg.porta_origem, seg.porta_destino):
                continue
            self.processar_segmento(seg)
        for estado in self.fluxos.values():
            for dados, buraco in estado.remontador.finalizar():
                self._alimentar(estado, dados, buraco, estado.ultimo_ts)

    def processar_segmento(self, seg) -> None:
        estado = self.fluxos.get(seg.fluxo)
        if estado is None:
            estado = self.fluxos[seg.fluxo] = EstadoFluxo(seg.fluxo, primeiro_ts=seg.ts)
        estado.ultimo_ts = seg.ts
        if seg.flags & RST:
            return
        for dados, buraco in estado.remontador.push(seg.seq, seg.dados, bool(seg.flags & SYN), seg.ts):
            self._alimentar(estado, dados, buraco, seg.ts)

    def _alimentar(self, estado: EstadoFluxo, dados: bytes, buraco: bool, ts: float) -> None:
        estado.bytes += len(dados)
        for op, payload in estado.framer.alimentar(dados, buraco):
            self._mensagem(estado, ts, op, payload, 0)

    # ---------- mensagens ----------
    def _mensagem(self, estado: EstadoFluxo, ts: float, op: int, payload: bytes, prof: int) -> None:
        estado.mensagens += 1
        if op in OPCODES or op == BLOCO:
            estado.conhecidas += 1
        self.opcodes[op] += 1
        self.bytes_opcode[op] += len(payload)
        if op == BLOCO:
            self.blocos += 1
            try:
                filhas = mensagens_do_bloco(payload)
            except ValueError as e:
                self._erro(op, str(e))
                self._observar(ts, estado, prof, op, payload, ("erro", str(e)))
                return
            self.bytes_comprimidos += len(payload) - 4
            self.bytes_descomprimidos += struct.unpack_from("<I", payload, 0)[0]
            self._observar(ts, estado, prof, op, payload, ("bloco", len(filhas)))
            if prof < MAX_PROFUNDIDADE:
                for fop, fpayload in filhas:
                    self._mensagem(estado, ts, fop, fpayload, prof + 1)
            return
        dec = DECODERS.get(op)
        if dec is None:
            self._observar(ts, estado, prof, op, payload, None)
            return
        nome, funcao = dec
        try:
            campos = funcao(payload)
        except Descartada as e:
            self.descartadas[op] += 1
            self._observar(ts, estado, prof, op, payload, ("descartada", str(e)))
            return
        except ErroDecodificacao as e:
            self._erro(op, str(e))
            self._observar(ts, estado, prof, op, payload, ("erro", str(e)))
            return
        self._aplicar(nome, campos, ts)
        self._observar(ts, estado, prof, op, payload, ("ok", campos))

    def _erro(self, op: int, msg: str) -> None:
        self.erros[op] += 1
        self.exemplo_erro.setdefault(op, msg)

    def _observar(self, ts, estado, prof, op, payload, resultado) -> None:
        if self.observador:
            self.observador(ts, estado.chave, prof, op, payload, resultado)

    def _aplicar(self, nome: str, c: dict, ts: float) -> None:
        if nome in ("dano", "dot"):
            f = self.fontes[c["origem"]]
            if not f.primeiro:
                f.primeiro = ts
            f.ultimo = ts
            f.skills[c["skill"]] += c["dano"]
            f.hits_por_skill[c["skill"]] += 1
            self.alvos[c["alvo"]] += c["dano"]
            if nome == "dot":
                f.dano_dot += c["dano"]
                f.dano += c["dano"]
            else:
                f.dano += c["dano"]
                f.hits += 1
                f.criticos += c["critico"]
                f.costas += c["costas"]
                f.frente += c["frente"]
                f.parry += c["parry"]
                f.perfect += c["perfect"]
                f.double += c["double"]
                f.multi_hit += c["multi_hit_dano"]
            self.eventos_dano.append({"ts": ts, "tipo": nome, **c})
        elif nome == "hp":
            e, hp = c["entidade"], c["hp"]
            self.hp_atual[e] = hp
            self.hp_max[e] = max(self.hp_max.get(e, 0), hp)
        elif nome == "morte":
            self.mortes.setdefault(c["entidade"], ts)
        elif nome == "inicio_skill":
            self.casts.append((ts, c["conjurador"], c["skill"], c["alvo"], c["cooldown_ms"]))
        elif nome == "combat_power":
            self.combat_power.append((ts, c["combat_power"], c["combat_power_maximo"]))

    # ---------- consultas ----------
    def fluxos_do_jogo(self) -> list[EstadoFluxo]:
        return sorted((f for f in self.fluxos.values() if f.parece_jogo), key=lambda f: -f.conhecidas)

    def jogadores(self) -> set[int]:
        """Entidades que causam dano com skills de classe (faixas 11..18 milhões)."""
        return {fid for fid, f in self.fontes.items() if any(11 <= s // 1_000_000 <= 18 for s in f.skills)}
