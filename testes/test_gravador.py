"""Testes da gravação em espera (overlay.Gravador)."""

from __future__ import annotations

import glob
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import overlay  # noqa: E402


def pacotes(caminho):
    b = open(caminho, "rb").read()
    i, ts = 24, []
    while i + 16 <= len(b):
        s, us, incl, _ = struct.unpack_from("<IIII", b, i)
        ts.append(s + us / 1e6)
        i += 16 + incl
    return ts


class TestGravador(unittest.TestCase):
    def test_grava_so_a_masmorra_com_memoria_e_espera(self):
        with tempfile.TemporaryDirectory() as tmp:
            if True:
                g = overlay.Gravador(0, os.path.join(tmp, "capturas"))
                for t in range(0, 400):
                    g.ativo = 200 <= t < 250              # boss apareceu em 200, saiu da zona em 250
                    g.pacote(1000.0 + t, b"x" * 10, 10)
                g.fechar()
                arquivos = glob.glob(os.path.join(tmp, "capturas", "*.pcap"))
                self.assertEqual(len(arquivos), 1)
                ts = pacotes(arquivos[0])
                self.assertEqual(ts[0], 1000.0 + 200 - g.MEMORIA)      # 2 min antes do boss
                self.assertEqual(ts[-1], 1000.0 + 250 + g.ESPERA)       # 60 s depois de sair

    def test_voltar_na_espera_nao_divide_o_arquivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            if True:
                g = overlay.Gravador(0, os.path.join(tmp, "capturas"))
                for t in range(0, 300):
                    g.ativo = 50 <= t < 100 or 130 <= t < 200  # morreu e voltou 30 s depois
                    g.pacote(float(t), b"x", 1)
                g.fechar()
                self.assertEqual(len(glob.glob(os.path.join(tmp, "capturas", "*.pcap"))), 1)


if __name__ == "__main__":
    unittest.main()
