"""Testes do meter de jogadores (a2parse/meter.py) e do adiantamento dos alertas."""

from __future__ import annotations

import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from a2parse.alertas import MotorAlertas, boss, carregar_mecanicas  # noqa: E402
from a2parse.meter import Medidor  # noqa: E402

DADOS = carregar_mecanicas()


class Boss:
    def __init__(self, nome):
        self.nome = nome


BOSS, ADD, EU, OUTRO = 900, 901, 10, 11
BOSSES = {BOSS: Boss("Divine Auldor")}
NOMES = {EU: "Heroi", OUTRO: "Fulano"}


def golpe(origem, alvo, dano, skill=11_020_000, critico=False):
    return {"origem": origem, "alvo": alvo, "dano": dano, "skill": skill, "critico": critico}


class TestMedidor(unittest.TestCase):
    def setUp(self):
        self.m = Medidor()
        self.j = lambda e: e in NOMES

    def bater(self, ts, *args, **kw):
        self.m.dano(ts, golpe(*args, **kw), BOSSES, self.j)

    def test_luta_vai_do_primeiro_ao_ultimo_golpe_no_boss(self):
        self.bater(10.0, EU, BOSS, 1000)
        self.bater(12.0, OUTRO, ADD, 500, skill=14_010_000)      # add no meio da luta: conta
        self.bater(20.0, OUTRO, BOSS, 3000, skill=14_010_000)
        self.bater(22.0, EU, ADD, 999)                            # depois do último golpe no boss: não conta
        self.m.morte(25.0, BOSS)
        l = self.m.atual
        self.assertEqual((l.inicio, l.fim), (10.0, 20.0))
        self.assertEqual(dict(l.dano), {EU: 1000, OUTRO: 3500})
        st = self.m.estado(30.0, NOMES, EU)
        self.assertEqual([x["nome"] for x in st["linhas"]], ["Fulano", "Heroi"])
        self.assertEqual([x["classe"] for x in st["linhas"]], ["Arqueiro", "Gladiador"])
        self.assertTrue(st["linhas"][1]["voce"])
        self.assertAlmostEqual(st["linhas"][0]["dps"], 350.0)   # 3500 em 10 s
        self.assertFalse(st["ativa"])

    def test_boss_com_skill_de_classe_nao_vira_jogador(self):
        self.bater(1.0, EU, BOSS, 100)
        self.m.dano(2.0, golpe(BOSS, EU, 50, skill=11_020_000), BOSSES, self.j)  # efeito refletido
        self.bater(3.0, EU, BOSS, 100)
        self.assertNotIn(BOSS, self.m.classes)
        self.assertEqual(self.m.atual.dano[EU], 200)

    def test_inatividade_fecha_e_nova_luta_guarda_a_ultima(self):
        self.bater(1.0, EU, BOSS, 100)
        self.m.tick(40.0)                                          # 39 s sem golpe no boss: wipe/reset
        self.assertEqual(self.m.atual.fim, 1.0)
        self.bater(50.0, EU, BOSS, 100)
        self.assertEqual(self.m.ultima.inicio, 1.0)
        self.assertEqual(self.m.atual.inicio, 50.0)

    def test_status_aparece_na_linha_do_jogador(self):
        self.bater(1.0, EU, BOSS, 100)
        st = self.m.estado(2.0, NOMES, EU, [{"em": "alvo", "alvo": EU, "texto": "POÇA"}])
        self.assertEqual(st["linhas"][0]["status"], ["POÇA"])


class TestOdyle(unittest.TestCase):
    def test_tickets_e_atualizacao(self):
        import struct
        import gerador as g
        from a2parse.decoders import ODYLE, ticket_atualizado, tickets
        lista = g.varint(2) + bytes([8]) + struct.pack("<I", ODYLE) + g.varint(40) + bytes([4]) + struct.pack("<I", 1) + g.varint(21)
        t = tickets(lista)["tickets"]
        self.assertEqual(t[0], {"ticket": ODYLE, "restante": 0, "recarga": 40})
        self.assertEqual(t[1]["restante"], 21)
        upd = bytes([0, 12]) + struct.pack("<I", ODYLE) + g.varint(30) + g.varint(35) + bytes([3])
        self.assertEqual(ticket_atualizado(upd)["tickets"][0], {"ticket": ODYLE, "restante": 30, "recarga": 35})


class TestPreparo(unittest.TestCase):
    def test_decoder(self):
        sys.path.insert(0, AQUI)
        import gerador as g
        from a2parse.decoders import preparo_skill
        self.assertEqual(preparo_skill(g.preparo(49322, 1504440, 3489)[3:]),
                         {"conjurador": 49322, "flag": 2, "skill": 1504440, "alvo": 3489})

    def test_aviso_sai_no_preparo_e_o_cast_so_confirma(self):
        m = MotorAlertas(boss(DADOS, "Guardian Captain Raur"), modo_skills=True, antecipar=0.8)
        a = m.preparo(10.0, 1504440, 7)
        self.assertEqual([(x.texto, x.t, x.contagem) for x in a], [("SAI DE PERTO", 10.0, 3.0)])   # 1 s + 2 s
        self.assertEqual([x.texto for x in m.skill(11.0, 1504440, 7) + m.avancar(20)], [])

    def test_zona_do_raur_avisa_3s_antes_com_o_burst(self):
        m = MotorAlertas(boss(DADOS, "Guardian Captain Raur"), modo_skills=True, antecipar=0.8)
        a = {x.texto: (x.t, x.contagem) for x in m.preparo(10.0, 1504450, 53590)}
        self.assertEqual(a["SAI DA ZONA"][0], 10.0)
        self.assertAlmostEqual(a["SAI DA ZONA"][1], 7.85)                 # 3 s de preparo + 4,85 s até a explosão
        self.assertEqual(a["SEGURA O BURST"][0], 10.0)

    def test_precursora_e_preparo_nao_duplicam(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, antecipar=0.8)
        saida = m.skill(0.0, 1600880, 1) + m.preparo(1.35, 1600930, 27268) + m.skill(2.35, 1600930, 27268) + m.avancar(9)
        self.assertEqual([x.texto for x in saida].count("SAI DA FAIXA"), 1)

    def test_morte_do_boss_limpa_o_que_ele_preparava(self):
        sys.path.insert(0, AQUI)
        import gerador as g
        from test_aovivo import Fluxo
        from a2parse.aovivo import Sessao
        s = Sessao(DADOS)
        f = Fluxo(s)
        f.enviar(0.0, b"", syn=True)
        f.enviar(0.1, g.horario(1) + g.spawn(53590, 2300206) + g.hp(53590, 5_000_000))
        f.enviar(1.0, g.preparo(53590, 1504440, 1))
        self.assertIn("SAI DE PERTO", [x.texto for x in s.estado(1.1)["cartoes"]])
        f.enviar(1.5, g.morte(53590))
        self.assertEqual(s.estado(1.6)["cartoes"], [])


class TestAdiantamento(unittest.TestCase):
    def test_passo_previsto_sai_antes_e_a_contagem_cresce(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, burst=False, antecipar=0.5)
        saida = m.skill(100.0, 1601010, 27268) + m.avancar(108.0)
        empilha = next(a for a in saida if a.texto == "EMPILHA NO CÍRCULO")
        self.assertAlmostEqual(empilha.t, 107.5)                   # previsto em +8 s, sai 0,5 s antes
        self.assertAlmostEqual(empilha.t + empilha.contagem, 111.6)  # a contagem termina no mesmo instante

    def test_passo_imediato_nao_muda(self):
        m = MotorAlertas(boss(DADOS, "Judge Urahum"), modo_skills=True, antecipar=0.5)
        a = m.skill(5.0, 1605110, 1)[0]
        self.assertEqual((a.t, a.contagem), (5.0, 2.0))

    def test_precursora_avisa_a_faixa_antes(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, antecipar=0.5)
        saida = m.skill(10.0, 1600880, 1)                          # 1600880 vem sempre 2,35 s antes das faixas
        faixa = [a for a in saida if a.texto == "SAI DA FAIXA"]
        self.assertEqual(len(faixa), 1)
        self.assertAlmostEqual(faixa[0].t, 10.0)
        self.assertAlmostEqual(faixa[0].contagem, 4.35)            # 2,35 até o cast + 2 s até o impacto
        saida = m.skill(12.4, 1600930, 27268) + m.avancar(20.0)    # a skill de verdade só confirma
        self.assertNotIn("SAI DA FAIXA", [a.texto for a in saida])

    def test_faixa_sem_precursora_ainda_avisa(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True)
        self.assertEqual([a.texto for a in m.skill(10.0, 1600930, 27268)], ["SAI DA FAIXA"])


if __name__ == "__main__":
    unittest.main()
