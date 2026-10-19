"""Fechar junto com o jogo: só pelo processo do jogo, com espera, nunca no meio do jogo."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse.fechamento import Fechamento  # noqa: E402


class TestFechamento(unittest.TestCase):
    def test_jogo_aberto_nunca_fecha_mesmo_parado_por_horas(self):
        f = Fechamento()
        self.assertTrue(all(f.atualizar(True, t) is None for t in range(0, 6 * 3600, 60)))

    def test_abrir_o_app_antes_do_jogo_nao_fecha(self):
        f = Fechamento()
        self.assertTrue(all(f.atualizar(False, t) is None for t in range(0, 600)))

    def test_fecha_depois_da_espera_com_o_jogo_fechado(self):
        f = Fechamento(espera=120)
        f.atualizar(True, 0)
        self.assertEqual(f.atualizar(False, 10), 120)
        self.assertEqual(f.atualizar(False, 70), 60)
        self.assertEqual(f.atualizar(False, 130), 0)

    def test_jogo_reaberto_zera_a_contagem(self):
        f = Fechamento(espera=120)
        f.atualizar(True, 0)
        f.atualizar(False, 10)
        f.atualizar(True, 100)                       # travou e você reabriu (ou o launcher reiniciou)
        self.assertEqual(f.atualizar(False, 200), 120)

    def test_ocupado_espera_terminar(self):
        f = Fechamento(espera=120)
        f.atualizar(True, 0)
        f.atualizar(False, 10)
        self.assertIsNone(f.atualizar(False, 200, ocupado=True))   # baixando atualização, ferramenta aberta
        self.assertEqual(f.atualizar(False, 210), 120)

    def test_manter_aberto_vale_ate_o_jogo_abrir_de_novo(self):
        f = Fechamento(espera=120)
        f.atualizar(True, 0)
        f.atualizar(False, 10)
        f.manter_aberto()
        self.assertIsNone(f.atualizar(False, 1000))
        f.atualizar(True, 2000)
        self.assertEqual(f.atualizar(False, 2010), 120)


if __name__ == "__main__":
    unittest.main()
