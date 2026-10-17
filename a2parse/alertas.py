"""Motor de alertas de mecânica.

Lê o mecanicas.json e, a partir de eventos (HP do boss, início de skill, boss
sumindo da tela), decide que alerta mostrar e quando. Não sabe de onde vêm os
eventos: a mesma lógica serve para a curva de HP do vídeo, para uma .pcapng e,
depois, para a captura ao vivo.

Ideias emprestadas dos boss mods de outros MMOs:
- três níveis de gravidade, como info/alert/alarm do cactbot;
- sequências que se reancoram em eventos reais dentro de uma janela, como as
  linhas "sync ... window antes,depois" das timelines do cactbot;
- lista de próximos eventos com ETA, como as barras do BigWigs e do DBM;
- ID estável por mecânica, para o usuário desligar ou reescrever alertas.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .caminhos import app, usuario

CAMINHO_MECANICAS = app("mecanicas", "mecanicas.json")
CAMINHO_USUARIO = usuario("mecanicas", "usuario.json")       # seus ajustes por ID de mecânica

DURACAO_PADRAO = 3.0      # alerta sem contagem própria fica 3 s (padrão do cactbot)
LIMIAR_RESET = 99.0       # HP voltou a esse nível depois de cair: o boss resetou (wipe)
TIPOS_ALARME = {"esconder", "parar_dano", "stagger", "enrage"}


# ---------------- dados ----------------

def carregar_mecanicas(caminho: str | None = None, usuario: str | None = CAMINHO_USUARIO) -> dict:
    with open(caminho or CAMINHO_MECANICAS, encoding="utf-8") as f:
        dados = json.load(f)
    if usuario and os.path.exists(usuario):
        with open(usuario, encoding="utf-8") as f:
            aplicar_usuario(dados, json.load(f))
    return dados


def aplicar_usuario(dados: dict, u: dict) -> None:
    """Preferências do usuário por ID de mecânica: {"desligadas": [...], "textos": {id: texto}, "voz": {id: texto}}."""
    desligadas = set(u.get("desligadas", []))
    for mz in dados["masmorras"]:
        for b in mz["bosses"]:
            b["mecanicas"] = [m for m in b["mecanicas"] if m.get("id") not in desligadas]
            for m in b["mecanicas"]:
                if m.get("id") in u.get("textos", {}):
                    novo = u["textos"][m["id"]]
                    m["alerta"] = novo
                    if m.get("sequencia"):
                        m["sequencia"][0]["texto"] = novo
                if m.get("id") in u.get("voz", {}):
                    m["voz"] = u["voz"][m["id"]]


def masmorra(dados: dict, nome: str) -> dict:
    for m in dados["masmorras"]:
        if m["nome"].lower() == nome.lower():
            return m
    raise KeyError(f"masmorra não encontrada: {nome}")


def boss(dados: dict, nome: str) -> dict:
    for m in dados["masmorras"]:
        for b in m["bosses"]:
            if b["nome"].lower() == nome.lower():
                return b
    raise KeyError(f"boss não encontrado: {nome}")


def boss_por_npc(dados: dict, npc_id: int) -> dict | None:
    for m in dados["masmorras"]:
        for b in m["bosses"]:
            for ids in b.get("ids", {}).values():
                if npc_id in ids:
                    return b
    return None


# ---------------- alertas ----------------

@dataclass(order=True)
class Alerta:
    t: float
    fase: str = field(compare=False)            # "breve" (aviso prévio) ou "ativo"
    boss: str = field(compare=False)
    mecanica: str = field(compare=False)
    texto: str = field(compare=False)
    sub: str = field(compare=False, default="")
    tipo: str = field(compare=False, default="atencao")
    contagem: float | None = field(compare=False, default=None)
    wipe: bool = field(compare=False, default=False)
    passo: int = field(compare=False, default=0)
    nivel: str = field(compare=False, default="info")   # info, alerta, alarme
    voz: str | None = field(compare=False, default=None)
    contagem_voz: bool = field(compare=False, default=False)
    id: str = field(compare=False, default="")
    dica: str = field(compare=False, default="")          # dica da sua classe para esta ação
    voz_curta: str = field(compare=False, default="")     # chave da palavra de ordem (voz.py); vazio = pelo tipo

    @property
    def duracao(self) -> float:
        return self.contagem if self.contagem else DURACAO_PADRAO


def nivel_de(tipo: str, wipe: bool, fase: str = "ativo") -> str:
    if fase == "breve" or tipo in ("atencao", "burst", "segurar_burst"):
        return "info"
    if tipo in TIPOS_ALARME or wipe:
        return "alarme"
    return "alerta"


def passos_de(m: dict) -> list[dict]:
    if m.get("sequencia"):
        return m["sequencia"]
    if not m.get("alerta"):
        return []
    return [{"t": 0.0, "texto": m["alerta"], "sub": m.get("acao", ""), "tipo": m.get("acao_tipo", "atencao"),
             "voz": m.get("voz")}]


BURST = {"segurar": ("SEGURA O BURST", "segurar_burst"), "soltar": ("BURST AGORA", "burst")}


def passos_completos(m: dict, burst: bool = True, papel: str | None = None, alcance: str | None = None,
                     classe: str | None = None) -> list[dict]:
    """Passos da mecânica + janelas de burst, já filtrados e reescritos para o seu papel, alcance e classe."""
    passos = []
    for p in passos_de(m):
        papeis = p.get("papeis") or m.get("papeis")
        if papel and papeis and papel not in papeis:
            continue
        if alcance == "longe" and (p.get("so_perto") or m.get("so_perto")):
            continue                      # ENGAJE e afins: quem bate de longe segue contribuindo
        classes = p.get("classes") or m.get("classes")
        if classe and classes and classe not in classes:
            continue                      # ex.: o vermelho do Thamon só para quem dá dano físico
        troca = (p.get("por_papel") or {}).get(papel or "") or (m.get("por_papel") or {}).get(papel or "")
        if troca:
            p = dict(p, **troca)
        troca = (p.get("por_classe") or {}).get(classe or "") or (m.get("por_classe") or {}).get(classe or "")
        passos.append(dict(p, **troca) if troca else p)
    if burst:
        for b in m.get("burst", []):
            texto, tipo = BURST[b["acao"]]
            passos.append({"t": b["t"], "texto": texto, "sub": b.get("sub", ""), "tipo": tipo, "burst": True})
    return sorted(passos, key=lambda p: float(p.get("t", 0)))


def carregar_dicas(caminho: str | None = None) -> dict:
    """dados/dicas_classes.json: {CLASSE: {tipo_de_ação: dica}}."""
    caminho = caminho or app("dados", "dicas_classes.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def pct_gatilho(m: dict, usar_observado: bool = True) -> float | None:
    g = m.get("gatilho") or {}
    if g.get("tipo") != "hp":
        return None
    if usar_observado and g.get("pct_observado") is not None:
        return float(g["pct_observado"])
    return float(g["pct"])


@dataclass
class Sequencia:
    """Uma mecânica disparada: passos com tempo relativo a 'base', que pode ser reancorada."""
    mec: dict
    base: float
    passos: list[dict]
    proximo: int = 0
    sincronizados: set = field(default_factory=set)
    criada: float = 0.0              # quando o motor criou a sequência (pode ser antes da base)
    precursora: bool = False         # criada por uma skill que sempre vem antes; espera a confirmação
    criada_por_precursora: bool = False

    def hora(self, i: int) -> float:
        return self.base + float(self.passos[i].get("t", 0))

    @property
    def acabou(self) -> bool:
        return self.proximo >= len(self.passos)


@dataclass
class Status:
    """Um estado com duração no boss ("NO CÉU") ou num jogador ("MERGULHO → Fulano").

    Os tempos são relativos à base da sequência da mecânica, então andam junto quando ela é reancorada.
    """
    mec_id: str
    texto: str
    tipo: str
    em: str                      # "boss" ou "alvo"
    alvo: int | None
    seq: Sequencia
    de: float
    ate: float

    @property
    def inicio(self) -> float:
        return self.seq.base + self.de

    @property
    def fim(self) -> float:
        return self.seq.base + self.ate


class MotorAlertas:
    """Avalia as mecânicas de UM boss. Crie um por luta (ou chame reset em wipe)."""

    def __init__(self, boss: dict, pre_aviso: bool = True, usar_observado: bool = True, tolerancia: float = 0.0,
                 modo_skills: bool = False, eu: int | None = None, burst: bool = True,
                 papel: str | None = None, classe: str | None = None, dicas: dict | None = None,
                 antecipar: float = 0.0) -> None:
        """tolerancia: pontos de % acima do gatilho que já contam como cruzado (fonte ruidosa, como o vídeo).
        modo_skills: a fonte tem skills (captura/ao vivo); mecânicas marcadas "fallback_video" ficam de fora.
        eu: ID da sua entidade, para alertas pessoais ("o mergulho é em você")."""
        self.boss = boss
        self.nome = boss["nome"]
        self.pre_aviso = pre_aviso
        self.usar_observado = usar_observado
        self.tolerancia = tolerancia
        self.modo_skills = modo_skills
        self.eu = eu
        self.burst = burst
        self.antecipar = antecipar        # s: passos previstos saem antes, e a contagem cresce o mesmo tanto
        self.papel = papel                 # "tank", "healer", "dps", "suporte"; None = vê tudo
        self.classe = classe               # "GLADIATOR", ... (a2parse.classes)
        self.dicas = dicas or {}           # {classe: {acao_tipo: dica}} de dados/dicas_classes.json
        self.reset()

    def _ativa(self, m: dict) -> bool:
        return not (self.modo_skills and m.get("fallback_video"))

    def reset(self) -> None:
        self.inicio: float | None = None
        self.disparadas: dict[int, float] = {}
        self.avisadas: set[int] = set()
        self.ativas: list[Sequencia] = []
        self._confirmaveis: list[Sequencia] = []    # precursoras já emitidas, ainda à espera da skill real
        self.status: list[Status] = []
        self.menor_hp = 100.0
        self.ultimo_hp = 100.0
        self.ajustes: list[tuple[float, str, float]] = []   # (t, mecânica, correção em s), como o test_timeline do cactbot

    # ---------- eventos ----------
    def comecar(self, t: float) -> None:
        if self.inicio is not None:
            return
        self.inicio = t
        for m in self.boss["mecanicas"]:
            g = m.get("gatilho") or {}
            if g.get("tipo") == "enrage" and g.get("segundos"):
                fim = float(g["segundos"])
                passos = [{"t": max(0.0, fim - 60), "texto": "ENRAGE EM 60s", "sub": m.get("acao", ""), "tipo": "enrage", "contagem": 60.0},
                          {"t": fim, "texto": "ENRAGE", "sub": m.get("acao", ""), "tipo": "enrage"}]
                seq = Sequencia(m, t, passos)
                self.ativas.append(seq)
                self.status.append(Status(m.get("id", ""), "ENRAGE", "enrage", "boss", None, seq, max(0.0, fim - 60), fim))

    def hp(self, t: float, pct: float) -> list[Alerta]:
        """Novo valor de HP (%) do boss no instante t (segundos)."""
        self.comecar(t)
        if pct >= LIMIAR_RESET and self.menor_hp < 95:
            self.reset()              # o boss voltou cheio: wipe ou reset
            self.comecar(t)
        self.menor_hp = min(self.menor_hp, pct)
        self.ultimo_hp = pct
        saida: list[Alerta] = []
        for i, m in enumerate(self.boss["mecanicas"]):
            alvo = pct_gatilho(m, self.usar_observado)
            if alvo is None or i in self.disparadas or not self._ativa(m):
                continue
            if pct <= alvo + self.tolerancia:
                self._disparar(i, m, t)
            elif self.pre_aviso and i not in self.avisadas and pct <= alvo + m.get("pre_aviso_pct", 5) and passos_de(m):
                self.avisadas.add(i)
                p0 = passos_de(m)[0]
                saida.append(Alerta(t, "breve", self.nome, m["nome"], f"EM BREVE: {p0['texto']}",
                                    f"em {alvo:g}% (agora {pct:.0f}%)", m.get("acao_tipo", "atencao"), None,
                                    m.get("wipe", False), 0, "info", None, False, m.get("id", "")))
        return saida + self.avancar(t)

    def preparo(self, t: float, skill_id: int, alvo: int | None = None) -> list[Alerta]:
        """O boss começou a preparar uma skill (0x3809): avisa já, com a contagem até o cast previsto.

        O atraso entre preparo e cast é fixo por skill ("preparo_s" no gatilho, medido com mapear.py).
        Quando o 0x3802 chega, ele só acerta o tempo (não repete o aviso).
        """
        self.comecar(t)
        for i, m in enumerate(self.boss["mecanicas"]):
            g = m.get("gatilho") or {}
            antes = (g.get("preparo_s") or {}).get(str(skill_id))
            if antes is None or not self._ativa(m):
                continue
            if g.get("pessoal") and (self.eu is None or alvo != self.eu):
                continue
            base = t + float(antes)
            if any(s.mec is m and s.precursora and abs(s.base - base) <= 1.5 for s in self.ativas + self._confirmaveis):
                continue                      # outra precursora (ex.: a 1600880 das faixas) já avisou
            ultimo = self.disparadas.get(i)
            if ultimo is not None and base - ultimo < g.get("supressao_s", 0):
                continue
            self._disparar(i, m, base, alvo, criada=t, precursora=True)
        return self.avancar(t)

    def skill(self, t: float, skill_id: int, alvo: int | None = None) -> list[Alerta]:
        """O boss iniciou uma skill (0x3802): dispara mecânicas mapeadas e serve de sync.

        Mecânicas com "pessoal": true só disparam quando o alvo da skill é você (self.eu).
        """
        self.comecar(t)
        for i, m in enumerate(self.boss["mecanicas"]):
            g = m.get("gatilho") or {}
            ids = g.get("skill_ids") or ([g["skill_id"]] if g.get("skill_id") else [])
            pre = g.get("precursor") or {}
            if skill_id in pre.get("ids", []) and self._ativa(m):
                # a skill que sempre vem antes: agenda a mecânica para daqui a "antes" s e já avisa agora
                self._disparar(i, m, t + float(pre["antes"]), alvo, criada=t, precursora=True)
                continue
            if g.get("tipo") != "skill" or skill_id not in ids or not self._ativa(m):
                continue
            prevista = next((s for s in self.ativas + self._confirmaveis
                             if s.mec is m and s.precursora and abs(t - s.base) <= pre.get("janela", 2.0)), None)
            if prevista:
                prevista.base, prevista.precursora = t, False     # chegou a skill de verdade: só acerta o tempo
                self.disparadas[i] = t
                for st in self.status:                           # e agora sabemos em quem caiu
                    if st.seq is prevista and st.em == "alvo" and alvo is not None:
                        st.alvo = alvo
                continue
            if g.get("pessoal") and (self.eu is None or alvo != self.eu):
                continue
            ultimo = self.disparadas.get(i)
            if ultimo is not None and t - ultimo < g.get("supressao_s", 0):
                continue                      # como o suppressSeconds do cactbot: um alerta por rajada
            self._disparar(i, m, t, alvo)     # skills se repetem: cada cast é um alerta
        self.sync(t, "skill", skill_id)
        return self.avancar(t)

    def sync(self, t: float, evento: str, valor: int | None = None) -> None:
        """Reancora sequências ativas cujo próximo passo espera esse evento dentro da janela."""
        for s in self.ativas:
            # inclui passos já emitidos: o alerta pode ter saído pela previsão um pouco antes do evento real
            for i in range(len(s.passos)):
                sy = s.passos[i].get("sync")
                if not sy or sy.get("evento") != evento or i in s.sincronizados:
                    continue
                if evento == "skill" and valor not in sy.get("ids", []):
                    continue
                antes, depois = sy.get("janela", [2.5, 2.5])
                previsto = s.hora(i)
                if previsto - antes <= t <= previsto + depois:
                    s.base += t - previsto          # os passos seguintes andam junto
                    s.sincronizados.add(i)
                    self.ajustes.append((t, s.mec["nome"], t - previsto))
                break

    def _antecedencia(self, s: Sequencia, i: int) -> float:
        """Quanto antes do horário previsto o passo sai: tudo, no 1º passo de uma precursora;
        senão até self.antecipar, sem nunca sair antes de a sequência existir."""
        folga = max(0.0, s.hora(i) - s.criada)
        if s.criada_por_precursora and float(s.passos[i].get("t", 0)) == 0:
            return folga                  # tudo o que sai junto com o cast sai no preparo
        return min(self.antecipar, folga)

    def avancar(self, t: float) -> list[Alerta]:
        """Entrega os passos cujo horário já chegou (menos a antecedência)."""
        saida = []
        for s in self.ativas:
            while not s.acabou and s.hora(s.proximo) - self._antecedencia(s, s.proximo) <= t:
                saida.append(self._alerta(s, s.proximo))
                s.proximo += 1
        acabaram = [s for s in self.ativas if s.acabou and s.precursora]
        self._confirmaveis = [s for s in self._confirmaveis + acabaram if s.base + 5 > t]
        self.ativas = [s for s in self.ativas if not s.acabou]
        return sorted(saida)

    def proximos(self, t: float, horizonte: float = 30.0) -> list[dict]:
        """O que vem por aí: passos agendados (com ETA) e gatilhos de HP ainda não cruzados (com distância)."""
        lista = []
        for s in self.ativas:
            for i in range(s.proximo, len(s.passos)):
                eta = s.hora(i) - t
                if eta <= horizonte:
                    p = s.passos[i]
                    lista.append({"texto": p["texto"], "tipo": p.get("tipo", "atencao"), "eta": eta, "id": s.mec.get("id", "")})
        for i, m in enumerate(self.boss["mecanicas"]):
            alvo = pct_gatilho(m, self.usar_observado)
            if alvo is not None and i not in self.disparadas and passos_de(m) and self._ativa(m):
                lista.append({"texto": passos_de(m)[0]["texto"], "tipo": m.get("acao_tipo", "atencao"),
                              "hp": alvo, "falta": max(0.0, self.ultimo_hp - alvo), "id": m.get("id", "")})
        return sorted(lista, key=lambda x: x.get("eta", 1e9) if "eta" in x else 1e6 + x["falta"])

    def status_ativos(self, t: float) -> list[dict]:
        """Status valendo no instante t, com os segundos restantes. Os do boss vêm antes dos de jogadores."""
        self.status = [s for s in self.status if s.fim > t]
        lista = [{"texto": s.texto, "tipo": s.tipo, "em": s.em, "alvo": s.alvo, "restante": s.fim - t,
                  "total": s.ate - s.de, "id": s.mec_id}
                 for s in self.status if s.inicio <= t]
        return sorted(lista, key=lambda x: (x["em"] != "boss", x["restante"]))

    # ---------- interno ----------
    def _disparar(self, i: int, m: dict, t: float, alvo: int | None = None, criada: float | None = None,
                  precursora: bool = False) -> None:
        self.disparadas[i] = t
        from .classes import ALCANCE
        passos = passos_completos(m, self.burst, self.papel, ALCANCE.get(self.classe or ""), self.classe)
        seq = Sequencia(m, t, passos, criada=t if criada is None else criada, precursora=precursora,
                        criada_por_precursora=precursora)
        if passos:
            self.ativas.append(seq)
        for st in m.get("status", []):
            em = st.get("em", "boss")
            quem = alvo if em == "alvo" else None
            # o mesmo status no mesmo alvo é renovado, não duplicado
            self.status = [s for s in self.status if not (s.mec_id == m.get("id", "") and s.texto == st["texto"] and s.alvo == quem)]
            self.status.append(Status(m.get("id", ""), st["texto"], st.get("tipo", m.get("acao_tipo", "atencao")), em, quem, seq,
                                      float(st.get("de", 0)), float(st.get("ate", DURACAO_PADRAO))))

    def _alerta(self, s: Sequencia, i: int) -> Alerta:
        p, m = s.passos[i], s.mec
        tipo = p.get("tipo", m.get("acao_tipo", "atencao"))
        wipe = m.get("wipe", False)
        if p.get("burst"):
            wipe = False
        ant = self._antecedencia(s, i)
        contagem = (p["contagem"] + ant) if p.get("contagem") else (round(ant, 2) if ant >= 1.0 else None)
        return Alerta(s.hora(i) - ant, "ativo", self.nome, m["nome"], p["texto"], p.get("sub", ""), tipo, contagem,
                      wipe, i, nivel_de(tipo, wipe), p.get("voz") or (m.get("voz") if i == 0 else None),
                      bool(p.get("contagem_voz")), m.get("id", ""), self._dica(m, p, tipo),
                      p.get("voz_curta") or m.get("voz_curta", ""))

    def _dica(self, m: dict, p: dict, tipo: str) -> str:
        """Dica da classe: a da mecânica (ou do passo) vence a genérica por tipo de ação."""
        if not self.classe:
            return ""
        chave = p.get("dica_tipo") or m.get("dica_tipo") or tipo
        tabela = self.dicas.get(self.classe, {})
        pessoal = (m.get("gatilho") or {}).get("pessoal")      # o alerta é sobre você: "sair_pessoal" vence "sair"
        return ((p.get("dicas") or {}).get(self.classe) or (m.get("dicas") or {}).get(self.classe)
                or (pessoal and tabela.get(chave + "_pessoal")) or tabela.get(chave, ""))


class DetectorBoss:
    """Escolhe, numa captura, qual entidade é o boss da luta atual.

    Enquanto o spawn (0x3641) não está decodificado, não temos o código do mob.
    Regra: boss é a entidade com o maior HP visto entre as que levam dano de
    jogadores. Cada boss novo recebe o próximo nome da lista (ordem da masmorra
    ou --bosses).
    """

    def __init__(self, nomes: list[str], hp_minimo: int = 1_000_000) -> None:
        self.nomes = list(nomes)
        self.hp_minimo = hp_minimo
        self.max_hp: dict[int, int] = {}
        self.dano: dict[int, int] = {}
        self.atribuidos: dict[int, str] = {}

    def hp(self, entidade: int, valor: int) -> None:
        self.max_hp[entidade] = max(self.max_hp.get(entidade, 0), valor)

    def dano_recebido(self, entidade: int, valor: int) -> None:
        self.dano[entidade] = self.dano.get(entidade, 0) + valor

    def nome_de(self, entidade: int) -> str | None:
        """Nome do boss se a entidade parece ser um boss; atribui o próximo nome na primeira vez."""
        if entidade in self.atribuidos:
            return self.atribuidos[entidade]
        if self.max_hp.get(entidade, 0) < self.hp_minimo or entidade not in self.dano:
            return None
        if len(self.atribuidos) >= len(self.nomes):
            return None
        nome = self.nomes[len(self.atribuidos)]
        self.atribuidos[entidade] = nome
        return nome

    def pct(self, entidade: int, valor: int) -> float:
        m = self.max_hp.get(entidade) or 1
        return 100.0 * valor / m
