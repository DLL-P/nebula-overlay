# Receita do PyInstaller: gera dist/NebulaOverlay/ (o app sem console, com os arquivos em _internal).
# Use empacotar/construir.py, que também gera o instalador.
# Só entra o que é do projeto: tabelas extraídas do jogo (npcs.json, skills*.json...) ficam de fora.
import os

RAIZ = os.path.dirname(SPECPATH)
p = lambda *x: os.path.join(RAIZ, *x)

dados = [
    (p("dados", "classes"), os.path.join("dados", "classes")),
    (p("dados", "dicas_classes.json"), "dados"),
    (p("dados", "icone.ico"), "dados"),
    (p("dados", "icone.png"), "dados"),
    (p("opcodes.json"), "."),
    (p("idiomas"), "idiomas"),
    (p("mecanicas", "mecanicas.json"), "mecanicas"),
    (p("mecanicas", "roteiros.json"), "mecanicas"),
    (p("mecanicas", "traducoes.json"), "mecanicas"),
    (p("mecanicas", "eventos.json"), "mecanicas"),
]

a = Analysis(
    [p("app.py")],
    pathex=[RAIZ],
    datas=dados,
    hiddenimports=["overlay", "painel", "roteiros", "relatorio", "voz", "mapear", "gravar"],
    excludes=["PIL", "numpy", "matplotlib", "pytest", "pydoc"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [("X utf8_mode=1", None, "OPTION")],
    exclude_binaries=True,
    name="NebulaOverlay",
    icon=p("dados", "icone.ico"),
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="NebulaOverlay")
