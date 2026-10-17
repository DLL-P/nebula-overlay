"""Testes do parser com capturas sintéticas. Rode da pasta aion2-meter:

    python -m unittest discover -s testes -v
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import gerador as g  # noqa: E402
from a2parse import decoders  # noqa: E402
from a2parse.analise import Analise  # noqa: E402
from a2parse.protocolo import FramerFluxo, lz4_descomprimir, mensagens_do_bloco  # noqa: E402

SERVIDOR = ("203.0.113.5", 2106, "192.168.1.10", 51000)
BOSS = 900001


def montar_luta(rng: random.Random):
    """Gera o stream de uma luta e o total esperado por origem."""
    esperado: dict[int, int] = {}
    mensagens: list[bytes] = [g.horario(1_792_100_000_000), g.combat_power(91500, 93000), g.desconhecido()]
    hp = 5_000_000
    pend: list[bytes] = []
    for passo in range(400):
        origem = rng.choice([1001, 1002, 1003])
        valor = rng.randint(500, 9000)
        multi = [rng.randint(10, 99) for _ in range(rng.randint(2, 4))] if rng.random() < 0.1 else None
        pend.append(g.dano(origem, BOSS, 11050000 + origem, valor, critico=rng.random() < 0.3,
                           costas=rng.random() < 0.3, double=rng.random() < 0.1, cura=rng.choice([None, 50]),
                           multi=multi, extra01=rng.random() < 0.2, extra08=rng.random() < 0.2))
        esperado[origem] = esperado.get(origem, 0) + valor
        hp -= valor
        if rng.random() < 0.1:
            pend.append(g.dano(origem, BOSS, 11050000, 99999, proc=True))
        if rng.random() < 0.05:
            pend.append(g.dano(origem, BOSS, 11050000, 99999, refletido=True))
        if passo % 10 == 0:
            pend.append(g.dot(1002, BOSS, 15060001, 300))
            esperado[1002] = esperado.get(1002, 0) + 300
            pend.append(g.dot(1004, 1003, 17070000, 800, mascara=0x02))  # cura: descartada
        if passo % 25 == 0:
            pend.append(g.inicio_skill(BOSS, 23004711, 1002, 0, posicao=passo % 50 == 0,
                                       alvos_extras=(1001, 1003) if passo % 75 == 0 else ()))
            pend.append(g.inicio_skill(1001, 11050000, BOSS, 12000, cargas=2))
        if len(pend) >= rng.randint(2, 6):
            mensagens.append(g.bloco(pend) if rng.random() < 0.8 else b"".join(pend))
            pend = []
        if passo % 20 == 0:
            mensagens.append(g.hp(BOSS, max(hp, 1)))
    mensagens.append(g.bloco(pend + [g.hp(BOSS, 0)]))
    mensagens.append(g.morte(BOSS))
    return b"".join(mensagens), esperado


class TestLZ4(unittest.TestCase):
    def test_ida_e_volta(self):
        rng = random.Random(1)
        for _ in range(200):
            n = rng.randint(0, 4000)
            dados = bytes(rng.choice([rng.randint(0, 255), 7, 7, 0]) for _ in range(n))
            self.assertEqual(lz4_descomprimir(g.lz4_comprimir(dados), n), dados)

    def test_bloco(self):
        (op, payload), = FramerFluxo().alimentar(g.horario(1) + g.bloco([g.hp(5, 10), g.morte(5)]))[1:]
        self.assertEqual(op, 0xFFFF)
        self.assertEqual([o for o, _ in mensagens_do_bloco(payload)], [0x8D00, 0x3642])


class TestDecoders(unittest.TestCase):
    def payload(self, m: bytes) -> bytes:
        # a âncora na frente faz o framer sincronizar mesmo com uma mensagem só
        (_, p), = FramerFluxo().alimentar(g.horario(1) + m)[1:]
        return p

    def test_dano_completo(self):
        p = self.payload(g.dano(7, 8, 11050000, 12345, critico=True, costas=True, double=True, parry=True,
                                cura=77, multi=[5, 6, 7], extra01=True, extra08=True))
        c = decoders.dano_direto(p)
        self.assertEqual((c["origem"], c["alvo"], c["skill"], c["dano"]), (7, 8, 11050000, 12345))
        self.assertTrue(c["critico"] and c["costas"] and c["double"] and c["parry"])
        self.assertEqual((c["cura"], c["hits"], c["multi_hit_dano"]), (77, 3, 18))

    def test_descartes(self):
        with self.assertRaises(decoders.Descartada):
            decoders.dano_direto(self.payload(g.dano(1, 2, 3, 4, proc=True)))
        with self.assertRaises(decoders.Descartada):
            decoders.dano_direto(self.payload(g.dano(1, 2, 3, 4, refletido=True)))
        with self.assertRaises(decoders.Descartada):
            decoders.dano_periodico(self.payload(g.dot(1, 2, 3, 4, mascara=0x02)))

    def test_inicio_skill(self):
        c = decoders.inicio_skill(self.payload(g.inicio_skill(9, 123, 4, 1500, cargas=3, posicao=True, alvos_extras=(5, 6))))
        self.assertEqual((c["conjurador"], c["skill"], c["alvo"], c["cooldown_ms"], c["cargas"], c["alvos_extras"]),
                         (9, 123, 4, 1500, 3, [5, 6]))


class TestCaptura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def analisar(self, w, **kw) -> Analise:
        caminho = os.path.join(self.tmp.name, "c.pcapng")
        w.salvar(caminho)
        a = Analise(**kw)
        a.processar_arquivo(caminho)
        return a

    def test_luta_com_reordenacao_e_retransmissao(self):
        rng = random.Random(42)
        stream, esperado = montar_luta(rng)
        w = g.EscritorPcapng()
        g.enviar_fluxo(w, rng, SERVIDOR, stream, 100.0, embaralhar=0.3, duplicar=0.1)
        # ruído: uma conexão TLS com bytes aleatórios, que deve ser ignorada
        g.enviar_fluxo(w, rng, ("10.0.0.9", 443, "192.168.1.10", 52000), bytes(rng.randrange(256) for _ in range(300_000)), 100.0)
        a = self.analisar(w)

        self.assertEqual({k: f.dano for k, f in a.fontes.items()}, esperado)
        self.assertEqual(sum(a.erros.values()), 0, a.exemplo_erro)
        jogo = a.fluxos_do_jogo()
        self.assertEqual(len(jogo), 1)
        self.assertEqual(jogo[0].chave, SERVIDOR)
        self.assertEqual(a.hp_atual[BOSS], 0)
        self.assertIn(BOSS, a.mortes)
        self.assertEqual(a.combat_power[-1][1:], (91500, 93000))
        self.assertEqual(len([c for c in a.casts if c[1] == BOSS]), 16)
        self.assertGreater(a.descartadas[0x3804], 0)
        self.assertGreater(a.descartadas[0x3805], 0)
        self.assertNotIn(1004, a.fontes)  # a cura não pode virar dano
        self.assertEqual(a.jogadores(), {1001, 1002, 1003})

    def test_comeco_no_meio_do_fluxo(self):
        rng = random.Random(7)
        stream, _ = montar_luta(rng)
        corte = 1337  # cai no meio de uma mensagem
        w = g.EscritorPcapng()
        g.enviar_fluxo(w, rng, SERVIDOR, stream[corte:], 100.0, syn=False)
        a = self.analisar(w)
        self.assertEqual(sum(a.erros.values()), 0, a.exemplo_erro)
        self.assertGreater(sum(f.dano for f in a.fontes.values()), 0)
        self.assertEqual(a.fluxos_do_jogo()[0].framer.sincronizacoes, 1)

    def test_pacote_perdido(self):
        rng = random.Random(9)
        stream, esperado = montar_luta(rng)
        w = g.EscritorPcapng()
        g.enviar_fluxo(w, rng, SERVIDOR, stream, 100.0, perder={20})
        a = self.analisar(w)
        f = a.fluxos_do_jogo()[0]
        self.assertEqual(f.remontador.buracos, 1)
        self.assertEqual(sum(a.erros.values()), 0, a.exemplo_erro)
        total = sum(x.dano for x in a.fontes.values())
        self.assertLess(total, sum(esperado.values()))
        self.assertGreater(total, 0.8 * sum(esperado.values()))

    def test_filtro_de_porta(self):
        rng = random.Random(3)
        stream, _ = montar_luta(rng)
        w = g.EscritorPcapng()
        g.enviar_fluxo(w, rng, SERVIDOR, stream, 100.0)
        self.assertFalse(self.analisar(w, porta=9999).fontes)


if __name__ == "__main__":
    unittest.main()
