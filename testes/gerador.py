"""Gera capturas .pcapng sintéticas no formato do Aion 2, a partir da especificação.

Escrito separado dos decoders para que os testes conferam uma implementação
contra a outra. Não substitui a validação com tráfego real do jogo.
"""

from __future__ import annotations

import random
import struct


def varint(v: int) -> bytes:
    b = bytearray()
    while True:
        if v < 0x80:
            b.append(v)
            return bytes(b)
        b.append((v & 0x7F) | 0x80)
        v >>= 7


def msg(op: int, payload: bytes) -> bytes:
    return varint(len(payload) + 6) + struct.pack("<H", op) + payload


def lz4_comprimir(src: bytes) -> bytes:
    n, out, tabela = len(src), bytearray(), {}
    ancora, i = 0, 0

    def tam_extra(r: int) -> None:
        while r >= 255:
            out.append(255)
            r -= 255
        out.append(r)

    def emitir(fim_lit: int, desloc: int, ml: int) -> None:
        lit, mlc = fim_lit - ancora, ml - 4
        out.append((min(lit, 15) << 4) | (min(mlc, 15) if ml else 0))
        if lit >= 15:
            tam_extra(lit - 15)
        out.extend(src[ancora:fim_lit])
        if ml:
            out.extend(struct.pack("<H", desloc))
            if mlc >= 15:
                tam_extra(mlc - 15)

    while i < n - 12:
        chave = src[i:i + 4]
        c = tabela.get(chave)
        tabela[chave] = i
        if c is not None and i - c < 65536:
            ml = 4
            while i + ml < n - 5 and src[c + ml] == src[i + ml]:
                ml += 1
            emitir(i, i - c, ml)
            i += ml
            ancora = i
        else:
            i += 1
    emitir(n, 0, 0)
    return bytes(out)


def bloco(mensagens: list[bytes]) -> bytes:
    bruto = b"".join(mensagens)
    return msg(0xFFFF, struct.pack("<I", len(bruto)) + lz4_comprimir(bruto))


def dano(origem, alvo, skill, valor, *, critico=False, costas=False, frente=False, double=False,
         parry=False, cura=None, multi=None, extra01=False, extra08=False, proc=False, refletido=False) -> bytes:
    flags = 0x02
    if not proc:
        flags |= 0x04
    if extra01:
        flags |= 0x01
    if extra08:
        flags |= 0x08
    if multi:
        flags |= 0x20
    p = bytearray(varint(alvo) + struct.pack("<H", flags) + varint(origem) + struct.pack("<IB", skill, 7))
    if extra01:
        p += struct.pack("<I", 0xAABBCCDD)
    p.append(9 if refletido else 3 if critico else 1)
    bits = (parry << 1) | (double << 3) | ((cura is not None) << 5)
    p.append(bits)
    p += varint(cura or 0)
    p.append(1 if costas else 2 if frente else 0)
    p += struct.pack("<II", 111, 222) + varint(5) + varint(valor)
    if extra08:
        p += struct.pack("<I", 0)
    if multi:
        p += varint(len(multi)) + b"".join(varint(x) for x in multi)
    return msg(0x3804, bytes(p))


def dot(origem, alvo, skill, valor, mascara=0x0A) -> bytes:
    return msg(0x3805, varint(alvo) + bytes([mascara]) + varint(origem) + varint(3) + struct.pack("<I", skill) + varint(valor))


def hp(entidade, valor) -> bytes:
    return msg(0x8D00, varint(entidade) + varint(2) + varint(0) + varint(0) + struct.pack("<Q", valor))


def morte(entidade) -> bytes:
    return msg(0x3642, varint(entidade) + varint(0) + varint(1))


def horario(ms) -> bytes:
    return msg(0x3600, struct.pack("<q", ms))


def combat_power(cp, maximo) -> bytes:
    return msg(0x3656, struct.pack("<QQ", cp, maximo))


def inicio_skill(conj, skill, alvo, cooldown, *, cargas=None, posicao=False, alvos_extras=()) -> bytes:
    fa = (0x04 if cargas is not None else 0) | (0x20 if alvos_extras else 0)
    fb = 0x02 if posicao else 0
    p = bytearray(varint(conj) + bytes([fa]) + struct.pack("<IB", skill, 1) + bytes([fb]) + varint(alvo))
    p += struct.pack("<I", 0)
    if posicao:
        p += struct.pack("<fff", 1.0, 2.0, 3.0)
    p += varint(0) + b"\x00" + varint(cooldown)
    if cargas is not None:
        p.append(cargas)
    if alvos_extras:
        p += varint(len(alvos_extras))
        for a in alvos_extras:
            p += varint(a) + b"\x00" * 12
    return msg(0x3802, bytes(p))


def spawn(entidade, mob) -> bytes:
    """0x3641: varint entidade | u16 | u8 | u32 código do mob | resto."""
    return msg(0x3641, varint(entidade) + struct.pack("<HBI", 0, 0, mob) + bytes(8))


def eu(entidade, nome) -> bytes:
    """0x3633 OwnCharacterInfo: varint ID | u32 | u8 | u8 tamanho | nome."""
    n = nome.encode()
    return msg(0x3633, varint(entidade) + struct.pack("<IBB", 0, 0, len(n)) + n + bytes(4))


def preparo(conj, skill, alvo, flag=2) -> bytes:
    """0x3809 SkillPrepare: varint conjurador | u8 flag | u32 skill | 01 02 | varint alvo | posição."""
    return msg(0x3809, varint(conj) + struct.pack("<BI", flag, skill) + b"" + varint(alvo) + bytes(14))


def personagem(entidade, nome) -> bytes:
    """0x3645 CharacterInfo de outro jogador: varint ID | u8 | u8 | varint | u8 | u8 tamanho | nome | resto."""
    n = nome.encode()
    return msg(0x3645, varint(entidade) + bytes([0x0D, 0x30]) + varint(160) + bytes([0x07, len(n)]) + n + bytes(12))


def desconhecido(op=0x4242, tam=7) -> bytes:
    return msg(op, bytes(range(tam)))


# ---------- pcapng ----------

def _bloco_pcapng(tipo: int, corpo: bytes) -> bytes:
    corpo += b"\x00" * ((4 - len(corpo) % 4) % 4)
    tam = len(corpo) + 12
    return struct.pack("<II", tipo, tam) + corpo + struct.pack("<I", tam)


def _quadro(src_ip, dst_ip, sp, dp, seq, flags, dados) -> bytes:
    tcp = struct.pack(">HHIIBBHHH", sp, dp, seq & 0xFFFFFFFF, 0, 5 << 4, flags, 65535, 0, 0) + dados
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 0, 0x4000, 64, 6, 0,
                     bytes(map(int, src_ip.split("."))), bytes(map(int, dst_ip.split("."))))
    return b"\x00\x11\x22\x33\x44\x55" + b"\x66\x77\x88\x99\xaa\xbb" + b"\x08\x00" + ip + tcp


class EscritorPcapng:
    def __init__(self) -> None:
        self.partes = [
            _bloco_pcapng(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1)),
            _bloco_pcapng(1, struct.pack("<HHI", 1, 0, 65535)),
        ]

    def pacote(self, ts: float, src_ip, dst_ip, sp, dp, seq, flags, dados=b"") -> None:
        q = _quadro(src_ip, dst_ip, sp, dp, seq, flags, dados)
        us = int(ts * 1e6)
        self.partes.append(_bloco_pcapng(6, struct.pack("<IIIII", 0, us >> 32, us & 0xFFFFFFFF, len(q), len(q)) + q))

    def salvar(self, caminho: str) -> None:
        with open(caminho, "wb") as f:
            f.write(b"".join(self.partes))


def enviar_fluxo(w: EscritorPcapng, rng: random.Random, fluxo, stream: bytes, ts0: float, *, syn=True,
                 isn=1000, embaralhar=0.0, duplicar=0.0, perder: set[int] = frozenset(), seg_min=40, seg_max=900) -> list[int]:
    """Picota o stream em segmentos TCP e grava. Devolve os tamanhos dos segmentos."""
    src, sp, dst, dp = fluxo
    seq = isn
    if syn:
        w.pacote(ts0, src, dst, sp, dp, seq, 0x02)
        seq += 1
    segs, o = [], 0
    while o < len(stream):
        n = rng.randint(seg_min, seg_max)
        segs.append((seq + o, stream[o:o + n]))
        o += n
    ordem = list(range(len(segs)))
    for i in range(len(ordem) - 1):
        if rng.random() < embaralhar:
            ordem[i], ordem[i + 1] = ordem[i + 1], ordem[i]
    ts = ts0
    for k in ordem:
        if k in perder:
            continue
        ts += 0.01
        s, d = segs[k]
        w.pacote(ts, src, dst, sp, dp, s, 0x18, d)
        if rng.random() < duplicar:
            w.pacote(ts + 0.001, src, dst, sp, dp, s, 0x18, d)
    return [len(d) for _, d in segs]
