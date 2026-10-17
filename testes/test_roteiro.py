"""Testes da linha do tempo (a2parse/roteiro.py)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse.roteiro import ATORDOAMENTO, Previsor, aprender, medidor_atordoamento  # noqa: E402

BOSS = {"nome": "Teste", "mecanicas": [
    {"id": "faixa", "alerta": "SAI DA FAIXA", "acao_tipo": "sair", "gatilho": {"tipo": "skill", "skill_ids": [10, 11]}},
    {"id": "leque", "alerta": "ATRÁS DELE", "acao_tipo": "atras", "gatilho": {"tipo": "skill", "skill_ids": [20]}},
    {"id": "ceu", "alerta": "FASE DO CÉU", "acao_tipo": "atencao", "gatilho": {"tipo": "skill", "skill_ids": [90]}},
]}


def run(hp_ceu=78.0):
    """Laço: 5 (sem ficha) → faixa +2,3 → leque +2,4 → 5 +4 ...; fase do céu a ~78% de HP."""
    t, hp, out = 0.0, 100.0, []
    for volta in range(6):
        for s, d in ((5, 4.0), (10 if volta % 2 else 11, 2.3), (20, 2.4)):
            t += d
            hp -= 1.5
            out.append((t, s, hp))
        if hp <= hp_ceu and not any(x[1] == 90 for x in out):
            out.append((t + 1, 90, hp))
    return out


class TestRoteiro(unittest.TestCase):
    def test_medidor_de_atordoamento(self):
        self.assertEqual(medidor_atordoamento(bytes.fromhex("cf8b020301b0040000a604000002")), (34255, 1190, 1200))
        self.assertIsNone(medidor_atordoamento(b"\x01\x02"))

    def test_aprende_a_cadeia_juntando_variacoes(self):
        r = aprender([run(), run(), run()], BOSS)
        self.assertEqual(r["cadeia"]["5"]["proxima"], "faixa")          # 10 e 11 viram o mesmo nó
        self.assertAlmostEqual(r["cadeia"]["faixa"]["apos"], 2.4)
        self.assertEqual([(f["no"], f["vez"]) for f in r["fases_hp"]], [("ceu", 1)])

    def test_previsor_encadeia_a_partir_do_cast(self):
        p = Previsor(aprender([run(), run(), run()], BOSS), BOSS)
        p.cast(100.0, 5)
        linha = {}
        for x in p.linha(100.0):
            linha.setdefault(x.texto, round(x.eta, 1))        # a 1ª volta do laço
        self.assertEqual(linha["SAI DA FAIXA"], 2.3)
        self.assertEqual(linha["ATRÁS DELE"], 4.7)

    def test_fase_por_hp_pelo_ritmo_de_dano(self):
        p = Previsor(aprender([run(), run(), run()], BOSS), BOSS)
        for k in range(11):                       # cai 1% por segundo, de 92% a 82%
            p.hp_pct(float(k), 92.0 - k)
        ceu = [x for x in p.linha(10.0) if x.texto == "FASE DO CÉU"]
        self.assertEqual(len(ceu), 1)
        self.assertAlmostEqual(ceu[0].eta, 82.0 - max(f["hp"] for f in p.roteiro["fases_hp"]), delta=0.6)

    def test_atordoamento_pelo_medidor(self):
        p = Previsor({"cadeia": {}, "fases_hp": [], "ciclos": {}}, BOSS)
        for k in range(7):                        # desce 100 por segundo
            p.atordoamento(float(k), 1200 - 100 * k, 1200)
        a = [x for x in p.linha(6.0) if x.fonte == "atordoamento"]
        self.assertAlmostEqual(a[0].eta, 6.0, delta=0.1)
        p.cast(12.0, ATORDOAMENTO)
        p.atordoamento(17.0, 1200, 1200)          # recarregou: começa do zero
        self.assertEqual([x for x in p.linha(17.0) if x.fonte == "atordoamento"], [])


class TestLinhaNaSessao(unittest.TestCase):
    """A linha do tempo usa o mesmo filtro de papel dos alertas (o leque do Auldor é só do tank)."""

    def linha(self, papel):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gerador as g
        from test_aovivo import Fluxo
        from a2parse.alertas import carregar_mecanicas
        from a2parse.aovivo import Sessao
        faixa, leque = "divine-auldor-faixas-laranja-caminho-dos-tornados", "divine-auldor-leque-frontal-4-tornados"
        rot = {"Divine Auldor": {"cadeia": {faixa: {"proxima": leque, "apos": 2.4, "chance": 0.9, "vezes": 5}},
                                 "fases_hp": [], "ciclos": {}, "precisao_centro": 0.9}}
        s = Sessao(carregar_mecanicas(), papel_fixo=papel, roteiros=rot)
        f = Fluxo(s)
        f.enviar(0.0, b"", syn=True)
        f.enviar(0.1, g.horario(1) + g.spawn(27268, 2300218) + g.hp(27268, 9_000_000))
        f.enviar(1.0, g.inicio_skill(27268, 1600930, 27268, 0))
        return [i["texto"] for i in s.estado(1.1)["linha"]]

    def test_dps_nao_ve_o_leque(self):
        self.assertNotIn("ATRÁS DELE", self.linha("dps"))

    def test_tank_ve_com_o_texto_dele(self):
        self.assertIn("VIRA ELE PRA FORA", self.linha("tank"))


if __name__ == "__main__":
    unittest.main()
