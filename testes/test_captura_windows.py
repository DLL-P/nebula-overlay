"""Captura sem Npcap: o filtro do socket do Windows e a troca Npcap → Windows na FonteAoVivo."""
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gravar  # noqa: E402
from a2parse.captura import _decodificar  # noqa: E402


def pacote(origem: int, destino: int, proto: int = 6, dados: bytes = b"oi") -> bytes:
    tcp = struct.pack(">HHIIBBHHH", origem, destino, 1, 0, 5 << 4, 0x18, 1000, 0, 0) + dados
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 0, 0, 64, proto, 0, bytes([192, 168, 0, 2]), bytes([1, 2, 3, 4]))
    return ip + tcp


def captura(porta=None) -> gravar.CapturaWindows:
    c = gravar.CapturaWindows.__new__(gravar.CapturaWindows)       # sem abrir socket (pede administrador)
    c.porta = porta
    return c


class TestFiltro(unittest.TestCase):
    def test_direto_pega_o_jogo_e_deixa_a_web_de_fora(self):
        c = captura()
        self.assertTrue(c.aceita(pacote(52791, 13328)))
        self.assertFalse(c.aceita(pacote(52791, 443)))
        self.assertFalse(c.aceita(pacote(80, 52791)))
        self.assertFalse(c.aceita(pacote(52791, 13328, proto=17)))     # UDP
        self.assertFalse(c.aceita(b"\x60" + bytes(60)))                 # IPv6

    def test_com_acelerador_so_a_porta_do_proxy(self):
        c = captura(porta=65274)
        self.assertTrue(c.aceita(pacote(65275, 65274)))
        self.assertFalse(c.aceita(pacote(65275, 13328)))

    def test_o_leitor_de_captura_entende_o_ip_cru(self):
        seg = _decodificar(gravar.CapturaWindows.LINKTYPE, pacote(52791, 13328, dados=b"abc"), 1.0)
        self.assertEqual((seg.porta_origem, seg.porta_destino, seg.dados), (52791, 13328, b"abc"))


class TestTroca(unittest.TestCase):
    def setUp(self):
        import overlay
        self.overlay = overlay

    def test_sem_npcap_e_sem_admin_pede_admin(self):
        sem = gravar.ErroCaptura("erro_npcap", "sem wpcap")
        with mock.patch.object(gravar, "carregar_wpcap", side_effect=sem), \
                mock.patch.object(gravar, "sou_admin", return_value=False):
            with self.assertRaises(gravar.ErroCaptura) as e:
                self.overlay.FonteAoVivo(salvar=False, rota={"proxy": None, "conexoes": 1, "ips_locais": ["192.168.0.2"]})
        self.assertEqual(e.exception.chave, "erro_npcap_admin")

    def test_sem_npcap_e_com_admin_captura_pelo_windows(self):
        sem = gravar.ErroCaptura("erro_npcap", "sem wpcap")
        aberta = mock.MagicMock()
        aberta.ler.return_value = None
        with mock.patch.object(gravar, "carregar_wpcap", side_effect=sem), \
                mock.patch.object(gravar, "sou_admin", return_value=True), \
                mock.patch.object(gravar, "CapturaWindows", return_value=aberta) as cw:
            cw.LINKTYPE = 101
            f = self.overlay.FonteAoVivo(salvar=False, rota={"proxy": "ExitLag.exe", "porta": 65274, "conexoes": 1})
            f.parar()
        cw.assert_called_once_with("127.0.0.1", 65274)
        self.assertEqual(f.linktype, 101)
        self.assertIn("ExitLag", f.rotulo)


if __name__ == "__main__":
    unittest.main()
