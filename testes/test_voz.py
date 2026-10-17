"""Testes das palavras de ordem (voz.py)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import voz  # noqa: E402
from a2parse import idioma  # noqa: E402
from a2parse.alertas import MotorAlertas, boss, carregar_mecanicas  # noqa: E402

DADOS = carregar_mecanicas()


class TestPalavras(unittest.TestCase):
    def falas(self, nome, skill, alvo=1, **kw):
        m = MotorAlertas(boss(DADOS, nome), modo_skills=True, **kw)
        return [voz.FRASES.get(voz.chave_de(a)) for a in m.skill(1.0, skill, alvo)]

    def test_por_tipo_de_acao(self):
        self.assertEqual(self.falas("Judge Urahum", 1605110), ["Sai!"])
        self.assertEqual(self.falas("Divine Auldor", 1601000), ["Espalha!"])
        self.assertEqual(self.falas("Guardian Captain Raur", 1504450)[0], "Sai da zona!")

    def test_quando_e_com_voce(self):
        self.assertEqual(self.falas("Judge Urahum", 1605142, alvo=7, eu=7, papel="dps"), ["Em você! Sai!"])

    def test_frase_propria_da_mecanica(self):
        self.assertEqual(self.falas("Judge Urahum", 1605090), ["Defesa!"])
        self.assertEqual(self.falas("Divine Auldor", 1600925, papel="tank"), ["Vira ele!"])

    def test_aviso_info_nao_tem_fala(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, burst=False)
        self.assertIsNone(voz.chave_de(m.skill(1.0, 1601010, 1)[0]))      # FASE DO CÉU (info)

    def test_toda_chave_tem_frase(self):
        for chave in voz.POR_TIPO.values():
            self.assertIn(chave, voz.FRASES)

    def test_toda_voz_tem_as_mesmas_frases(self):
        for cod, frases in voz.FRASES_POR_IDIOMA.items():
            self.assertEqual(set(frases), set(voz.FRASES), cod)
        self.assertEqual(voz.frases_de("es")["sair"], "¡Sal!")
        self.assertEqual(voz.frases_de("en-US")["sair"], "Move out!")
        self.assertTrue(voz.pasta_de("en-US").endswith(os.path.join("voz", "en-US")))

    def test_sem_audios_nao_fica_pronta(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(voz.VozCurta(tmp).pronta)
            for k in ("sair", "empilhar", "um", "dois", "tres"):
                open(os.path.join(tmp, f"{k}.wav"), "wb").close()
            self.assertTrue(voz.VozCurta(tmp).pronta)



class TestVozesDoNebula(unittest.TestCase):
    def test_toda_frase_tem_audio_em_cada_idioma(self):
        """As vozes que vêm com o app (voz_padrao) cobrem todas as frases; frase nova pede rodar gerar_vozes.py."""
        for cod, _ in idioma.vozes():
            pasta = voz.pasta_padrao(cod)
            faltam = sorted(k for k in voz.frases_de(cod) if not os.path.exists(os.path.join(pasta, f"{k}.wav")))
            self.assertEqual(faltam, [], f"{cod}: rode empacotar/gerar_vozes.py")
            self.assertIsNotNone(voz.preparar(cod, avisar=lambda _m: None, fonte="nebula"))


if __name__ == "__main__":
    unittest.main()
