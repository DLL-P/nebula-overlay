"""Perfis do grupo (0x9702): classe, nível, GS e CP, com e sem o byte opcional depois do GS."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2parse.grupo import ler_perfis  # noqa: E402


def registro(pos, ident, servidor, nome, classe, nivel, gs, cp, extra=None):
    """Um jogador no formato do 0x9702 (nomes de teste; o resto como nas capturas de 2026-10-17)."""
    n = nome.encode("utf-8")
    return (bytes([0x1E, pos]) + struct.pack("<IHH", ident, 0, servidor) + bytes([len(n)]) + n
            + struct.pack("<III", classe, nivel, gs) + (bytes([extra]) if extra is not None else b"")
            + struct.pack("<HHB", servidor, 0x1133, 4) + struct.pack("<QQ", cp, 7) + b"\x01\x00")


CABECALHO = bytes.fromhex("b0 01 04 00 0c") + b"Leaving now." + bytes.fromhex("05 ff 27 09 00 01 03 a7 81 03 00 00 00 7e 05 ff 01 02 05")


class TestPerfis(unittest.TestCase):
    def test_lista_do_grupo(self):
        p = (CABECALHO + registro(1, 230311, 1406, "Heroi", 6, 45, 1955, 93878)
             + registro(2, 240100, 2401, "Fulana", 19, 45, 1605, 84121, extra=7)      # com o byte opcional
             + registro(3, 240200, 1402, "Beltrano", 29, 45, 1642, 69991) + b"\x00\x09")
        r = ler_perfis(p)
        self.assertEqual([x["nome"] for x in r], ["Heroi", "Fulana", "Beltrano"])
        self.assertEqual((r[0]["classe"], r[0]["nivel"], r[0]["gs"], r[0]["cp"]), ("GLADIATOR", 45, 1955, 93878))
        self.assertEqual((r[1]["classe"], r[1]["cp"]), ("ASSASSIN", 84121))
        self.assertEqual(r[2]["classe"], "CLERIC")

    def test_lixo_e_lista_vazia(self):
        self.assertEqual(ler_perfis(CABECALHO), [])
        self.assertEqual(ler_perfis(bytes(range(256))), [])
        quebrado = registro(1, 1, 1406, "Heroi", 6, 45, 1955, 93878)[:-20]       # cortado antes do CP
        self.assertEqual(ler_perfis(quebrado), [])


if __name__ == "__main__":
    unittest.main()
