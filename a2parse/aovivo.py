"""Processamento em tempo real: pacote → evento → motor de alertas.

Sem interface gráfica: o overlay (overlay.py) chama `Sessao.segmento()` para cada
segmento TCP e `Sessao.estado(agora)` para desenhar a tela.

Identificação automática (validada na captura de 2026-10-16):
- 0x3633 OwnCharacterInfo começa com o seu ID (varint) e traz o seu nome. O ID
  muda a cada troca de zona, então ele é relido sempre que o pacote chega.
- 0x3645 CharacterInfo começa com o ID (varint) de outro jogador e traz o nome
  dele, para mostrar "MERGULHO → Fulano".
- 0x3641 (spawn) traz varint ID | u16 flags | u8 | u32 código do mob. O código
  do mob leva ao boss no mecanicas.json (ou ao nome no npcs.json).
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field

from .alertas import Alerta, MotorAlertas, boss_por_npc, carregar_dicas
from .analise import Analise
from .classes import NOME as NOME_CLASSE, PAPEL, DetectorClasse, classe_do_pc
from . import controle as cc
from .decoders import Leitor
from .eventos import Eventos
from .grupo import ler_perfis
from .latencia import Latencia
from .meter import Medidor
from .roteiro import Previsor, carregar as carregar_roteiros, medidor_atordoamento

from .caminhos import dados_jogo


def carregar_npcs() -> dict[int, dict]:
    """Tabela opcional de NPCs (nome, isBoss). Sem ela, só os bosses do mecanicas.json são reconhecidos."""
    caminho = dados_jogo("npcs.json")
    if not caminho:
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def ler_spawn(p: bytes) -> tuple[int, int] | None:
    """0x3641: (entidade, código do mob)."""
    r = ler_spawn_completo(p)
    return (r[0], r[1]) if r else None


def ler_spawn_completo(p: bytes) -> tuple[int, int, str | None] | None:
    """0x3641 SummonMapping: (entidade, código do mob, nome do dono ou None).

    varint entidade | u16 | u8 flag | [flag 1: u8 tamanho | nome do dono] | u32 mob | ...
    Na run de 2026-10-16 17:11, a invocação do Clérigo trouxe "NuncaErrei" aqui; as do Mago (mob
    2920655) e os bosses vêm com flag 0, sem dono.
    """
    if len(p) < 12:
        return None
    try:
        r = Leitor(p)
        ent = r.varint(5)
        r.u16()
        dono = None
        if r.u8() == 1:
            n = r.u8()
            dono = p[r.o:r.o + n].decode("utf-8", "replace") if 0 < n <= 32 else None
            r.pular(n)
        return ent, r.u32(), dono
    except Exception:
        return None


def ler_eu(p: bytes) -> tuple[int, str] | None:
    """0x3633: (seu ID, seu nome). Layout: varint ID | u32 | u8 | u8 tamanho | nome UTF-8 | u16 servidor | u8 classe."""
    r = ler_eu_completo(p)
    return (r[0], r[1]) if r else None


def ler_eu_completo(p: bytes) -> tuple[int, str, int | None, int | None] | None:
    """(ID, nome, servidor, ID de classe). Na captura de 2026-10-16: servidor 1406 (Ariel), classe 6 (Gladiador)."""
    try:
        r = Leitor(p)
        ent = r.varint(5)
        r.u32()
        r.u8()
        n = r.u8()
        nome = p[r.o:r.o + n].decode("utf-8", "replace") if 0 < n <= 32 else ""
        r.pular(n)
        servidor = classe = None
        if len(p) >= r.o + 3:
            servidor, classe = r.u16(), r.u8()
        return ent, nome, servidor, classe
    except Exception:
        return None


def ler_nome(p: bytes) -> tuple[int, str] | None:
    """0x3645: (ID, nome). Layout: varint ID | u8 | u8 | varint | u8 | ... | u8 tamanho | nome UTF-8.

    O trecho entre o ID e o tamanho varia (1 byte a mais em alguns personagens), então
    o nome é o primeiro texto UTF-8 legível com prefixo de tamanho nos 12 bytes seguintes.
    """
    try:
        r = Leitor(p)
        ent = r.varint(5)
    except Exception:
        return None
    for k in range(r.o + 3, min(r.o + 12, len(p))):
        n = p[k]
        if not 1 <= n <= 32 or k + 1 + n > len(p):
            continue
        try:
            nome = p[k + 1:k + 1 + n].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if nome.isprintable() and not nome[0].isspace():
            return ent, nome
    return None


@dataclass
class BossVivo:
    entidade: int
    nome: str
    motor: MotorAlertas | None
    max_hp: int = 0
    hp: int = 0
    morto: bool = False
    visto: float = 0.0
    previsor: Previsor | None = None
    atordoamento: tuple[int, int] | None = None     # (atual, máximo) do medidor 0xE005

    @property
    def pct(self) -> float:
        return 100.0 * self.hp / self.max_hp if self.max_hp else 100.0


@dataclass
class Sessao:
    dados: dict
    pre_aviso: bool = True
    burst: bool = True
    papel_fixo: str | None = None       # --papel: força o papel em vez do padrão da classe
    classe_fixa: str | None = None      # --classe: força a classe em vez da detectada
    com_dicas: bool = True
    antecipar: float = 0.8              # s: passos previstos aparecem antes (pedido do usuário: entre 0,5 e 1 s)
    centro_antes: float = 5.0           # s: previsões confiáveis sobem para o centro com essa antecedência (0 desliga)
    roteiros: dict | None = None        # mecanicas/roteiros.json (roteiros.py); None = carrega do disco
    controle: bool = False              # avisos de controle em você (ATORDOADO 2s + dica da classe); opcional
    alertas: list[Alerta] = field(default_factory=list)
    bosses: dict[int, BossVivo] = field(default_factory=dict)
    eu: int | None = None
    meu_nome: str = ""
    jogo_visto: bool = False
    mensagens: int = 0
    nomes: dict[int, str] = field(default_factory=dict)
    odyle: tuple[int, int] | None = None   # energia Odyle: (restante, recarga), mostrada como "0 (+35)"
    perfis: dict = field(default_factory=dict)  # nome -> {classe, nivel, gs, cp} (lista do grupo, 0x9702/0x970B)
    grupo: list = field(default_factory=list)   # nomes do grupo, na ordem da última lista
    zona_com_boss: bool = False         # algum boss apareceu desde a última troca de zona (usado pela gravação)
    eventos: Eventos | None = None      # eventos de campo (Festival Shugo...); o overlay passa o mesmo entre conexões
    ultimo_ts: float = 0.0

    def __post_init__(self) -> None:
        self.npcs = carregar_npcs()
        self.classe = DetectorClasse()
        self.medidor = Medidor()
        self.latencia = Latencia()
        if self.eventos is None:
            self.eventos = Eventos()
        if self.roteiros is None:
            self.roteiros = carregar_roteiros()
        self.dicas = carregar_dicas() if self.com_dicas else {}
        self.avisos_controle = cc.AvisosControle()
        self.dados.setdefault("categorias_alerta", {}).setdefault("controle", dict(cc.CATEGORIA))
        self.analise = Analise(observador=self._observar)
        from collections import deque
        self.analise.eventos_dano = deque(maxlen=2000)   # ao vivo não precisa guardar a sessão inteira

    # ---------- entrada ----------
    def segmento(self, seg) -> None:
        self.analise.processar_segmento(seg)
        self.latencia.segmento(seg, self.analise.fluxos)

    @property
    def minha_classe(self) -> str | None:
        return self.classe_fixa or self.classe.classe

    @property
    def meu_papel(self) -> str | None:
        return self.papel_fixo or PAPEL.get(self.minha_classe or "")

    def tick(self, agora: float) -> None:
        """Entrega passos de sequência que vencem mesmo sem pacote novo."""
        self.medidor.tick(agora)
        classe, papel = self.minha_classe, self.meu_papel
        for b in self.bosses.values():
            if b.motor:
                b.motor.classe, b.motor.papel = classe, papel
                self.alertas += b.motor.avancar(agora)
        self._podar(agora)

    # ---------- saída ----------
    def boss_atual(self) -> BossVivo | None:
        vivos = [b for b in self.bosses.values() if not b.morto and b.max_hp]
        return max(vivos, key=lambda b: b.visto) if vivos else None

    def estado(self, agora: float) -> dict:
        ativos = [a for a in self.alertas if a.t <= agora < a.t + (4.0 if a.fase == "breve" else a.duracao)]
        prio = {"alarme": 3, "alerta": 2, "info": 1}
        cartoes = sorted((a for a in ativos if a.fase == "ativo"), key=lambda a: (-prio.get(a.nivel, 0), -a.t))[:2]
        breve = [a for a in ativos if a.fase == "breve"][-1:]
        b = self.boss_atual()
        status = []
        for x in self.bosses.values():
            if x.motor and not x.morto:
                for s in x.motor.status_ativos(agora):
                    s["voce"] = s["alvo"] is not None and s["alvo"] == self.eu
                    s["nome"] = "VOCÊ" if s["voce"] else self.nomes.get(s["alvo"], "") if s["alvo"] is not None else ""
                    status.append(s)
        meter = self.medidor.estado(agora, self.nomes, self.eu, status)
        status += self._chips_burst(agora)
        linha, centro = self._linha_do_tempo(b, agora, cartoes)
        return {
            "meter": meter,
            "linha": linha,
            "centro": centro,
            "atordoamento": b.atordoamento if b else None,
            "odyle": self.odyle,
            "perfis": self.perfis,
            "grupo": [self.perfis[n] for n in self.grupo if n in self.perfis],
            "latencia": self.latencia.estado(agora),
            "status": status,
            "cartoes": cartoes,
            "breve": breve[0] if breve else None,
            "boss": b,
            "proximos": b.motor.proximos(agora)[:5] if b and b.motor else [],
            "eu": self.meu_nome or (str(self.eu) if self.eu else ""),
            "classe": NOME_CLASSE.get(self.minha_classe or "", ""),
            "classe_chave": self.minha_classe,
            "papel": self.meu_papel or "",
            "jogo": self.jogo_visto,
            "mensagens": self.mensagens,
        }

    def _linha_do_tempo(self, b: BossVivo | None, agora: float, cartoes: list) -> tuple[list[dict], dict | None]:
        """O que vem a seguir: passos já agendados (exatos) + previsões (roteiro, HP, atordoamento, ciclos).
        Devolve a lista (para o meter) e o item que sobe para o centro (confiança ≥ 0,7 e a ≤ centro_antes s)."""
        if not b:
            return [], None
        itens = []
        if b.motor:
            for p in b.motor.proximos(agora):
                if "eta" in p:
                    itens.append({"texto": p["texto"], "tipo": p["tipo"], "eta": p["eta"], "confianca": 1.0,
                                  "exata": True, "fonte": "sequencia"})
        if b.previsor:
            from .alertas import passos_completos
            from .classes import ALCANCE
            fichas = {m.get("id"): m for m in (b.motor.boss["mecanicas"] if b.motor else [])}
            for p in b.previsor.linha(agora):
                texto, tipo = p.texto, p.tipo
                m = fichas.get(p.no)
                if m is not None:
                    # o mesmo filtro dos alertas: o leque é só do tank, o ENGAJE só de quem bate de perto
                    passos = passos_completos(m, False, self.meu_papel, ALCANCE.get(self.minha_classe or ""),
                                              self.minha_classe)
                    if not passos:
                        continue
                    texto, tipo = passos[0]["texto"], passos[0].get("tipo", tipo)
                if any(i["texto"] == texto and abs(i["eta"] - p.eta) < 2.5 for i in itens):
                    continue                                   # já agendado pela sequência: vale o exato
                itens.append({"texto": texto, "tipo": tipo, "eta": p.eta, "confianca": p.confianca,
                              "exata": p.exata, "fonte": p.fonte})
        itens = sorted((i for i in itens if -0.5 <= i["eta"] <= 40), key=lambda i: i["eta"])
        centro = None
        if self.centro_antes > 0:
            na_tela = {a.texto for a in cartoes}
            for i in itens:
                if i["confianca"] >= 0.75 and 0 <= i["eta"] <= self.centro_antes and i["texto"] not in na_tela:
                    centro = i
                    break
        return itens, centro

    def _chips_burst(self, agora: float) -> list[dict]:
        """SEGURA O BURST até o próximo "BURST AGORA"; BURST AGORA por 10 s."""
        ultimo = None
        for a in self.alertas:
            if a.id.endswith("-atordoado"):
                continue                      # o atordoamento já tem o próprio chip (ATORDOADO, 5 s)
            if a.tipo in ("burst", "segurar_burst") and a.t <= agora and (ultimo is None or a.t >= ultimo.t):
                ultimo = a
        if ultimo is None:
            return []
        base = {"em": "boss", "alvo": None, "voce": False, "nome": "", "id": ultimo.id}
        if ultimo.tipo == "burst":
            if agora - ultimo.t < 10:
                return [dict(base, texto="BURST AGORA", tipo="burst", restante=ultimo.t + 10 - agora, total=10.0)]
            return []
        b = self.boss_atual()
        eta = next((p["eta"] for p in (b.motor.proximos(agora) if b and b.motor else []) if p["texto"] == "BURST AGORA"), None)
        if eta is None:
            return [] if agora - ultimo.t > 20 else [dict(base, texto="SEGURA O BURST", tipo="segurar_burst",
                                                          restante=20 - (agora - ultimo.t), total=20.0)]
        return [dict(base, texto="SEGURA O BURST", tipo="segurar_burst", restante=eta, total=eta + (agora - ultimo.t))]

    # ---------- interno ----------
    def _observar(self, ts, fluxo, prof, op, payload, resultado) -> None:
        self.mensagens += 1
        self.jogo_visto = True
        self.ultimo_ts = ts
        if op == 0x3633:
            r = ler_eu_completo(payload)
            if r:
                self.zona_com_boss = False          # trocou de zona: os bosses da nova zona aparecem logo depois
                if r[1] and r[1] != self.meu_nome:
                    self.classe.reset()          # trocou de personagem
                self.eu, self.meu_nome = r[0], r[1] or self.meu_nome
                if self.meu_nome:
                    self.nomes[self.eu] = self.meu_nome     # o ID muda a cada zona: o meter acha você em qualquer um
                if r[3] is not None:
                    self.classe.do_pacote = classe_do_pc(r[3]) or self.classe.do_pacote
                for b in self.bosses.values():
                    if b.motor:
                        b.motor.eu = self.eu
                self.avisos_controle.limpar()
            return
        if op in (0x382A, 0x382C, 0x3816):
            if self.controle:
                self._controle(ts, op, bytes(payload))
            return
        if op == 0x3645:
            r = ler_nome(payload)
            if r:
                self.nomes[r[0]] = r[1]
            return
        if op == 0xE005:
            r = medidor_atordoamento(payload)
            if r and r[0] in self.bosses:
                b = self.bosses[r[0]]
                b.atordoamento = (r[1], r[2])
                if b.previsor:
                    b.previsor.atordoamento(ts, r[1], r[2])
            return
        if op in (0x6000, 0x6001):
            self.eventos.mensagem(op, bytes(payload))
            return
        if op in (0x9702, 0x970B):
            lista = ler_perfis(bytes(payload))
            for x in lista:
                self.perfis[x["nome"]] = x
            if op == 0x9702 and lista:
                self.grupo = [x["nome"] for x in lista]
            return
        if op == 0x3641:
            r = ler_spawn_completo(payload)
            if r:
                if r[2]:
                    self.medidor.donos_nome[r[0]] = r[2]      # invocação com dono declarado
                self._spawn(ts, r[0], r[1])
            return
        if not resultado or resultado[0] != "ok":
            return
        c = resultado[1]
        if op == 0x3656:                         # seu CP (o "maior" é o que o perfil do jogo mostra)
            if self.meu_nome:
                eu = self.perfis.setdefault(self.meu_nome, {"nome": self.meu_nome})
                eu["cp"] = c["combat_power_maximo"] or c["combat_power"]
            return
        if op == 0x3600:
            self.eventos.relogio(ts, c["horario_servidor"])
            self.latencia.relogio(ts, c["horario_servidor"])
            return
        if op in (0x610B, 0x610C):
            from .decoders import ODYLE
            for t in c["tickets"]:
                if t["ticket"] == ODYLE:
                    self.odyle = (t["restante"], t["recarga"])
            return
        if self.eu is not None and op in (0x3804, 0x3802) and c.get("origem", c.get("conjurador")) == self.eu:
            self.classe.skill(c["skill"])
        if op in (0x3804, 0x3805):
            self.medidor.dano(ts, c, self.bosses, lambda e: e in self.nomes or e == self.eu)
        if op == 0x8D00 and c["entidade"] in self.bosses:
            b = self.bosses[c["entidade"]]
            b.hp, b.max_hp, b.visto = c["hp"], max(b.max_hp, c["hp"]), ts
            if b.previsor:
                b.previsor.hp_pct(ts, b.pct)
            if b.motor:
                self.alertas += b.motor.hp(ts, b.pct)
        elif op == 0x3802 and c["conjurador"] in self.bosses:
            b = self.bosses[c["conjurador"]]
            b.visto = ts
            if b.previsor:
                b.previsor.cast(ts, c["skill"])
            if b.motor:
                self.alertas += b.motor.skill(ts, c["skill"], c["alvo"])
        elif op == 0x3809 and c["conjurador"] in self.bosses:
            b = self.bosses[c["conjurador"]]
            b.visto = ts
            if b.motor:
                self.alertas += b.motor.preparo(ts, c["skill"], c["alvo"])
        elif op == 0x3642 and c["entidade"] in self.bosses:
            b = self.bosses[c["entidade"]]
            b.morto = True
            # boss morto não executa o que estava preparando: some com os avisos dele que ainda estão na tela
            self.alertas = [a for a in self.alertas if a.boss != b.nome or a.t + a.duracao <= ts]
            if b.motor:
                b.motor.ativas.clear()
            self.medidor.morte(ts, c["entidade"])
        self.tick(ts)

    def _controle(self, ts: float, op: int, p: bytes) -> None:
        """Controle em você: um cartão por vez, com a contagem; some quando o efeito sai (no tempo ou quebrado)."""
        av = self.avisos_controle
        if op == 0x382C:
            for c in av.remocao(ts, cc.ler_remocao(p), self.eu):
                self._encerrar_controle(ts, f"controle-{c.inst}")
            return
        novo = av.efeito(ts, cc.ler_efeito(p), self.eu) if op == 0x382A else av.movimento(ts, cc.ler_movimento(p), self.eu)
        if novo is None:
            return
        self._encerrar_controle(ts, None)                  # o controle novo substitui o anterior na tela
        self.alertas.append(cc.alerta(novo, self.dicas.get(self.minha_classe or "", {}).get("controle", "")))

    def _encerrar_controle(self, ts: float, id_: str | None) -> None:
        """Encurta o cartão de controle (id_ None = todos) para sair da tela agora."""
        for a in self.alertas:
            if a.mecanica == "controle" and (id_ is None or a.id == id_) and a.t <= ts < a.t + a.duracao:
                a.contagem = max(0.01, ts - a.t)

    def _spawn(self, ts: float, ent: int, mob: int) -> None:
        b = boss_por_npc(self.dados, mob)
        info = self.npcs.get(mob, {})
        if b is None and not info.get("isBoss"):
            return
        nome = b["nome"] if b else info.get("name", f"boss {mob}")
        motor = MotorAlertas(b, pre_aviso=self.pre_aviso, modo_skills=True, eu=self.eu, burst=self.burst,
                             papel=self.meu_papel, classe=self.minha_classe, dicas=self.dicas,
                             antecipar=self.antecipar) if b else None
        self.zona_com_boss = True
        rot = (self.roteiros or {}).get(nome)
        previsor = Previsor(rot, b or {"nome": nome, "mecanicas": []}) if rot else None
        self.bosses[ent] = BossVivo(ent, nome, motor, visto=ts, previsor=previsor)

    def _podar(self, agora: float) -> None:
        if len(self.alertas) > 200:
            self.alertas = [a for a in self.alertas if a.t + 30 > agora]
