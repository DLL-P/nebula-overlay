"""Partes do app instalado: idiomas, versão/atualização, roteiros juntados, classes sem tabela do jogo."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse import atualizar, idioma, roteiro  # noqa: E402
from a2parse.alertas import carregar_dicas, carregar_mecanicas  # noqa: E402
from a2parse.classes import PC_CLASSES  # noqa: E402


class TestIdioma(unittest.TestCase):
    def tearDown(self):
        idioma.definir("pt")

    def test_textos_da_interface_nos_tres_idiomas(self):
        for chave, textos in idioma.UI.items():
            self.assertEqual(len(textos), 3, chave)
            self.assertTrue(all(textos), chave)
        idioma.definir("en")
        self.assertEqual(idioma.t("em_s", s="5", texto="SPREAD"), "IN 5s · SPREAD")
        idioma.definir("es")
        self.assertEqual(idioma.t("eu"), "YO")

    def test_alertas_traduzidos_e_em_breve(self):
        idioma.definir("en")
        self.assertEqual(idioma.tr("SAI DA ZONA"), "LEAVE THE ZONE")
        self.assertEqual(idioma.tr("EM BREVE: ESPALHA"), "SOON: SPREAD")
        self.assertEqual(idioma.tr("texto que não existe"), "texto que não existe")
        idioma.definir("pt")
        self.assertEqual(idioma.tr("SAI DA ZONA"), "SAI DA ZONA")

    def test_todo_texto_de_alerta_tem_traducao(self):
        """Mecânica nova sem tradução aparece em português: este teste lembra de traduzir."""
        textos = set()

        def andar(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in ("alerta", "acao", "texto", "sub") and isinstance(v, str) and v.strip():
                        textos.add(v)
                    else:
                        andar(v)
            elif isinstance(x, list):
                for v in x:
                    andar(v)
        andar(carregar_mecanicas(usuario=None)["masmorras"])
        for dicas in carregar_dicas().values():
            textos.update(dicas.values())
        for cod in ("en", "es"):
            faltam = sorted(textos - set(idioma._traducoes(cod)))
            self.assertEqual(faltam, [], f"sem tradução para {cod}")

    def test_numero_no_formato_do_idioma(self):
        idioma.definir("pt")
        self.assertEqual(idioma.numero(12345), "12,3k")
        idioma.definir("en")
        self.assertEqual(idioma.numero(1234567), "1.23M")


class TestAtualizar(unittest.TestCase):
    def test_numeros_da_versao(self):
        self.assertEqual(atualizar.numeros("v2026.10.17.4"), (2026, 10, 17, 4))
        self.assertGreater(atualizar.numeros("2026.10.17.10"), atualizar.numeros("2026.10.17.9"))
        self.assertEqual(atualizar.numeros("dev"), ())

    def test_so_baixa_do_proprio_repositorio(self):
        info = {"versao": "1.2", "instalador": "https://exemplo.com/x.exe", "sha256": "https://exemplo.com/x.sha256"}
        with self.assertRaises(ValueError):
            atualizar.baixar(info)


class TestRoteiros(unittest.TestCase):
    def test_junta_o_do_programa_e_o_aprendido_aqui_pelo_numero_de_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            prog, local = os.path.join(tmp, "prog.json"), os.path.join(tmp, "local.json")
            json.dump({"A": {"runs": 6, "de": "prog"}, "B": {"runs": 1, "de": "prog"}}, open(prog, "w"))
            json.dump({"A": {"runs": 2, "de": "local"}, "B": {"runs": 3, "de": "local"}, "C": {"runs": 1, "de": "local"}},
                      open(local, "w"))
            antigos = roteiro.CAMINHO, roteiro.CAMINHO_LOCAL
            roteiro.CAMINHO, roteiro.CAMINHO_LOCAL = prog, local
            try:
                r = roteiro.carregar()
            finally:
                roteiro.CAMINHO, roteiro.CAMINHO_LOCAL = antigos
            self.assertEqual({k: v["de"] for k, v in r.items()}, {"A": "prog", "B": "local", "C": "local"})


class TestClasses(unittest.TestCase):
    def test_id_de_classe_em_faixas_de_quatro(self):
        self.assertEqual(PC_CLASSES[5], "GLADIATOR")
        self.assertEqual(PC_CLASSES[8], "GLADIATOR")
        self.assertEqual(PC_CLASSES[9], "TEMPLAR")
        self.assertEqual(PC_CLASSES[36], "CHANTER")
        self.assertEqual(PC_CLASSES[45], "FIGHTER")
        self.assertNotIn(40, PC_CLASSES)


if __name__ == "__main__":
    unittest.main()
