"""Leitura de arquivos .pcap e .pcapng e extração dos segmentos TCP.

Sem dependências externas. Suporta Ethernet (com VLAN), loopback do Npcap
(linktype NULL), IP cru, Linux SLL e SLL2, sobre IPv4 e IPv6.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass
from typing import Iterator

FIN, SYN, RST = 0x01, 0x02, 0x04


@dataclass(slots=True)
class SegmentoTCP:
    ts: float
    origem: str
    porta_origem: int
    destino: str
    porta_destino: int
    seq: int
    flags: int
    dados: bytes

    @property
    def fluxo(self) -> tuple[str, int, str, int]:
        return (self.origem, self.porta_origem, self.destino, self.porta_destino)


def ler_segmentos(caminho: str) -> Iterator[SegmentoTCP]:
    with open(caminho, "rb") as f:
        dados = f.read()
    magic = dados[:4]
    if magic == b"\x0a\x0d\x0d\x0a":
        pacotes = _pcapng(dados)
    elif magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
        pacotes = _pcap(dados)
    else:
        raise ValueError("formato não reconhecido: esperado .pcap ou .pcapng")
    for ts, linktype, quadro in pacotes:
        seg = _decodificar(linktype, quadro, ts)
        if seg is not None:
            yield seg


def _pcap(d: bytes) -> Iterator[tuple[float, int, bytes]]:
    magic = d[:4]
    e = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
    nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    linktype = struct.unpack_from(e + "I", d, 20)[0] & 0xFFFF
    o = 24
    while o + 16 <= len(d):
        seg, frac, incl, _ = struct.unpack_from(e + "IIII", d, o)
        o += 16
        yield seg + frac / (1e9 if nano else 1e6), linktype, d[o:o + incl]
        o += incl


def _pcapng(d: bytes) -> Iterator[tuple[float, int, bytes]]:
    o, e = 0, "<"
    interfaces: list[tuple[int, float]] = []
    ultimo_ts = 0.0
    while o + 12 <= len(d):
        tipo_bruto = d[o:o + 4]
        if tipo_bruto == b"\x0a\x0d\x0d\x0a":
            e = "<" if d[o + 8:o + 12] == b"\x4d\x3c\x2b\x1a" else ">"
            interfaces = []
        tipo, tam = struct.unpack_from(e + "II", d, o)
        if tam < 12 or o + tam > len(d):
            break
        corpo = d[o + 8:o + tam - 4]
        if tipo == 1:  # Interface Description Block
            linktype = struct.unpack_from(e + "H", corpo, 0)[0]
            interfaces.append((linktype, _resolucao_ts(corpo[8:], e)))
        elif tipo == 6:  # Enhanced Packet Block
            iface, alto, baixo, cap = struct.unpack_from(e + "IIII", corpo, 0)
            linktype, res = interfaces[iface] if iface < len(interfaces) else (1, 1e-6)
            ultimo_ts = ((alto << 32) | baixo) * res
            yield ultimo_ts, linktype, corpo[20:20 + cap]
        elif tipo == 3:  # Simple Packet Block
            orig = struct.unpack_from(e + "I", corpo, 0)[0]
            linktype = interfaces[0][0] if interfaces else 1
            yield ultimo_ts, linktype, corpo[4:4 + min(orig, len(corpo) - 4)]
        o += tam


def _resolucao_ts(opcoes: bytes, e: str) -> float:
    o = 0
    while o + 4 <= len(opcoes):
        codigo, tam = struct.unpack_from(e + "HH", opcoes, o)
        if codigo == 0:
            break
        if codigo == 9 and tam >= 1:
            v = opcoes[o + 4]
            return 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
        o += 4 + ((tam + 3) & ~3)
    return 1e-6


def _decodificar(linktype: int, q: bytes, ts: float) -> SegmentoTCP | None:
    if linktype == 1:  # Ethernet
        if len(q) < 14:
            return None
        o, et = 14, struct.unpack_from(">H", q, 12)[0]
        while et in (0x8100, 0x88A8) and len(q) >= o + 4:
            et = struct.unpack_from(">H", q, o + 2)[0]
            o += 4
    elif linktype == 0:  # NULL / loopback do Npcap
        if len(q) < 4:
            return None
        familia = struct.unpack_from("<I", q, 0)[0]
        o, et = 4, 0x0800 if familia == 2 else 0x86DD
    elif linktype in (12, 101):  # IP cru
        o = 0
        et = 0x0800 if q and q[0] >> 4 == 4 else 0x86DD
    elif linktype == 113:  # Linux SLL
        o, et = 16, struct.unpack_from(">H", q, 14)[0] if len(q) >= 16 else 0
    elif linktype == 276:  # Linux SLL2
        o, et = 20, struct.unpack_from(">H", q, 0)[0] if len(q) >= 20 else 0
    else:
        return None

    if et == 0x0800:
        if len(q) < o + 20 or q[o] >> 4 != 4:
            return None
        ihl = (q[o] & 0x0F) * 4
        total = struct.unpack_from(">H", q, o + 2)[0]
        frag = struct.unpack_from(">H", q, o + 6)[0]
        if q[o + 9] != 6 or frag & 0x3FFF:
            return None  # não é TCP, ou é fragmento IP
        origem = str(ipaddress.IPv4Address(q[o + 12:o + 16]))
        destino = str(ipaddress.IPv4Address(q[o + 16:o + 20]))
        t, fim = o + ihl, min(len(q), o + total)
    elif et == 0x86DD:
        if len(q) < o + 40 or q[o + 6] != 6:
            return None
        plen = struct.unpack_from(">H", q, o + 4)[0]
        origem = str(ipaddress.IPv6Address(q[o + 8:o + 24]))
        destino = str(ipaddress.IPv6Address(q[o + 24:o + 40]))
        t, fim = o + 40, min(len(q), o + 40 + plen)
    else:
        return None

    if fim < t + 20:
        return None
    sp, dp, seq, _, off, flags = struct.unpack_from(">HHIIBB", q, t)
    inicio = t + (off >> 4) * 4
    return SegmentoTCP(ts, origem, sp, destino, dp, seq, flags, bytes(q[inicio:fim]))


_M = 0xFFFFFFFF


def _dif(a: int, b: int) -> int:
    d = (a - b) & _M
    return d - 0x100000000 if d >= 0x80000000 else d


class Remontador:
    """Remonta um sentido de uma conexão TCP em ordem de sequência.

    push() devolve pedaços (dados, buraco). buraco=True avisa que bytes se
    perderam antes desse pedaço e quem consome precisa ressincronizar.
    """

    MAX_PENDENTE = 4 * 1024 * 1024
    # Na captura (sobretudo no loopback do ExitLag), um segmento que o Npcap perdeu não volta nunca:
    # esperar por ele travava o parser. Na run de 2026-10-16 17:11 foram ~45 s cegos no pull do Auldor.
    MAX_ESPERA = 1.0          # s (relógio dos pacotes) esperando um buraco antes de pular

    def __init__(self) -> None:
        self.proximo: int | None = None
        self.pendentes: dict[int, bytes] = {}
        self.bytes_pendentes = 0
        self.buracos = 0
        self.retransmissoes = 0
        self.esperando_desde: float | None = None

    def push(self, seq: int, dados: bytes, syn: bool = False, ts: float | None = None) -> list[tuple[bytes, bool]]:
        if syn:
            self.proximo = (seq + 1) & _M
            self.pendentes.clear()
            self.bytes_pendentes = 0
            return []
        if not dados:
            return []
        if self.proximo is None:
            self.proximo = seq
        d = _dif(seq, self.proximo)
        if d < 0:
            if d + len(dados) <= 0:
                self.retransmissoes += 1
                return []
            dados, d = dados[-d:], 0
        if d > 0:
            antigo = self.pendentes.get(seq)
            if antigo is None or len(dados) > len(antigo):
                self.bytes_pendentes += len(dados) - (len(antigo) if antigo else 0)
                self.pendentes[seq] = dados
            if self.esperando_desde is None:
                self.esperando_desde = ts
            if self.bytes_pendentes > self.MAX_PENDENTE or (
                    ts is not None and self.esperando_desde is not None and ts - self.esperando_desde > self.MAX_ESPERA):
                return self._pular_buraco()
            return []
        saida = [(dados, False)]
        self.proximo = (self.proximo + len(dados)) & _M
        saida.extend(self._drenar())
        if not self.pendentes:
            self.esperando_desde = None     # o buraco foi preenchido (retransmissão): espera zerada
        return saida

    def finalizar(self) -> list[tuple[bytes, bool]]:
        saida: list[tuple[bytes, bool]] = []
        while self.pendentes:
            saida.extend(self._pular_buraco())
        return saida

    def _drenar(self) -> list[tuple[bytes, bool]]:
        saida = []
        andou = True
        while self.pendentes and andou:
            andou = False
            for s in list(self.pendentes):
                d = _dif(s, self.proximo)
                if d <= 0:
                    dados = self.pendentes.pop(s)
                    self.bytes_pendentes -= len(dados)
                    if d + len(dados) > 0:
                        parte = dados[-d:] if d < 0 else dados
                        saida.append((parte, False))
                        self.proximo = (self.proximo + len(parte)) & _M
                    andou = True
        return saida

    def _pular_buraco(self) -> list[tuple[bytes, bool]]:
        menor = min(self.pendentes, key=lambda s: _dif(s, self.proximo))
        self.proximo = menor
        self.buracos += 1
        self.esperando_desde = None
        saida = self._drenar()
        if saida:
            saida[0] = (saida[0][0], True)
        return saida
