"""Canal de atualização: estável (/releases/latest) ou beta (a mais nova de todas, pré-lançamentos incluídos)."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse import atualizar  # noqa: E402

REPO = atualizar.REPO


def publicacao(versao: str, beta: bool = False) -> dict:
    base = f"https://github.com/{REPO}/releases/download/v{versao}/"
    return {"tag_name": f"v{versao}", "prerelease": beta, "draft": False, "body": "notas",
            "assets": [{"name": "NebulaOverlay-Setup.exe", "browser_download_url": base + "NebulaOverlay-Setup.exe"},
                       {"name": "NebulaOverlay-Setup.exe.sha256", "browser_download_url": base + "NebulaOverlay-Setup.exe.sha256"}]}


ESTAVEL, BETA = publicacao("2026.10.21.34"), publicacao("2026.10.21.35", beta=True)


def resposta(req, timeout=0):
    url = req.full_url
    corpo = ESTAVEL if url.endswith("/releases/latest") else [BETA, ESTAVEL]
    return io.BytesIO(json.dumps(corpo).encode())


class TestCanal(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(atualizar, "VERSAO", "2026.10.21.33"),
                  mock.patch.object(atualizar.urllib.request, "urlopen", side_effect=resposta)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_estavel_nao_ve_o_beta(self):
        info = atualizar.mais_nova()
        self.assertEqual((info["versao"], info["beta"]), ("2026.10.21.34", False))

    def test_beta_pega_a_mais_nova_de_todas(self):
        info = atualizar.mais_nova(beta=True)
        self.assertEqual((info["versao"], info["beta"]), ("2026.10.21.35", True))

    def test_beta_ja_instalado_nao_volta_para_a_estavel_antiga(self):
        with mock.patch.object(atualizar, "VERSAO", "2026.10.21.35"):
            self.assertIsNone(atualizar.mais_nova())
            self.assertIsNone(atualizar.mais_nova(beta=True))


if __name__ == "__main__":
    unittest.main()
