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

    def test_cada_idioma_tem_todos_os_textos(self):
        self.assertTrue({"pt", "en", "es"} <= set(idioma.IDIOMAS))
        chaves = set(idioma._parte("pt", "interface"))
        for cod in idioma.IDIOMAS:
            for parte in ("interface", "classes", "papeis", "voz"):
                faltam = set(idioma._parte("pt", parte)) - set(idioma._parte(cod, parte))
                self.assertEqual(faltam, set(), f"{cod}: {parte}")
            self.assertTrue(all(idioma._parte(cod, "interface").values()), cod)
        self.assertGreater(len(chaves), 90)
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

    def test_idioma_novo_e_so_um_arquivo(self):
        """Um fr.json com metade dos textos já funciona: o resto sai em inglês."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "idiomas"))
            json.dump({"idioma": {"nome": "Français", "voz": "fr-FR", "regioes": ["fr"]},
                       "interface": {"btn_sair": "Quitter"}, "voz": {"sair": "Sortez !"}},
                      open(os.path.join(tmp, "idiomas", "fr.json"), "w", encoding="utf-8"))
            antigo = idioma.usuario
            idioma.usuario = lambda *p: os.path.join(tmp, *p)
            try:
                novos = idioma._carregar()
            finally:
                idioma.usuario = antigo
            guardado = dict(idioma._IDIOMAS), dict(idioma.IDIOMAS)
            idioma._IDIOMAS.clear(), idioma._IDIOMAS.update(novos)
            idioma.IDIOMAS["fr"] = "Français"
            try:
                idioma.definir("fr")
                self.assertEqual(idioma.t("btn_sair"), "Quitter")
                self.assertEqual(idioma.t("btn_config"), "Settings")              # faltou: inglês
                self.assertIn(("fr-FR", "Français"), idioma.vozes())
                self.assertEqual(idioma.frases("fr-FR")["sair"], "Sortez !")
                self.assertNotIn("pular", idioma.frases("fr-FR"))                # sem frase: bipe
            finally:
                idioma._IDIOMAS.clear(), idioma._IDIOMAS.update(guardado[0])
                idioma.IDIOMAS.clear(), idioma.IDIOMAS.update(guardado[1])

    def test_numero_no_formato_do_idioma(self):
        idioma.definir("pt")
        self.assertEqual(idioma.numero(12345), "12,3k")
        idioma.definir("en")
        self.assertEqual(idioma.numero(1234567), "1.23M")
        self.assertEqual(idioma.decimal(76.34), "76.3")
        idioma.definir("pt")
        self.assertEqual(idioma.decimal(76.34), "76,3")


class TestAtualizar(unittest.TestCase):
    def test_numeros_da_versao(self):
        self.assertEqual(atualizar.numeros("v2026.10.17.4"), (2026, 10, 17, 4))
        self.assertGreater(atualizar.numeros("2026.10.17.10"), atualizar.numeros("2026.10.17.9"))
        self.assertEqual(atualizar.numeros("dev"), ())

    def test_so_baixa_do_proprio_repositorio(self):
        info = {"versao": "1.2", "instalador": "https://exemplo.com/x.exe", "sha256": "https://exemplo.com/x.sha256"}
        with self.assertRaises(ValueError):
            atualizar.baixar(info)

    def test_endereco_do_download_conferido_por_partes(self):
        base = f"https://github.com/{atualizar.REPO}/releases/download/v2026.10.17.5/"
        self.assertTrue(atualizar._do_repositorio(base + "NebulaOverlay-Setup.exe"))
        for ruim in (base.replace("https", "http") + "x.exe",
                     base + "../../../../outro/repo/releases/download/v1/x.exe",
                     base + "%2e%2e/x.exe",
                     base + "x.exe?redirect=https://exemplo.com",
                     f"https://github.com.exemplo.com/{atualizar.REPO}/releases/download/v1/x.exe",
                     f"https://github.com/{atualizar.REPO}-falso/releases/download/v1/x.exe"):
            self.assertFalse(atualizar._do_repositorio(ruim), ruim)


class TestPlaca(unittest.TestCase):
    """Com e sem acelerador: loopback no proxy local, senão a placa com o IP das conexões do jogo."""
    LISTA = [{"nome": "NPF_Loopback", "descricao": "Adapter for loopback traffic capture", "ips": ["127.0.0.1"]},
             {"nome": "NPF_{A}", "descricao": "Intel Ethernet", "ips": ["192.168.1.10"]},
             {"nome": "NPF_{B}", "descricao": "WireGuard Tunnel", "ips": ["10.6.0.2"]}]

    def test_acelerador_usa_o_loopback(self):
        import gravar
        self.assertIn("loopback", gravar.escolher_placa(self.LISTA, {"proxy": "ExitLag.exe", "porta": 51736})["descricao"])

    def test_direto_usa_a_placa_das_conexoes_do_jogo(self):
        import gravar
        rota = {"proxy": None, "conexoes": 2, "ips_locais": ["10.6.0.2"]}
        self.assertEqual(gravar.escolher_placa(self.LISTA, rota)["descricao"], "WireGuard Tunnel")

    def test_placa_forcada_pelo_nome(self):
        import gravar
        self.assertEqual(gravar.escolher_placa(self.LISTA, None, "intel")["descricao"], "Intel Ethernet")
        self.assertIsNone(gravar.escolher_placa(self.LISTA, None, "não existe"))


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
