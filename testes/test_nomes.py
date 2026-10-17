"""Todo nome global usado dentro das funções existe no módulo (import esquecido derrubava o overlay inteiro:
o "tocar" que faltava no aviso de evento parava o laço da tela, o painel e a gravação)."""

import builtins
import dis
import importlib
import os
import sys
import types
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

MODULOS = ["overlay", "painel", "voz", "gravar", "roteiros", "relatorio", "app"] + [
    "a2parse." + os.path.splitext(f)[0] for f in sorted(os.listdir(os.path.join(RAIZ, "a2parse")))
    if f.endswith(".py") and f != "__init__.py"]


def globais_usados(codigo: types.CodeType):
    instrucoes = list(dis.get_instructions(codigo))
    locais = {i.argval for i in instrucoes if i.opname in ("STORE_NAME", "IMPORT_NAME")}    # corpo de classe
    for ins in instrucoes:
        if ins.opname == "LOAD_GLOBAL" or (ins.opname == "LOAD_NAME" and ins.argval not in locais):
            yield ins.argval, ins.positions.lineno if ins.positions else None
    for c in codigo.co_consts:
        if isinstance(c, types.CodeType):
            yield from globais_usados(c)


class TestNomes(unittest.TestCase):
    def test_nenhum_nome_global_faltando(self):
        faltam = []
        for nome in MODULOS:
            mod = importlib.import_module(nome)
            with open(mod.__file__, encoding="utf-8") as f:
                codigo = compile(f.read(), mod.__file__, "exec")
            for c in codigo.co_consts:                       # só o corpo das funções e classes
                if not isinstance(c, types.CodeType):
                    continue
                for n, linha in globais_usados(c):
                    if not hasattr(mod, n) and not hasattr(builtins, n):
                        faltam.append(f"{nome}.py:{linha} {n}")
        self.assertEqual(sorted(set(faltam)), [])


if __name__ == "__main__":
    unittest.main()
