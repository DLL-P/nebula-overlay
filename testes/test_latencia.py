"""Tempo de resposta do servidor só lendo o tráfego: eco do jogo (com e sem acelerador), ACKs do TCP (direto)."""

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


class TestEco(unittest.TestCase):
    """O cliente manda 12 bytes a cada 10 s e o servidor responde com o 0x3603: vale com e sem acelerador."""

    def _sessao_de_ecos(self, servidor, cliente, rtts, tcp_na_hora=False):
        l, f = Latencia(), _fluxos(servidor, cliente)
        volta = (*servidor, *cliente)
        for i, rtt in enumerate(rtts):
            ts = 100 + 10 * i
            for k in range(5):                                       # movimento: pacotes de 11 bytes
                l.segmento(_seg(ts - 0.5 + k * 0.05, cliente, servidor, 1000 * i + 11 * k, b"m" * 11), f)
            l.segmento(_seg(ts, cliente, servidor, 1000 * i + 500, b"p" * 12), f)
            if tcp_na_hora:                                          # o proxy local confirma na hora
                l.segmento(_seg(ts + 0.0001, servidor, cliente, 1, b"", ack=1000 * i + 512), f)
            l.heartbeat(ts + rtt, volta)
            for k in range(25):                                      # horário do servidor, sem lag
                t = ts + rtt + k * 0.04
                l.relogio(t, int(t * 1000) - 4000)
        return l, 100 + 10 * (len(rtts) - 1) + rtts[-1] + 0.96

    def test_com_acelerador_mostra_o_tempo_de_resposta_e_nao_o_ack_do_proxy(self):
        l, agora = self._sessao_de_ecos(PROXY, JOGO, [0.068, 0.071, 0.070], tcp_na_hora=True)
        e = l.estado(agora)
        self.assertTrue(l.proxy)
        self.assertEqual((e["tipo"], e["ms"], e["nivel"]), ("ping", 70, "bom"))

    def test_direto_tambem_usa_o_eco(self):
        l, agora = self._sessao_de_ecos(SERVIDOR, CLIENTE, [0.120, 0.180, 0.125])
        self.assertEqual(l.estado(agora)["ms"], 125)                 # mediana: um eco atrasado não pula o número
        self.assertEqual(l.estado(agora)["nivel"], "medio")

    def test_heartbeat_sem_eco_nao_conta(self):
        l = Latencia()
        l.heartbeat(10.0, (*SERVIDOR, *CLIENTE))
        self.assertEqual(len(l.ecos), 0)

    def test_lag_entre_um_eco_e_outro_soma_no_ping(self):
        l, agora = self._sessao_de_ecos(PROXY, JOGO, [0.070, 0.070, 0.070])
        for k in range(25):                                          # agora tudo chega 60 ms atrasado
            t = agora + k * 0.04
            l.relogio(t + 0.060, int(t * 1000) - 4000)
        e = l.estado(agora + 24 * 0.04 + 0.06)
        self.assertGreaterEqual(e["ms"], 125)
        self.assertEqual(e["nivel"], "medio")

    def test_servidor_parado(self):
        l = Latencia()
        for i in range(20):
            l.relogio(10 + i * 0.05, 10_000 + i * 50)
        e = l.estado(10 + 19 * 0.05 + 2.5)
        self.assertEqual((e["tipo"], e["nivel"]), ("parado", "ruim"))
        self.assertAlmostEqual(e["ms"], 2500, delta=5)
        self.assertIsNone(l.estado(10 + 19 * 0.05 + 60))     # jogo fechado: some do rodapé

    def test_sem_eco_no_loopback_nao_inventa_numero(self):
        l, f = Latencia(), _fluxos(PROXY, JOGO)
        for i in range(10):
            l.segmento(_seg(1 + i * 0.05, JOGO, PROXY, 10 * i, b"x" * 10), f)
            l.segmento(_seg(1 + i * 0.05 + 0.0001, PROXY, JOGO, 1, b"", ack=10 * i + 10), f)
            l.relogio(1 + i * 0.05, int((1 + i * 0.05) * 1000))
        self.assertIsNone(l.estado(1.5))


if __name__ == "__main__":
    unittest.main()
