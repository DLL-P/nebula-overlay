"""Pacote de contribuição: os dados da luta saem, os nomes não."""

import json
import os
import random
import sys
import tempfile
import unittest
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import gerador as g  # noqa: E402
from a2parse import contribuicao  # noqa: E402

AULDOR_NPC, BOSS, EU, OUTRO = 2300218, 27268, 9230, 15935
SERVIDOR = ("203.0.113.5", 2106, "192.168.1.10", 51000)


def captura(caminho: str) -> None:
    stream = (g.horario(1_792_000_000_000) + g.eu(EU, "Heroi") + g.personagem(OUTRO, "Fulano")
              + g.spawn(BOSS, AULDOR_NPC) + g.hp(BOSS, 8_000_000)
              + g.dano(EU, BOSS, 11020000, 50_000) + g.dano(OUTRO, BOSS, 15010000, 70_000)
              + g.preparo(BOSS, 1600930, EU) + g.inicio_skill(BOSS, 1600930, EU, 0)
              + g.dano(BOSS, EU, 1600930, 9_000) + g.dano(BOSS, OUTRO, 1600930, 8_000)
              + g.hp(BOSS, 4_000_000) + g.dano(EU, BOSS, 11020000, 30_000) + g.morte(BOSS))
    w = g.EscritorPcapng()
    g.enviar_fluxo(w, random.Random(3), SERVIDOR, stream, 100.0)
    w.salvar(caminho)


class TestContribuicao(unittest.TestCase):
    def test_run_sem_nomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap = os.path.join(tmp, "run.pcapng")
            captura(cap)
            r = contribuicao.exportar(cap)
        texto = json.dumps(r, ensure_ascii=False)
        for proibido in ("Heroi", "Fulano", str(EU), str(OUTRO), "203.0.113.5", "192.168.1.10"):
            self.assertNotIn(proibido, texto)
        b = r["bosses"][0]
        self.assertEqual((b["nome"], b["mob"], b["masmorra"], b["morto"]), ("Divine Auldor", AULDOR_NPC, "Urugugu Canyon", True))
        self.assertEqual(b["casts"][0]["skill"], 1600930)
        self.assertEqual(b["casts"][0]["alvo"], "voce")
        self.assertIsNotNone(b["casts"][0]["preparo_s"])
        self.assertEqual(b["golpes"]["1600930"]["jogadores_por_vez"], 2)
        self.assertEqual(b["dano"], {"voce": 80_000, "J1": 70_000})
        self.assertEqual(r["jogadores"]["J1"]["classe"], "SORCERER")

    def test_pacote_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap = os.path.join(tmp, "run.pcapng")
            captura(cap)
            antigo = contribuicao.pasta_usuario
            contribuicao.pasta_usuario = lambda *p: os.makedirs(os.path.join(tmp, *p), exist_ok=True) or os.path.join(tmp, *p)
            try:
                z = contribuicao.empacotar(cap, {"conteudo": "Urugugu Conquista", "relato": "o mergulho veio cedo"})
                com_bruta = contribuicao.empacotar(cap, {"relato": "x"}, incluir_captura=True)
            finally:
                contribuicao.pasta_usuario = antigo
            with zipfile.ZipFile(z) as f:
                self.assertEqual(sorted(f.namelist()), ["relato.json", "run.json"])
                self.assertEqual(json.loads(f.read("relato.json"))["relato"], "o mergulho veio cedo")
            self.assertIn("urugugu-conquista", os.path.basename(z))
            with zipfile.ZipFile(com_bruta) as f:
                self.assertIn("run.pcapng", f.namelist())


if __name__ == "__main__":
    unittest.main()
