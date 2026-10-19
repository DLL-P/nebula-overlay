"""'Tudo funcionando?': cada problema comum vira uma linha com o conserto certo."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse import diagnostico, idioma  # noqa: E402

BOM = {"npcap": True, "npcap_versao": "Npcap version 1.89", "npcap_so_admin": False, "admin": False,
       "loopback": True, "jogo_aberto": True, "janela": (100, 50, 1600, 900), "tela": (2560, 1080),
       "conectado": True, "proxy": None, "sem_mensagem_s": 2, "latencia": {"ms": 70, "tipo": "ping", "nivel": "bom"},
       "relogio_s": 0.3, "erro": None, "nova_versao": None}


def _acoes(e: dict) -> dict:
    return {l["acao"]: l["nivel"] for l in diagnostico.verificar(e) if l["acao"]}


class TestDiagnostico(unittest.TestCase):
    def setUp(self):
        idioma.definir("pt")

    def test_tudo_certo_e_so_verde(self):
        self.assertEqual({l["nivel"] for l in diagnostico.verificar(BOM)}, {"ok"})

    def test_sem_npcap_sugere_administrador(self):
        self.assertEqual(_acoes({**BOM, "npcap": False}), {"admin": "erro"})
        self.assertEqual(_acoes({**BOM, "npcap": False, "admin": True}), {"npcap": "aviso"})

    def test_npcap_so_para_administrador(self):
        self.assertEqual(_acoes({**BOM, "npcap_so_admin": True}), {"admin": "erro"})
        self.assertEqual(_acoes({**BOM, "npcap_so_admin": True, "admin": True}), {})

    def test_acelerador_sem_loopback(self):
        self.assertEqual(_acoes({**BOM, "proxy": "ExitLag", "loopback": False}), {"npcap": "erro"})

    def test_conectado_sem_mensagem_do_jogo(self):
        linhas = diagnostico.verificar({**BOM, "sem_mensagem_s": 300})
        self.assertIn(("erro", "tentar"), [(l["nivel"], l["acao"]) for l in linhas])

    def test_tela_cheia_avisa(self):
        sem_bordas = {**BOM, "janela": (0, 0, 2560, 1080)}           # janela sem bordas funciona: não avisa
        self.assertEqual({l["nivel"] for l in diagnostico.verificar(sem_bordas)}, {"ok"})
        self.assertIn("aviso", [l["nivel"] for l in diagnostico.verificar({**BOM, "tela_exclusiva": True})])

    def test_relogio_errado(self):
        linhas = diagnostico.verificar({**BOM, "relogio_s": -300})
        l = next(l for l in linhas if l["acao"] == "relogio")
        self.assertEqual(l["nivel"], "erro")
        self.assertIn("300 s atrasado", l["texto"])

    def test_texto_para_copiar_sem_nome_nem_ip(self):
        linhas = diagnostico.verificar(BOM)
        txt = diagnostico.texto(BOM, linhas, "2026.10.19.28", ["Intel(R) Ethernet", "Adapter for loopback"])
        self.assertIn("2026.10.19.28", txt)
        self.assertIn("Intel(R) Ethernet", txt)
        self.assertNotRegex(txt.replace("2026.10.19.28", ""), r"\b(\d{1,3}\.){3}\d{1,3}\b")      # nenhum IP


if __name__ == "__main__":
    unittest.main()
