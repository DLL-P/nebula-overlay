"""Tempo de resposta do servidor, medido só olhando o tráfego que já passa pela captura (nada é enviado).

- Eco do próprio jogo (com e sem acelerador): a cada 10 s o cliente manda um pacote de 12 bytes (cifrado, mas o
  tamanho não muda) e o servidor responde com o heartbeat 0x3603. O tempo entre os dois é o ping até o servidor do
  jogo, passando pelo acelerador se houver. Nas capturas com ExitLag deu ~70 ms, estável. Vale a mediana dos
  últimos ECOS ecos.
- Entre um eco e outro, um lag repentino aparece pela oscilação: o servidor manda o horário dele (0x3600) a cada
  50 ms; chegada − horário = atraso de ida + diferença dos relógios. A diferença dos relógios quase não muda, então
  o quanto isso sobe acima do mínimo dos últimos JANELA_BASE s é atraso a mais. Passando de PICO ms, ele soma no
  número mostrado.
- Sem eco ainda (primeiros 10 s) e conexão direta: o tempo entre um segmento TCP do jogo e o ACK do servidor que o
  cobre (o menor dos últimos JANELA_PING s; retransmissão não conta, algoritmo de Karn). No loopback do acelerador
  quem confirma o TCP é o proxy local, então isso não vale lá.
- Mais de PARADO s sem o horário do servidor: mostra há quanto tempo não chega nada.
"""

from __future__ import annotations

import statistics
from collections import deque

from .captura import ACK, FIN, SYN, _dif

TAM_PING = 12           # bytes do pacote de eco do cliente (a cada 10 s)
ECOS = 3                # o ping é a mediana dos últimos ecos
VALIDADE_ECO = 35.0     # s: eco mais velho que isso não vale (o jogo parou de mandar)
JANELA_PING = 10.0      # s: sem eco, o ping TCP é o menor RTT nessa janela
JANELA_BASE = 30.0      # s: o menor atraso de ida nessa janela é a referência da oscilação
JANELA_OSC = 1.0        # s: a oscilação é a mediana do excesso nesse último segundo
PICO = 25               # ms de atraso a mais que já somam no ping mostrado
PARADO = 1.0            # s sem o horário do servidor (vem a cada 0,05 s): conexão parada
LIMITES = (80, 150)     # ms: até o 1º é bom, até o 2º é médio


def _loopback(ip: str) -> bool:
    return ip.startswith("127.") or ip == "::1"


class Latencia:
    def __init__(self) -> None:
        self.pendentes: dict[tuple, deque] = {}     # fluxo servidor → cliente: (fim do segmento do cliente, ts)
        self.maior_fim: dict[tuple, int] = {}
        self.ping_enviado: dict[tuple, float] = {}  # fluxo servidor → cliente: quando saiu o último pacote de eco
        self.ecos: deque = deque(maxlen=ECOS)       # (ts, s)
        self.rtts: deque = deque()                  # (ts, s): ping TCP
        self.atrasos: deque = deque()               # (ts, ms): chegada − horário do servidor
        self.base: deque = deque()                  # mínimos crescentes do atraso (janela deslizante)
        self.ultimo_relogio = 0.0
        self.proxy = False                          # o servidor é um endereço de loopback (acelerador)

    # ---------- entrada ----------
    def segmento(self, seg, fluxos: dict) -> None:
        """Todo segmento da captura. `fluxos` é o Analise.fluxos: diz quais fluxos são do jogo."""
        f = fluxos.get(seg.fluxo)
        if f is not None and f.parece_jogo:          # servidor → cliente
            if seg.flags & ACK and seg.fluxo in self.pendentes:
                self._confirmado(seg.fluxo, seg.ack, seg.ts)
            return
        volta = (seg.destino, seg.porta_destino, seg.origem, seg.porta_origem)
        f = fluxos.get(volta)
        if f is None or not f.parece_jogo:
            return
        if len(seg.dados) == TAM_PING:
            self.ping_enviado[volta] = seg.ts
        if _loopback(seg.destino):                   # o servidor é o proxy local: o RTT do TCP não diz nada
            self.proxy = True
            return
        tam = len(seg.dados) + bool(seg.flags & SYN) + bool(seg.flags & FIN)
        if not tam:
            return
        fim = (seg.seq + tam) & 0xFFFFFFFF
        fila = self.pendentes.setdefault(volta, deque(maxlen=512))
        anterior = self.maior_fim.get(volta)
        if anterior is not None and _dif(fim, anterior) <= 0:
            fila.clear()                             # retransmissão: o próximo ACK seria ambíguo
            return
        self.maior_fim[volta] = fim
        fila.append((fim, seg.ts))

    def _confirmado(self, fluxo: tuple, ack: int, ts: float) -> None:
        fila, ultimo = self.pendentes[fluxo], None
        while fila and _dif(fila[0][0], ack) <= 0:
            ultimo = fila.popleft()
        if ultimo is not None and 0 <= ts - ultimo[1] < 5:
            self.rtts.append((ts, ts - ultimo[1]))
            while self.rtts and ts - self.rtts[0][0] > JANELA_PING:
                self.rtts.popleft()

    def heartbeat(self, ts: float, fluxo: tuple) -> None:
        """Cada 0x3603 (a resposta ao eco), no fluxo servidor → cliente."""
        enviado = self.ping_enviado.pop(fluxo, None)
        if enviado is not None and 0.005 < ts - enviado < 2.0:
            self.ecos.append((ts, ts - enviado))

    def relogio(self, ts: float, horario_servidor_ms: int) -> None:
        """Cada 0x3600: horário do servidor em ms desde 1970, `ts` é a chegada (s)."""
        atraso = ts * 1000.0 - horario_servidor_ms
        self.ultimo_relogio = ts
        self.atrasos.append((ts, atraso))
        while self.atrasos and ts - self.atrasos[0][0] > JANELA_OSC:
            self.atrasos.popleft()
        while self.base and self.base[-1][1] >= atraso:
            self.base.pop()
        self.base.append((ts, atraso))
        while ts - self.base[0][0] > JANELA_BASE:
            self.base.popleft()

    # ---------- saída ----------
    def oscilacao(self) -> float:
        """ms de atraso a mais agora (último segundo) que o melhor dos últimos 30 s."""
        if len(self.atrasos) < 5 or not self.base:
            return 0.0
        return max(0.0, statistics.median(a for _, a in self.atrasos) - self.base[0][1])

    def estado(self, agora: float) -> dict | None:
        """{"ms", "tipo": "ping"/"parado", "nivel": "bom"/"medio"/"ruim"} ou None (ainda sem medida)."""
        if self.ultimo_relogio and agora - self.ultimo_relogio > PARADO:
            if agora - self.ultimo_relogio > 30:     # jogo fechado ou captura parada: some
                return None
            return {"ms": int((agora - self.ultimo_relogio) * 1000), "tipo": "parado", "nivel": "ruim"}
        ecos = [r for t, r in self.ecos if agora - t <= VALIDADE_ECO]
        rtts = [r for t, r in self.rtts if agora - t <= JANELA_PING]
        if ecos:
            ms = statistics.median(ecos) * 1000
        elif len(rtts) >= 3 and not self.proxy:
            ms = min(rtts) * 1000
        else:
            return None
        osc = self.oscilacao()
        if osc > PICO:                               # lag agora, entre um eco e outro
            ms += osc
        return {"ms": max(0, round(ms)), "tipo": "ping",
                "nivel": "bom" if ms <= LIMITES[0] else "medio" if ms <= LIMITES[1] else "ruim"}
