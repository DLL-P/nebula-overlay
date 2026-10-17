"""Decoders dos payloads (layouts em docs/PROTOCOLO.md).

Cada decoder recebe o payload e devolve um dict. Levanta Descartada quando a
mensagem não entra na conta (proc sem dano, reflexo, cura), e
ErroDecodificacao quando o payload não bate com o layout.
"""

from __future__ import annotations

import struct


class Descartada(Exception):
    pass


class ErroDecodificacao(Exception):
    pass


class Leitor:
    def __init__(self, b: bytes) -> None:
        self.b, self.o = b, 0
        self.bits_byte, self.bits_usados = 0, 8

    def _tem(self, n: int) -> None:
        if self.o + n > len(self.b):
            raise ErroDecodificacao(f"payload truncado ({len(self.b)} bytes)")

    def u8(self) -> int:
        self._tem(1)
        v = self.b[self.o]
        self.o += 1
        return v

    def u16(self) -> int:
        self._tem(2)
        v = struct.unpack_from("<H", self.b, self.o)[0]
        self.o += 2
        return v

    def u32(self) -> int:
        self._tem(4)
        v = struct.unpack_from("<I", self.b, self.o)[0]
        self.o += 4
        return v

    def u64(self) -> int:
        self._tem(8)
        v = struct.unpack_from("<Q", self.b, self.o)[0]
        self.o += 8
        return v

    def i64(self) -> int:
        self._tem(8)
        v = struct.unpack_from("<q", self.b, self.o)[0]
        self.o += 8
        return v

    def pular(self, n: int) -> None:
        self._tem(n)
        self.o += n

    def varint(self, max_bytes: int = 10) -> int:
        v = 0
        for i in range(max_bytes):
            b = self.u8()
            v |= (b & 0x7F) << (7 * i)
            if not b & 0x80:
                return v
        raise ErroDecodificacao("varint longo demais")

    def bit(self) -> int:
        """Leitor de bits do archiveReader: carrega um byte e entrega do bit menos significativo em diante."""
        if self.bits_usados >= 8:
            self.bits_byte, self.bits_usados = self.u8(), 0
        v = (self.bits_byte >> self.bits_usados) & 1
        self.bits_usados += 1
        return v

    @property
    def restante(self) -> int:
        return len(self.b) - self.o


def dano_direto(p: bytes) -> dict:
    """0x3804 DamageDealt."""
    r = Leitor(p)
    f = {"alvo": r.varint(5)}
    flags = r.u16()
    f["flags"] = flags
    if not flags & 0x04:
        raise Descartada("sem o bit 0x04: proc/buff/efeito, não é acerto")
    f["origem"] = r.varint(5)
    f["skill"] = r.u32()
    f["action_uid"] = r.u8()
    if flags & 0x01:
        r.pular(4)
    tipo = r.u8()
    f["tipo_acerto"] = tipo
    if tipo == 9:
        raise Descartada("dano refletido")
    f["critico"] = tipo == 3
    f.update(parry=False, perfect=False, double=False, costas=False, frente=False, cura=0)
    if flags & 0x02:
        r.bit()
        f["parry"] = bool(r.bit())
        f["perfect"] = bool(r.bit())
        f["double"] = bool(r.bit())
        r.bit()
        tem_cura = r.bit()
        cura = r.varint()
        if tem_cura:
            f["cura"] = cura
        r.bit()
        direcao = r.u8()
        f["costas"], f["frente"] = direcao == 1, direcao == 2
    r.pular(4)
    r.pular(4)
    r.varint(5)
    f["dano"] = r.varint()
    f["hits"], f["multi_hit_dano"] = 1, 0
    if flags & 0x08:
        r.pular(4)
    if flags & 0x10:
        r.bit()
    if flags & 0x20:
        n = r.varint(5)
        soma = 0
        for _ in range(n):
            if r.restante <= 0:
                break
            soma += r.varint()
        if n:
            f["hits"], f["multi_hit_dano"] = n, soma
    return f


def dano_periodico(p: bytes) -> dict:
    """0x3805 DamageOverTime."""
    r = Leitor(p)
    f = {"alvo": r.varint(5)}
    mascara = r.u8()
    f["mascara"] = mascara
    if mascara != 0x0A:
        raise Descartada(f"máscara 0x{mascara:02X}: não é tick de dano")
    f["origem"] = r.varint(5)
    r.varint(5)
    f["skill"] = r.u32()
    f["dano"] = r.varint()
    return f


def hp_entidade(p: bytes) -> dict:
    """0x8D00 EntityHP."""
    if len(p) < 6:
        raise ErroDecodificacao(f"payload curto demais ({len(p)} bytes)")
    r = Leitor(p)
    f = {"entidade": r.varint(5)}
    tipo = r.varint(5)
    if tipo != 2:
        raise Descartada(f"não é type 2 (veio {tipo})")
    r.varint(5)
    r.varint(5)
    f["hp"] = r.u64()
    return f


def morte(p: bytes) -> dict:
    """0x3642 Death."""
    r = Leitor(p)
    f = {"entidade": r.varint(5)}
    r.varint(5)
    f["flag_morte"] = r.varint(5)
    return f


def combat_power(p: bytes) -> dict:
    """0x3656 CombatPowerUpdate: exatamente 16 bytes."""
    if len(p) != 16:
        raise ErroDecodificacao(f"payload tem {len(p)} bytes, não 16")
    cp, maximo = struct.unpack("<QQ", p)
    return {"combat_power": cp, "combat_power_maximo": maximo}


def horario_servidor(p: bytes) -> dict:
    """0x3600 ServerTimestamp: exatamente 8 bytes."""
    if len(p) != 8:
        raise ErroDecodificacao(f"{len(p)} bytes, esperado 8")
    return {"horario_servidor": struct.unpack("<q", p)[0]}


def heartbeat(p: bytes) -> dict:
    """0x3603 Heartbeat. Layout provável: i32 em ms no offset 2."""
    if len(p) < 10:
        raise ErroDecodificacao(f"payload curto demais ({len(p)} < 10)")
    return {"ms": struct.unpack_from("<i", p, 2)[0]}


def inicio_skill(p: bytes) -> dict:
    """0x3802 SkillStart."""
    r = Leitor(p)
    f = {"conjurador": r.varint(5)}
    flags_a = r.u8()
    f["skill"] = r.u32()
    f["action_uid"] = r.u8()
    if flags_a & 0x01:
        r.pular(1)
    flags_b = r.u8()
    f["alvo"] = r.varint(5)
    if flags_b & 0x01:
        r.pular(4)
    r.pular(4)
    if flags_b & 0x02:
        r.pular(12)  # provavelmente a posição do alvo (vec3)
    r.varint(5)
    r.pular(1)
    if flags_a & 0x02:
        r.varint(5)
    f["cooldown_ms"] = r.varint(5)
    f["tem_cargas"] = bool(flags_a & 0x0C)
    f["cargas"] = r.u8() if flags_a & 0x04 else 0
    f["recarga_ms"] = r.varint(5) if flags_a & 0x08 else 0
    if flags_a & 0x10:
        r.bit()
    if flags_a & 0x20:
        n = r.varint(5)
        alvos = []
        for _ in range(n):
            alvos.append(r.varint(5))
            r.pular(12)
        f["alvos_extras"] = alvos
    if r.restante:
        raise ErroDecodificacao(f"sobraram {r.restante} bytes")
    f["flags_a"], f["flags_b"] = flags_a, flags_b
    return f


# opcode -> (nome curto, função)
def preparo_skill(p: bytes) -> dict:
    """0x3809 (nome nosso: SkillPrepare). Mapeado nas capturas de 2026-10-16, não vem do meter.

    O boss avisa que vai usar a skill um tempo fixo antes do 0x3802 (1,0 s no círculo do Raur,
    3,0 s na zona dele, 1,5 s no círculo do Urahum...), sempre igual para a mesma skill.
    Layout: varint conjurador | u8 flag | u32 skill | u8 1 | u8 2 | varint alvo | posição...
    62 de 64 preparos de boss na run das 11:21 vieram seguidos do cast da mesma skill.
    """
    r = Leitor(p)
    f = {"conjurador": r.varint(5), "flag": r.u8(), "skill": r.u32(), "alvo": None}
    if r.restante >= 3 and r.u8() == 1 and r.u8() == 2:
        f["alvo"] = r.varint(5)
    return f


ODYLE = 60000001       # ticket da energia Odyle


def _ticket(r: Leitor) -> dict:
    """ContentsTicketInfo: u8 flags | u32 ticket | [1: 8 bytes] | [2: 8 bytes] | [4: varint restante] | [8: varint recarga]."""
    fl = r.u8()
    t = {"ticket": r.u32(), "restante": 0, "recarga": 0}
    if fl & 1:
        r.pular(8)
    if fl & 2:
        r.pular(8)
    if fl & 4:
        t["restante"] = r.varint(5)
    if fl & 8:
        t["recarga"] = r.varint(5)
    return t


def tickets(p: bytes) -> dict:
    """0x610B ContentsTickets: varint quantidade | tickets. A Odyle é o ticket 60000001."""
    r = Leitor(p)
    n = r.varint(5)
    if n > 512:
        raise ErroDecodificacao(f"{n} tickets")
    return {"tickets": [_ticket(r) for _ in range(n)]}


def ticket_atualizado(p: bytes) -> dict:
    """0x610C ContentsTicketUpdate: u8 flags | ticket | u8 motivo | [flags 1: u32]."""
    r = Leitor(p)
    r.u8()
    return {"tickets": [_ticket(r)]}


DECODERS = {
    0x3804: ("dano", dano_direto),
    0x3805: ("dot", dano_periodico),
    0x8D00: ("hp", hp_entidade),
    0x3642: ("morte", morte),
    0x3656: ("combat_power", combat_power),
    0x3600: ("horario", horario_servidor),
    0x3603: ("heartbeat", heartbeat),
    0x3802: ("inicio_skill", inicio_skill),
    0x3809: ("preparo", preparo_skill),
    0x610B: ("tickets", tickets),
    0x610C: ("ticket", ticket_atualizado),
}
