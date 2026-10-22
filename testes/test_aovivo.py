"""Testes do processamento ao vivo (a2parse/aovivo.py), sem interface gráfica."""

from __future__ import annotations

import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import gerador as g  # noqa: E402
from a2parse.alertas import carregar_mecanicas  # noqa: E402
from a2parse.aovivo import Sessao, ler_eu, ler_nome, ler_spawn  # noqa: E402
from a2parse.captura import SegmentoTCP  # noqa: E402

DADOS = carregar_mecanicas()
AULDOR_NPC, BOSS, EU = 2300218, 27268, 9230


class Fluxo:
    """Entrega bytes ao Sessao como segmentos TCP de um servidor fictício."""

    def __init__(self, sessao: Sessao) -> None:
        self.s, self.seq = sessao, 5000

    def enviar(self, ts: float, dados: bytes, syn: bool = False) -> None:
        flags = 0x02 if syn else 0x18
        self.s.segmento(SegmentoTCP(ts, "203.0.113.5", 2106, "192.168.1.10", 51000, self.seq, flags, dados))
        self.seq += len(dados) + (1 if syn else 0)


class TestLeitores(unittest.TestCase):
    def test_spawn_e_eu(self):
        self.assertEqual(ler_spawn(g.spawn(BOSS, AULDOR_NPC)[3:]), (BOSS, AULDOR_NPC))
        self.assertEqual(ler_eu(g.eu(EU, "Heroi")[3:]), (EU, "Heroi"))

    def test_nome_de_outro_jogador(self):
        self.assertEqual(ler_nome(g.personagem(15935, "Fulano")[3:]), (15935, "Fulano"))
        self.assertEqual(ler_nome(g.personagem(976, "Nymuë")[3:]), (976, "Nymuë"))


class TestSessao(unittest.TestCase):
    def setUp(self):
        self.s = Sessao(DADOS)
        self.f = Fluxo(self.s)
        self.f.enviar(0.0, b"", syn=True)
        self.f.enviar(0.1, g.horario(1) + g.eu(EU, "Heroi") + g.spawn(BOSS, AULDOR_NPC) + g.hp(BOSS, 8_000_000))

    def test_identifica_voce_e_o_boss(self):
        st = self.s.estado(0.2)
        self.assertEqual(st["eu"], "Heroi")
        self.assertEqual(st["boss"].nome, "Divine Auldor")
        self.assertTrue(st["jogo"])

    def test_fase_do_ceu_com_mergulho_em_voce(self):
        self.f.enviar(10.0, g.hp(BOSS, 6_000_000) + g.inicio_skill(BOSS, 1601010, BOSS, 0))
        self.s.tick(18.1)
        st = self.s.estado(18.1)
        self.assertEqual([a.texto for a in st["cartoes"]][:1], ["EMPILHA NO CÍRCULO"])
        self.assertEqual(st["boss"].pct, 75.0)
        self.f.enviar(21.6, g.inicio_skill(BOSS, 1601030, EU, 0))
        textos = {a.texto for a in self.s.estado(21.7)["cartoes"]}
        self.assertEqual(textos, {"MERGULHO", "O MERGULHO É EM VOCÊ"})

    def test_troca_de_zona_atualiza_seu_id(self):
        self.f.enviar(5.0, g.eu(16160, "Heroi"))
        self.f.enviar(6.0, g.inicio_skill(BOSS, 1601030, 16160, 0))
        self.assertIn("O MERGULHO É EM VOCÊ", {a.texto for a in self.s.estado(6.1)["cartoes"]})

    def test_morte_tira_o_boss_da_tela(self):
        self.f.enviar(30.0, g.morte(BOSS))
        self.assertIsNone(self.s.estado(30.1)["boss"])

    def test_status_com_nome_do_alvo(self):
        self.f.enviar(1.0, g.personagem(15935, "Fulano"))
        self.f.enviar(2.0, g.inicio_skill(BOSS, 1601030, 15935, 0))
        st = self.s.estado(2.1)["status"]
        self.assertEqual([(s["texto"], s["nome"], s["voce"]) for s in st], [("MERGULHO", "Fulano", False)])
        self.f.enviar(5.0, g.inicio_skill(BOSS, 1601030, EU, 0))
        self.assertIn(("MERGULHO", "VOCÊ", True), [(s["texto"], s["nome"], s["voce"]) for s in self.s.estado(5.1)["status"]])

    def test_classe_pelo_pacote_e_pelos_casts(self):
        st = self.s.estado(0.2)
        self.assertEqual(st["classe"], "")                                    # o gerador manda classe 0
        for k in range(3):
            self.f.enviar(1.0 + k, g.dano(EU, BOSS, 17_010_000, 1000))      # skills de prefixo 17 = Clérigo
        self.assertEqual((self.s.estado(4.0)["classe"], self.s.estado(4.0)["papel"]), ("Clérigo", "healer"))

    def test_classe_e_papel_forcados(self):
        s = Sessao(DADOS, classe_fixa="TEMPLAR", papel_fixo="dps")
        self.assertEqual((s.estado(0)["classe"], s.estado(0)["papel"]), ("Templário", "dps"))

    def test_hibridas_assumem_o_papel_que_falta_no_grupo(self):
        """Gladiador sem Templário no grupo é o tank desde o pull; com Templário, é DPS. Chanter sem Clérigo cura."""
        def sessao(classe, outras):
            s = Sessao(DADOS, classe_fixa=classe)
            f = Fluxo(s)
            f.enviar(0.0, b"", syn=True)
            f.enviar(0.1, g.horario(1) + g.eu(EU, "Heroi") + g.spawn(BOSS, AULDOR_NPC) + g.hp(BOSS, 8_000_000))
            s.grupo = ["Heroi"] + [f"P{i}" for i in range(len(outras))]
            s.perfis = {f"P{i}": {"classe": c} for i, c in enumerate(outras)}
            return s, s.bosses[BOSS]
        s, b = sessao("GLADIATOR", ["RANGER", "CLERIC"])
        self.assertEqual(s.papel_no_boss(b, 1.0), "tank")
        s, b = sessao("GLADIATOR", ["TEMPLAR", "CLERIC"])
        self.assertEqual(s.papel_no_boss(b, 1.0), "dps")
        s, b = sessao("CHANTER", ["GLADIATOR", "RANGER"])
        self.assertEqual(s.papel_no_boss(b, 1.0), "healer")
        s, b = sessao("CHANTER", ["CLERIC"])
        self.assertEqual(s.papel_no_boss(b, 1.0), "suporte")

    def test_tank_improvisado_quando_o_aggro_e_seu(self):
        s = Sessao(DADOS, classe_fixa="GLADIATOR")
        f = Fluxo(s)
        f.enviar(0.0, b"", syn=True)
        f.enviar(0.1, g.horario(1) + g.eu(EU, "Heroi") + g.spawn(BOSS, AULDOR_NPC) + g.hp(BOSS, 8_000_000))
        b = s.bosses[BOSS]
        self.assertEqual(s.papel_no_boss(b, 1.0), "dps")
        for k in range(3):                                   # o boss bate em você: o aggro é seu
            f.enviar(1.0 + k, g.inicio_skill(BOSS, 1600940, EU, 0))
        self.assertEqual(s.papel_no_boss(b, 3.5), "dps")     # sozinho (Nightmare): não há grupo para proteger
        s.grupo = ["Heroi", "Parceiro"]
        self.assertEqual(s.papel_no_boss(b, 3.5), "tank")
        f.enviar(4.0, g.inicio_skill(BOSS, 1600925, BOSS, 0))  # leque frontal: aviso só do tank
        self.assertIn("VIRA ELE PRA FORA", [a.texto for a in s.estado(4.1)["cartoes"]])
        for k in range(5):                                   # o aggro foi para outro jogador
            f.enviar(10.0 + k, g.inicio_skill(BOSS, 1600940, 4242, 0))
        self.assertEqual(s.papel_no_boss(b, 14.5), "dps")
        s.papel_fixo = "healer"                              # papel escolhido na engrenagem vale sempre
        for k in range(3):
            f.enviar(20.0 + k, g.inicio_skill(BOSS, 1600940, EU, 0))
        self.assertEqual(s.papel_no_boss(b, 22.5), "healer")

    def test_npc_comum_e_ignorado(self):
        self.f.enviar(1.0, g.spawn(777, 123456))
        self.assertNotIn(777, self.s.bosses)


if __name__ == "__main__":
    unittest.main()
