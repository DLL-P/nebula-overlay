"""Latência só lendo o tráfego: ping pelos ACKs (conexão direta), oscilação pelo horário do servidor (acelerador)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse.captura import ACK, SegmentoTCP  # noqa: E402
from a2parse.latencia import Latencia  # noqa: E402

SERVIDOR, CLIENTE = ("203.0.113.5", 7777), ("192.168.1.10", 51000)
PROXY, JOGO = ("127.0.0.1", 51736), ("127.0.0.1", 54551)


class _Fluxo:
    def __init__(self, jogo: bool) -> None:
        self.parece_jogo = jogo


def _fluxos(servidor, cliente) -> dict:
    """Como o Analise.fluxos: o sentido servidor → cliente é o que tem mensagens do jogo."""
    return {(*servidor, *cliente): _Fluxo(True), (*cliente, *servidor): _Fluxo(False)}


def _seg(ts, origem, destino, seq, dados=b"", ack=0):
    return SegmentoTCP(ts, origem[0], origem[1], destino[0], destino[1], seq, ACK, dados, ack)


class TestPing(unittest.TestCase):
    def setUp(self):
        self.l, self.f = Latencia(), _fluxos(SERVIDOR, CLIENTE)

    def _troca(self, ts, seq, rtt, atraso_ack=0.0):
        """O cliente manda 10 bytes; o servidor confirma rtt (+ atraso do ACK) depois."""
        self.l.segmento(_seg(ts, CLIENTE, SERVIDOR, seq, b"x" * 10), self.f)
        self.l.segmento(_seg(ts + rtt + atraso_ack, SERVIDOR, CLIENTE, 999, b"dados", ack=seq + 10), self.f)

    def test_ping_e_o_menor_rtt_da_janela(self):
        for i, atraso in enumerate((0.03, 0.0, 0.045, 0.01, 0.02)):     # ACK que sai junto com o próximo pacote
            self._troca(100 + i, 1000 + 10 * i, 0.042, atraso)
        e = self.l.estado(104.1)
        self.assertEqual((e["tipo"], e["ms"], e["nivel"]), ("ping", 42, "bom"))

    def test_ack_cumulativo_mede_pelo_ultimo_segmento_coberto(self):
        self.l.segmento(_seg(10.0, CLIENTE, SERVIDOR, 0, b"a" * 10), self.f)
        self.l.segmento(_seg(10.05, CLIENTE, SERVIDOR, 10, b"b" * 10), self.f)
        self.l.segmento(_seg(10.15, SERVIDOR, CLIENTE, 1, b"", ack=20), self.f)
        self.assertAlmostEqual(self.l.rtts[-1][1], 0.10, places=6)

    def test_retransmissao_nao_conta(self):
        self.l.segmento(_seg(10.0, CLIENTE, SERVIDOR, 0, b"a" * 10), self.f)
        self.l.segmento(_seg(10.5, CLIENTE, SERVIDOR, 0, b"a" * 10), self.f)       # reenviado
        self.l.segmento(_seg(10.52, SERVIDOR, CLIENTE, 1, b"", ack=10), self.f)
        self.assertEqual(len(self.l.rtts), 0)

    def test_outros_programas_nao_entram(self):
        outro = ("198.51.100.9", 3478)
        f = {**self.f, (*outro, *CLIENTE): _Fluxo(False)}
        self.l.segmento(_seg(1.0, CLIENTE, outro, 0, b"a" * 10), f)
        self.l.segmento(_seg(1.3, outro, CLIENTE, 1, b"", ack=10), f)
        self.assertEqual(len(self.l.rtts), 0)

    def test_ping_alto_fica_vermelho(self):
        for i in range(3):
            self._troca(50 + i, 10 * i, 0.210)
        self.assertEqual(self.l.estado(52.3)["nivel"], "ruim")


class TestAcelerador(unittest.TestCase):
    def test_loopback_mostra_a_oscilacao_e_nao_o_rtt_do_proxy(self):
        l, f = Latencia(), _fluxos(PROXY, JOGO)
        for i in range(60):
            ts = 1000 + i * 0.05
            l.segmento(_seg(ts, JOGO, PROXY, 10 * i, b"x" * 10), f)
            l.segmento(_seg(ts + 0.0001, PROXY, JOGO, 1, b"", ack=10 * i + 10), f)      # o proxy confirma na hora
            l.relogio(ts, int((ts - 4.0) * 1000))                                            # relógio 4 s atrasado
        e = l.estado(1000 + 59 * 0.05)
        self.assertTrue(l.proxy)
        self.assertEqual(len(l.rtts), 0)
        self.assertEqual(e["tipo"], "oscilacao")
        self.assertLessEqual(e["ms"], 1)                  # o atraso constante de 4 s some: é a diferença dos relógios

    def test_lag_aparece_como_oscilacao(self):
        l = Latencia()
        for i in range(100):
            ts = 2000 + i * 0.05
            atraso = 0.060 if i >= 80 else 0.0               # nos últimos 1 s, tudo chega 60 ms atrasado
            l.relogio(ts + atraso, int(ts * 1000) - 4000)
        e = l.estado(2000 + 99 * 0.05 + 0.06)
        self.assertEqual(e["tipo"], "oscilacao")
        self.assertGreaterEqual(e["ms"], 59)
        self.assertEqual(e["nivel"], "ruim")

    def test_servidor_parado(self):
        l = Latencia()
        for i in range(20):
            l.relogio(10 + i * 0.05, 10_000 + i * 50)
        e = l.estado(10 + 19 * 0.05 + 2.5)
        self.assertEqual((e["tipo"], e["nivel"]), ("parado", "ruim"))
        self.assertAlmostEqual(e["ms"], 2500, delta=5)
        self.assertIsNone(l.estado(10 + 19 * 0.05 + 60))     # jogo fechado: some do rodapé


if __name__ == "__main__":
    unittest.main()
