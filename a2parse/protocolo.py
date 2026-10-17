"""Formato de fio do Aion 2: varint, framer de mensagens, blocos 0xFFFF e LZ4.

Formato (detalhes em docs/PROTOCOLO.md):
  varint length (LEB128, até 5 bytes) | u16 opcode (LE) | payload de (length - 6) bytes
  0xFFFF: u32 tamanho descomprimido | bloco LZ4 cru -> mais mensagens, até 3 níveis
"""

from __future__ import annotations

import json
import os
import struct

BLOCO = 0xFFFF
ANCORA = 0x3600  # ServerTimestamp, payload de 8 bytes: começa com 0E 00 36
MAX_PAYLOAD = 1 << 20
MAX_PROFUNDIDADE = 3


def carregar_opcodes() -> dict[int, str]:
    from .caminhos import app
    caminho = app("opcodes.json")
    with open(caminho, encoding="utf-8") as f:
        return {int(k, 16): v for k, v in json.load(f).items()}


OPCODES = carregar_opcodes()


def ler_varint(buf, pos: int) -> tuple[int, int] | None:
    """Devolve (valor, bytes usados), None se faltam bytes, ou levanta ValueError se passar de 5 bytes."""
    valor = 0
    for i in range(5):
        if pos + i >= len(buf):
            return None
        b = buf[pos + i]
        valor |= (b & 0x7F) << (7 * i)
        if not b & 0x80:
            return valor, i + 1
    raise ValueError("varint com mais de 5 bytes")


def cabecalho(buf, pos: int):
    """Lê o cabeçalho em pos. Devolve (opcode, inicio_payload, tam_payload), None se incompleto, 'ruim' se inválido."""
    try:
        r = ler_varint(buf, pos)
    except ValueError:
        return "ruim"
    if r is None:
        return None
    length, n = r
    if length < 6 or length - 6 > MAX_PAYLOAD:
        return "ruim"
    if pos + n + 2 > len(buf):
        return None
    op = buf[pos + n] | (buf[pos + n + 1] << 8)
    return op, pos + n + 2, length - 6


class FramerFluxo:
    """Corta um fluxo TCP remontado em mensagens, com ressincronização.

    Sem sincronia, procura uma posição onde duas mensagens seguidas têm opcodes
    conhecidos, ou onde começa a âncora 0E 00 36.
    """

    LIMITE_BUSCA = 2 * 1024 * 1024  # desiste de fluxos que não parecem ser do jogo
    MAX_DESCONHECIDOS_SEGUIDOS = 8

    def __init__(self, conhecidos=None) -> None:
        self.conhecidos = set(conhecidos or OPCODES)
        self.buf = bytearray()
        self.sincronizado = False
        self.desistiu = False
        self.buscados = 0
        self.inicio_busca = 0
        self.espera: int | None = None
        self.dessincronizacoes = 0
        self.sincronizacoes = 0
        self.desconhecidos_seguidos = 0

    def alimentar(self, dados: bytes, buraco: bool = False) -> list[tuple[int, bytes]]:
        if self.desistiu:
            return []
        if buraco and self.sincronizado:
            self.buf.clear()
            self._perder()
        self.buf += dados
        return self._extrair()

    def _perder(self) -> None:
        self.sincronizado = False
        self.dessincronizacoes += 1
        self.inicio_busca = 0
        self.espera = None

    def _extrair(self) -> list[tuple[int, bytes]]:
        saida: list[tuple[int, bytes]] = []
        while True:
            if not self.sincronizado:
                p = self._procurar()
                if p is None:
                    return saida
                del self.buf[:p]
                self.sincronizado = True
                self.sincronizacoes += 1
                self.desconhecidos_seguidos = 0
            h = cabecalho(self.buf, 0)
            if h is None:
                return saida
            if h == "ruim":
                del self.buf[:1]
                self._perder()
                continue
            op, ini, tam = h
            if ini + tam > len(self.buf):
                return saida
            payload = bytes(self.buf[ini:ini + tam])
            del self.buf[:ini + tam]
            if op in self.conhecidos or op == BLOCO:
                self.desconhecidos_seguidos = 0
            else:
                self.desconhecidos_seguidos += 1
                if self.desconhecidos_seguidos > self.MAX_DESCONHECIDOS_SEGUIDOS:
                    self._perder()
                    continue
            saida.append((op, payload))

    CADEIA = 3  # mensagens conhecidas seguidas exigidas para sincronizar
    MAX_CANDIDATO = 64 * 1024   # na busca, mensagem solta maior que isso (fora bloco 0xFFFF) não é candidata

    def _cadeia(self, p: int):
        """True se há CADEIA mensagens conhecidas seguidas a partir de p, None se faltam bytes, False se não."""
        buf = self.buf
        for _ in range(self.CADEIA):
            h = cabecalho(buf, p)
            if h is None:
                return None
            if h == "ruim" or not (h[0] in self.conhecidos or h[0] == BLOCO):
                return False
            if h[0] != BLOCO and h[2] > self.MAX_CANDIDATO:
                return False        # tamanho absurdo lido no lixo: esperar por ele travava o parser
            p = h[1] + h[2]
            if p > len(buf):
                return None
        return True

    def _procurar(self) -> int | None:
        buf = self.buf
        # 1) o candidato que esperava mais bytes já se resolveu?
        if self.espera is not None:
            ok = self._cadeia(self.espera)
            if ok:
                p, self.espera = self.espera, None
                return p
            if ok is False:
                self.espera = None
        # 2) segue a varredura de onde parou: nunca revarre o que já viu (senão fica quadrático)
        p = self.inicio_busca
        fim = len(buf)
        while p < fim:
            if buf[p:p + 3] == b"\x0e\x00\x36" and p + 11 <= fim:
                self.espera = None
                return p  # âncora: ServerTimestamp de 8 bytes
            ok = self._cadeia(p)
            if ok:
                self.espera = None
                return p
            if ok is None:
                if fim - p <= 16:
                    break  # perto do fim pode faltar só o cabeçalho: revê no próximo pacote
                if self.espera is None:
                    # pode ser um começo válido, mas a busca continua: uma âncora ou cadeia completa
                    # adiante vence. Antes a busca parava aqui e esperava (na run de 2026-10-16 17:11,
                    # um tamanho de 239 KB lido no lixo deixou o parser ~45 s parado no pull do Auldor).
                    self.espera = p
            p += 1
        self.buscados += p - self.inicio_busca
        if self.buscados > self.LIMITE_BUSCA:
            self.desistiu = True
            self.buf.clear()
            return None
        # guarda só a cauda que ainda pode virar candidato (e o candidato em espera, se houver)
        guarda = min(p, self.espera) if self.espera is not None else p
        corte = max(0, guarda - 8)
        del buf[:corte]
        self.inicio_busca = p - corte
        if self.espera is not None:
            self.espera -= corte
        return None


def mensagens_do_bloco(payload: bytes) -> list[tuple[int, bytes]]:
    """Descomprime um 0xFFFF e corta as mensagens de dentro."""
    if len(payload) < 5:
        raise ValueError(f"bloco curto demais ({len(payload)} bytes)")
    tamanho = struct.unpack_from("<I", payload, 0)[0]
    if tamanho == 0 or tamanho > MAX_PAYLOAD:
        raise ValueError(f"tamanho descomprimido {tamanho} fora do limite")
    dados = lz4_descomprimir(payload[4:], tamanho)
    saida = []
    p = 0
    while p < len(dados):
        h = cabecalho(dados, p)
        if h is None or h == "ruim":
            break
        op, ini, tam = h
        if ini + tam > len(dados):
            break
        saida.append((op, dados[ini:ini + tam]))
        p = ini + tam
    return saida


def lz4_descomprimir(src: bytes, tamanho: int) -> bytes:
    """Descompressor do formato "block" do LZ4 (o mesmo que lz4block.UncompressBlock)."""
    dst = bytearray()
    s, n = 0, len(src)
    while s < n:
        token = src[s]
        s += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[s]
                s += 1
                lit += b
                if b != 255:
                    break
        if s + lit > n:
            raise ValueError("LZ4: literais além do bloco")
        dst += src[s:s + lit]
        s += lit
        if s >= n:
            break
        desloc = src[s] | (src[s + 1] << 8)
        s += 2
        if desloc == 0 or desloc > len(dst):
            raise ValueError("LZ4: deslocamento inválido")
        ml = token & 15
        if ml == 15:
            while True:
                b = src[s]
                s += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        inicio = len(dst) - desloc
        if desloc >= ml:
            dst += dst[inicio:inicio + ml]
        else:
            for k in range(ml):
                dst.append(dst[inicio + k])
        if len(dst) > tamanho:
            raise ValueError("LZ4: passou do tamanho declarado")
    if len(dst) != tamanho:
        raise ValueError(f"LZ4: {len(dst)} de {tamanho} bytes")
    return bytes(dst)
