"""Testes dos avisos de controle em você (a2parse/controle.py e a ligação na Sessao)."""

from __future__ import annotations

import os
import struct
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import gerador as g  # noqa: E402
from a2parse import controle as cc, idioma  # noqa: E402
from a2parse.alertas import carregar_dicas, carregar_mecanicas  # noqa: E402
from a2parse.aovivo import Sessao  # noqa: E402
from a2parse.captura import SegmentoTCP  # noqa: E402

DADOS = carregar_mecanicas()
EU, BOSS, OUTRO = 7606, 18114, 47698

# payloads reais da captura de 2026-10-17 00:29 (Pinopi, solo, Gladiador)
ANEL_PINOPI = bytes.fromhex("b63b0113554353ba00d0070000000000005002e947a1010000c28d01018887180000501eb5c2b265144500009042")
REMOCAO = bytes.fromhex("b63b01005501")
REMOCAO_DUPLA = bytes.fromhex("b63b02005001004d01")
MOVIMENTO = bytes.fromhex("b63bc28d019f404707826d99425e04204500009042040101")


def efeito(alvo, inst, ef, dur_ms, origem, skill=None) -> bytes:
    """0x382A montado pela especificação (docs/PROTOCOLO.md), separado do leitor."""
    p = g.varint(alvo) + bytes([1, 0x13 if skill else 0x11]) + g.varint(inst) + struct.pack("<IqQ", ef, dur_ms, 0)
    p += g.varint(origem) + b"\x01" + (struct.pack("<I", skill) if skill else b"") + b"\x00" + b"\x00" * 12
    return g.msg(0x382A, p)


def remocao(alvo, *insts) -> bytes:
    return g.msg(0x382C, g.varint(alvo) + bytes([len(insts)]) + b"".join(b"\x00" + g.varint(i) + b"\x13" for i in insts))


def movimento(alvo, origem, ef) -> bytes:
    return g.msg(0x3816, g.varint(alvo) + g.varint(origem) + struct.pack("<I", ef * 10 + 1) + b"\x00" * 12 + b"\x04\x01\x01")


class Fluxo:
    def __init__(self, sessao: Sessao) -> None:
        self.s, self.seq = sessao, 5000

    def enviar(self, ts: float, dados: bytes, syn: bool = False) -> None:
        self.s.segmento(SegmentoTCP(ts, "203.0.113.5", 2106, "192.168.1.10", 51000, self.seq, 0x02 if syn else 0x18, dados))
        self.seq += len(dados) + (1 if syn else 0)


class TestLeitores(unittest.TestCase):
    def test_efeito_real_do_pinopi(self):
        f = cc.ler_efeito(ANEL_PINOPI)
        self.assertEqual((f["alvo"], f["inst"], f["efeito"], f["duracao_ms"], f["origem"], f["skill"]),
                         (EU, 85, 12211011, 2000, BOSS, 1607560))

    def test_efeito_sem_skill_e_sem_fim(self):
        p = efeito(EU, 300, 19000000, -1, EU)[3:]
        f = cc.ler_efeito(p)
        self.assertEqual((f["inst"], f["duracao_ms"], f["skill"]), (300, None, None))
        self.assertIsNone(cc.ler_efeito(p[:10]))

    def test_remocao_e_movimento_reais(self):
        self.assertEqual(cc.ler_remocao(REMOCAO), (EU, [85]))
        self.assertEqual(cc.ler_remocao(REMOCAO_DUPLA), (EU, [80, 77]))
        self.assertEqual(cc.ler_movimento(MOVIMENTO), (EU, BOSS, 12211011))


class TestClassificacao(unittest.TestCase):
    def test_tabela_do_programa(self):
        tabela = cc.carregar_tabela()
        self.assertEqual(tabela[100000321], "derrubada")
        self.assertEqual(tabela[100000311], "atordoamento")
        self.assertTrue(set(tabela.values()) <= set(cc.TIPOS))

    def test_pelo_nome_da_skill(self):
        av = cc.AvisosControle(tabela={}, nomes={1234560: "Golpe Atordoante", 7654320: "Flecha de Grilhão"})
        f = {"alvo": EU, "origem": OUTRO, "inst": 1, "efeito": 12345601, "duracao_ms": 2000, "skill": 1234560}
        self.assertEqual(av.efeito(0.0, f, EU).tipo, "atordoamento")
        self.assertEqual(av.efeito(0.0, dict(f, inst=2, efeito=76543201, skill=7654320), EU).tipo, "enraizamento")
        self.assertIsNone(av.efeito(0.0, dict(f, inst=3, efeito=11111101, skill=1111110), EU))
        self.assertEqual(cc.tipo_pelo_nome("Ressonância"), None)          # "sono" só como palavra

    def test_textos_em_todos_os_idiomas(self):
        try:
            for cod in ("pt", "en", "es"):
                idioma.definir(cod)
                for tipo in cc.TIPOS:
                    self.assertNotEqual(idioma.t("cc_" + tipo), "cc_" + tipo, f"{cod}: {tipo}")
        finally:
            idioma.definir("pt")

    def test_toda_classe_tem_dica_de_controle(self):
        self.assertTrue(all(d.get("controle") for d in carregar_dicas().values()))


class TestSessao(unittest.TestCase):
    def nova(self, ligado=True) -> tuple[Sessao, Fluxo]:
        s = Sessao(DADOS, classe_fixa="GLADIATOR", controle=ligado)
        f = Fluxo(s)
        f.enviar(0.0, b"", syn=True)
        f.enviar(0.1, g.horario(1) + g.eu(EU, "Heroi"))
        return s, f

    def cartoes(self, s: Sessao, agora: float) -> list:
        return [a for a in s.estado(agora)["cartoes"] if a.mecanica == "controle"]

    def test_desligado_por_padrao(self):
        self.assertFalse(Sessao(DADOS).controle)
        s, f = self.nova(ligado=False)
        f.enviar(1.0, efeito(EU, 10, 100000311, 3000, OUTRO, 18060130))
        self.assertEqual(self.cartoes(s, 1.1), [])

    def test_atordoado_com_contagem_e_dica(self):
        s, f = self.nova()
        f.enviar(1.0, efeito(EU, 10, 100000311, 3000, OUTRO, 18060130))
        c = self.cartoes(s, 1.5)
        self.assertEqual([(a.texto, a.contagem, a.tipo) for a in c], [("ATORDOADO", 3.0, "controle")])
        self.assertEqual(c[0].dica, "Remoção de Impacto quebra o controle")
        self.assertEqual(self.cartoes(s, 4.1), [])

    def test_some_quando_o_controle_e_quebrado(self):
        s, f = self.nova()
        f.enviar(1.0, efeito(EU, 10, 100000321, 3000, OUTRO, 11290007))
        f.enviar(1.8, remocao(EU, 10))
        self.assertEqual(self.cartoes(s, 1.9), [])

    def test_derrubada_pelo_movimento_forcado(self):
        s, f = self.nova()
        f.enviar(1.0, efeito(EU, 11, 99999901, 2000, BOSS, 1607999))
        self.assertEqual(self.cartoes(s, 1.02), [])                 # sem tipo: espera o 0x3816
        f.enviar(1.05, movimento(EU, BOSS, 99999901))
        self.assertEqual([(a.texto, a.contagem) for a in self.cartoes(s, 1.1)], [("DERRUBADO", 2.0)])

    def test_o_novo_substitui_o_anterior(self):
        s, f = self.nova()
        f.enviar(1.0, efeito(EU, 12, 12211002, 900, BOSS, 1607620))
        f.enviar(1.5, efeito(EU, 13, 12211011, 2000, BOSS, 1607620))
        self.assertEqual([a.texto for a in self.cartoes(s, 1.6)], ["DERRUBADO"])

    def test_ignora_o_que_nao_e_controle_em_voce(self):
        s, f = self.nova()
        f.enviar(1.0, efeito(OUTRO, 20, 100000311, 3000, BOSS, 1607560))     # em outro jogador
        f.enviar(1.1, efeito(EU, 21, 100000311, 3000, EU, 18060130))         # aplicado por você
        f.enviar(1.2, efeito(EU, 22, 12211001, 100, BOSS, 1607620))          # solavanco de 0,1 s
        f.enviar(1.3, efeito(EU, 23, 181200101, 8000, OUTRO, 18120140))      # buff do Encantador
        f.enviar(1.4, efeito(EU, 24, 99999902, 2000, BOSS, 1607999))         # sem tipo e sem 0x3816
        f.enviar(2.5, movimento(EU, BOSS, 99999902))                         # chegou tarde demais
        self.assertEqual(self.cartoes(s, 2.6), [])

    def test_troca_de_zona_limpa(self):
        s, f = self.nova()
        f.enviar(1.0, efeito(EU, 30, 100000201, 3000, OUTRO, 11200030))
        self.assertEqual([a.texto for a in self.cartoes(s, 1.1)], ["PRESO NO LUGAR"])
        f.enviar(1.5, g.eu(9999, "Heroi"))
        self.assertEqual(s.avisos_controle.ativos, {})


if __name__ == "__main__":
    unittest.main()
