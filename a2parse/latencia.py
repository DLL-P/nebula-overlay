"""Latência com o servidor, medida só olhando o tráfego que já passa pela captura (nada é enviado).

- Conexão direta: ping de verdade. É o tempo entre um segmento TCP que o jogo envia e o ACK do servidor que o
  cobre. Vale o menor dos últimos JANELA_PING s: o ACK pode sair atrasado (junto com o próximo pacote do
  servidor), mas nunca adiantado. Segmento retransmitido não conta (algoritmo de Karn).
- Com acelerador (ExitLag e parecidos), a captura fica no loopback: quem confirma o TCP é o proxy local (dá ~0 ms)
  e o sentido cliente → servidor é cifrado, sem eco para cronometrar. Fica a oscilação: o servidor manda o horário
  dele (0x3600) a cada 50 ms; chegada − horário = atraso de ida + diferença dos relógios. A diferença dos relógios
  quase não muda, então o quanto isso sobe acima do mínimo dos últimos JANELA_BASE s é o lag que se sente.
- Mais de PARADO s sem o horário do servidor: mostra há quanto tempo não chega nada.
"""

from __future__ import annotations

from collections import deque

from .captura import ACK, FIN, SYN, _dif

JANELA_PING = 10.0      # s: o ping é o menor RTT nessa janela
JANELA_BASE = 30.0      # s: o menor atraso de ida nessa janela é a referência da oscilação
JANELA_OSC = 1.0        # s: a oscilação é a mediana do excesso nesse último segundo
PARADO = 1.0            # s sem o horário do servidor (vem a cada 0,05 s): conexão parada
LIMITES = {"ping": (80, 150), "oscilacao": (15, 40)}     # ms: até o 1º é bom, até o 2º é médio


def _loopback(ip: str) -> bool:
    return ip.startswith("127.") or ip == "::1"


class Latencia:
    def __init__(self) -> None:
        self.pendentes: dict[tuple, deque] = {}     # fluxo servidor → cliente: (fim do segmento do cliente, ts)
        self.maior_fim: dict[tuple, int] = {}
        self.rtts: deque = deque()                  # (ts, s)
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
        if _loopback(seg.destino):                   # o servidor é o proxy local: o RTT não diz nada
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
    def estado(self, agora: float) -> dict | None:
        """{"ms", "tipo": "ping"/"oscilacao"/"parado", "nivel": "bom"/"medio"/"ruim"} ou None (ainda sem medida)."""
        if self.ultimo_relogio and agora - self.ultimo_relogio > PARADO:
            if agora - self.ultimo_relogio > 30:     # jogo fechado ou captura parada: some
                return None
            return {"ms": int((agora - self.ultimo_relogio) * 1000), "tipo": "parado", "nivel": "ruim"}
        rtts = [r for t, r in self.rtts if agora - t <= JANELA_PING]
        if len(rtts) >= 3 and not self.proxy:
            return self._nivel("ping", min(rtts) * 1000)
        if len(self.atrasos) >= 5 and self.base:
            excessos = sorted(a - self.base[0][1] for _, a in self.atrasos)
            return self._nivel("oscilacao", excessos[len(excessos) // 2])
        return None

    @staticmethod
    def _nivel(tipo: str, ms: float) -> dict:
        bom, medio = LIMITES[tipo]
        return {"ms": max(0, round(ms)), "tipo": tipo, "nivel": "bom" if ms <= bom else "medio" if ms <= medio else "ruim"}
