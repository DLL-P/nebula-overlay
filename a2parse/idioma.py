"""Idiomas: um arquivo por idioma em idiomas/<código>.json (pt, en, es...).

Cada arquivo traz o nome do idioma, a voz do Windows que combina com ele, os textos da interface, os nomes de
classe e papel e as frases da voz. Idioma novo = arquivo novo (copie en.json); o app monta a lista sozinho.
Também vale pôr um arquivo em Documentos/Nebula Overlay/idiomas (por cima do que vem com o programa).

- t(chave, **valores): textos da interface. Chave que faltar no idioma sai em inglês (e depois em português).
- tr(texto): textos de alerta. O original é em português (mecanicas.json, dicas); a tradução vem da seção do
  idioma em mecanicas/traducoes.json. Texto sem tradução aparece em português.
"""

from __future__ import annotations

import glob
import json
import os

from .caminhos import app, usuario

RESERVA = ("en", "pt")          # de onde vem um texto que falta no idioma escolhido


def _carregar() -> dict[str, dict]:
    idiomas: dict[str, dict] = {}
    for pasta in (app("idiomas"), usuario("idiomas")):
        for caminho in sorted(glob.glob(os.path.join(pasta, "*.json"))):
            try:
                with open(caminho, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            cod = os.path.splitext(os.path.basename(caminho))[0]
            if cod in idiomas:                       # o do usuário completa/corrige o do programa
                for parte, valor in d.items():
                    if isinstance(valor, dict):
                        idiomas[cod].setdefault(parte, {}).update(valor)
            else:
                idiomas[cod] = d
    # ordem da engrenagem: "ordem" do arquivo (pt, en, es...) e depois o código
    return dict(sorted(idiomas.items(), key=lambda kv: ((kv[1].get("idioma") or {}).get("ordem", 99), kv[0])))


_IDIOMAS = _carregar()
IDIOMAS = {cod: (d.get("idioma") or {}).get("nome", cod) for cod, d in _IDIOMAS.items()}
_atual = ["pt" if "pt" in IDIOMAS else next(iter(IDIOMAS), "pt")]


def _parte(cod: str, parte: str) -> dict:
    return _IDIOMAS.get(cod, {}).get(parte, {})


def _meta(cod: str) -> dict:
    return _parte(cod, "idioma")


def detectar() -> str:
    """Idioma pelo formato regional do Windows (muita gente usa o Windows em inglês com região pt-BR ou es-XX);
    sem idioma para a região, vale o idioma da interface do Windows; sem nenhum dos dois, inglês."""
    def do_prefixo(nome: str) -> str | None:
        pre = (nome or "").split("-")[0].lower()
        return next((c for c in IDIOMAS if pre and (pre == c or pre in _meta(c).get("regioes", []))), None)
    try:
        import ctypes
        k = ctypes.windll.kernel32
        b = ctypes.create_unicode_buffer(85)
        if k.GetUserDefaultLocaleName(b, 85) and do_prefixo(b.value):
            return do_prefixo(b.value)
        if k.LCIDToLocaleName(k.GetUserDefaultUILanguage(), b, 85, 0) and do_prefixo(b.value):
            return do_prefixo(b.value)
    except Exception:
        pass
    return "en" if "en" in IDIOMAS else _atual[0]


def definir(cod: str | None) -> str:
    _atual[0] = cod if cod in IDIOMAS else detectar()
    return _atual[0]


def atual() -> str:
    return _atual[0]


def t(chave: str, **valores) -> str:
    for cod in (_atual[0], *RESERVA):
        texto = _parte(cod, "interface").get(chave)
        if texto:
            return texto.format(**valores) if valores else texto
    return chave


def nome_classe(chave: str | None) -> str:
    for cod in (_atual[0], *RESERVA):
        nome = _parte(cod, "classes").get(chave or "")
        if nome:
            return nome
    return ""


def classes() -> dict[str, str]:
    """{chave da classe: nome no idioma atual}, na ordem do arquivo."""
    base = _parte("pt", "classes") or _parte("en", "classes")
    return {k: nome_classe(k) for k in base}


def nome_papel(papel: str | None) -> str:
    for cod in (_atual[0], *RESERVA):
        nome = _parte(cod, "papeis").get(papel or "")
        if nome:
            return nome
    return papel or ""


# ---------------- voz ----------------

def voz_de(cod: str | None = None) -> str:
    """Voz do Windows que combina com o idioma (ex.: "pt-BR")."""
    return _meta(cod or _atual[0]).get("voz") or "en-US"


def vozes() -> list[tuple[str, str]]:
    """[(código da voz, nome para mostrar)] de todos os idiomas com frases de voz."""
    return [(m["voz"], m.get("nome_voz") or IDIOMAS[c]) for c in IDIOMAS
            if (m := _meta(c)).get("voz") and _parte(c, "voz")]


def frases(voz: str) -> dict[str, str]:
    """Frases da voz (chave do áudio → texto falado) do idioma dessa voz. Frase que faltar não é gravada
    (a voz de um idioma lendo texto de outro soa errado): aquele alerta toca bipe."""
    cod = next((c for c in IDIOMAS if _meta(c).get("voz") == voz), None)
    if cod is None:
        cod = next((c for c in IDIOMAS if voz.split("-")[0].lower() == c), "pt")
    return dict(_parte(cod, "voz"))


# ---------------- textos de alerta ----------------

_cache: dict[str, dict[str, str]] = {}


def _traducoes(cod: str) -> dict[str, str]:
    if cod not in _cache:
        tabela: dict[str, str] = {}
        # as do programa e, por cima, as suas (Documentos/Nebula Overlay/mecanicas/traducoes.json)
        for caminho in (app("mecanicas", "traducoes.json"), usuario("mecanicas", "traducoes.json")):
            try:
                with open(caminho, encoding="utf-8") as f:
                    tabela.update(json.load(f).get(cod, {}))
            except (OSError, ValueError):
                pass
        _cache[cod] = tabela
    return _cache[cod]


def tr(texto: str | None) -> str:
    """Texto de alerta no idioma atual."""
    if not texto or _atual[0] == "pt":
        return texto or ""
    tabela = _traducoes(_atual[0])
    if texto in tabela:
        return tabela[texto]
    prefixo = _parte("pt", "interface").get("em_breve", "EM BREVE: ")
    if texto.startswith(prefixo):
        return t("em_breve") + tr(texto[len(prefixo):])
    return texto


def numero(v: float) -> str:
    """12345 → 12,3k · 1234567 → 1,23M (vírgula decimal conforme o idioma)."""
    if v >= 1e6:
        s = f"{v / 1e6:.2f}M"
    elif v >= 1e3:
        s = f"{v / 1e3:.1f}k"
    else:
        return f"{v:.0f}"
    return s.replace(".", ",") if _meta(_atual[0]).get("virgula_decimal") else s


def decimal(v: float, casas: int = 1) -> str:
    """1.25 → "1,3" em português, "1.3" em inglês."""
    s = f"{v:.{casas}f}"
    return s.replace(".", ",") if _meta(_atual[0]).get("virgula_decimal") else s
