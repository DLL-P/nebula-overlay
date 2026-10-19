"""Eventos de campo: pacotes 0x6000/0x6001 (bytes reais de 2026-10-16) e agenda."""

import datetime as dt
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse.eventos import Eventos, ler_evento, ler_lista, proximo_inicio  # noqa: E402

# 0x6001 recebido às 02:00:05: evento 110301 abre (fase 1) às 02:00:01, fase até 02:03:01
ABRIU = bytes.fromhex("03 dd dd 06 01 64 67 96 47 a1 01 00 00 64 67 96 47 a1 01 00 00 84 26 99 47 a1 01 00 00")
SHUGO = {"chave": "shugo", "nome": {"pt": "Festival Shugo"}, "ids": [110301], "agenda": {"tipo": "hora", "minuto": 0},
         "duracao_min": 8}


def ts(texto: str) -> float:
    return dt.datetime.fromisoformat(texto).replace(tzinfo=dt.timezone.utc).timestamp()


class TestPacotes(unittest.TestCase):
    def test_evento_abrindo(self):
        r = ler_evento(ABRIU)
        self.assertEqual((r["tipo"], r["evento"], r["fase"]), (3, 110301, 1))
        self.assertAlmostEqual(r["fim_fase"] - r["inicio"], 180.0, places=1)

    def test_lixo_nao_vira_evento(self):
        self.assertIsNone(ler_evento(b"\x03\x01\x01" + b"\x00" * 24))
        self.assertEqual(ler_lista(b"\x00"), [])

    def test_lista_com_um_registro(self):
        self.assertEqual(ler_lista(b"\x01" + ABRIU[1:])[0]["evento"], 110301)


class TestAgenda(unittest.TestCase):
    def test_hora_em_hora(self):
        self.assertEqual(proximo_inicio(SHUGO, ts("2026-10-17T01:57:00")), ts("2026-10-17T02:00:00"))
        self.assertEqual(proximo_inicio(SHUGO, ts("2026-10-17T02:00:00")), ts("2026-10-17T03:00:00"))

    def test_horarios_fixos_com_fuso_e_dias(self):
        ev = {"agenda": {"tipo": "horarios", "horas": ["21:00"], "dias": [1], "utc": "-03:00"}}   # terça, 21:00 de Brasília
        # 2026-10-17 é sábado: a próxima terça é 20/10, 21:00 em -03:00 = 00:00 UTC de 21/10
        self.assertEqual(proximo_inicio(ev, ts("2026-10-17T12:00:00")), ts("2026-10-21T00:00:00"))

    def test_em_breve_aberto_pelo_servidor_e_desligado(self):
        e = Eventos(definicoes=[SHUGO])
        r = ler_evento(ABRIU)
        antes = e.estado(r["inicio"] - 120, janela=300)
        self.assertEqual([(x["chave"], x["estado"]) for x in antes], [("shugo", "em_breve")])
        self.assertAlmostEqual(antes[0]["faltam"], 120, delta=2)      # a agenda conta da hora cheia; o servidor abre ~1,6 s depois
        self.assertEqual(e.estado(r["inicio"] - 900, janela=300), [])      # longe demais: nada
        e.mensagem(0x6001, ABRIU)
        agora = e.estado(r["inicio"] + 30)
        self.assertEqual(agora[0]["estado"], "aberto")
        self.assertAlmostEqual(agora[0]["restam"], 150, places=0)
        self.assertEqual(e.estado(r["inicio"] + 30, desligados={"shugo"}), [])

    def test_relogio_do_servidor(self):
        e = Eventos(definicoes=[SHUGO])
        e.relogio(1000.0, 1_792_000_008_000)                       # servidor 8 s à frente... de um PC parado em 1970
        self.assertGreater(e.atraso, 1e9)
        e.relogio(ts("2026-10-17T01:59:52"), int(ts("2026-10-17T02:00:00") * 1000))
        self.assertEqual(e.estado(ts("2026-10-17T01:59:52"), janela=60)[0]["faltam"], 0)

class TestMinijogos(unittest.TestCase):
    def test_not_this_tile_pelo_id_e_pela_duracao(self):
        from a2parse.eventos import carregar
        e = Eventos(definicoes=carregar())
        ini = ts("2026-10-19T04:00:01")
        e.abertos[110901] = {"evento": 110901, "fase": 2, "inicio": ini, "inicio_fase": ini + 180,
                             "fim_fase": ini + 180 + 195, "tipo": 3}
        e.abertos[110101] = {"evento": 110101, "fase": 2, "inicio": ini, "inicio_fase": ini + 180,
                             "fim_fase": ini + 180 + 175, "tipo": 3}
        m = e.minijogos(ini + 200)
        self.assertEqual([x["nome"]["pt"] for x in m], ["Jump Jump", "Not This Tile?"])
        self.assertAlmostEqual(m[1]["restam"], 175.0, places=1)
        self.assertIn("+100", m[1]["regras"]["pt"])
        self.assertEqual(e.minijogos(ini + 400), [])


class TestInvasao(unittest.TestCase):
    def test_120101_e_a_invasao_dimensional(self):
        """Captura de 2026-10-19: o 120101 abre às :30:01 (3 min de preparação + 10 min). Vira um cartão só,
        com o nome da agenda, e não "evento-120101" ao lado do cartão da agenda."""
        ini = ts("2026-10-19T17:30:01")
        varint = bytes([0xA5, 0xAA, 0x07])                     # 120101
        pacote = b"" + varint + b"" + struct.pack("<qqq", int(ini * 1000), int((ini + 180) * 1000),
                                                          int((ini + 780) * 1000))
        self.assertEqual(ler_evento(pacote)["evento"], 120101)
        e = Eventos()
        e.mensagem(0x6001, pacote)
        lista = e.estado(ini + 200)
        invasao = [x for x in lista if x["chave"] == "invasao-dimensional"]
        self.assertEqual(len(invasao), 1)
        self.assertEqual((invasao[0]["id"], invasao[0]["fase"]), (120101, 2))
        self.assertAlmostEqual(invasao[0]["restam"], 580.0, places=1)
        self.assertFalse(any(x["chave"].startswith("evento-") for x in lista))


if __name__ == "__main__":
    unittest.main()
