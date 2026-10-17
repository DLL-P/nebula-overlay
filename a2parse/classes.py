"""Classes do Aion 2: identificação e papel.

Duas fontes:
- o prefixo do ID da skill: skill_id // 1.000.000 (11 = Gladiador ... 19 = Lutador);
- o ID de classe que vem no 0x3633, logo depois do nome e do servidor (4 IDs seguidos por classe).
"""

from __future__ import annotations

from collections import Counter

POR_PREFIXO = {11: "GLADIATOR", 12: "TEMPLAR", 13: "ASSASSIN", 14: "RANGER", 15: "SORCERER",
               16: "ELEMENTALIST", 17: "CLERIC", 18: "CHANTER", 19: "FIGHTER"}

NOME = {"GLADIATOR": "Gladiador", "TEMPLAR": "Templário", "ASSASSIN": "Assassino", "RANGER": "Arqueiro",
        "SORCERER": "Mago", "ELEMENTALIST": "Espiritualista", "CLERIC": "Clérigo", "CHANTER": "Encantador",
        "FIGHTER": "Lutador"}

# papel padrão em masmorra; dá para trocar com --papel no overlay
PAPEL = {"GLADIATOR": "dps", "TEMPLAR": "tank", "ASSASSIN": "dps", "RANGER": "dps", "SORCERER": "dps",
         "ELEMENTALIST": "dps", "CLERIC": "healer", "CHANTER": "suporte", "FIGHTER": "dps"}

# corpo a corpo ("perto") ou à distância ("longe"): passos com "so_perto" (ex.: ENGAJE) não aparecem para "longe"
ALCANCE = {"GLADIATOR": "perto", "TEMPLAR": "perto", "ASSASSIN": "perto", "CHANTER": "perto", "FIGHTER": "perto",
           "RANGER": "longe", "SORCERER": "longe", "ELEMENTALIST": "longe", "CLERIC": "longe"}

# ID de classe do 0x3633: primeiro ID de cada faixa de 4
_FAIXAS = {5: "GLADIATOR", 9: "TEMPLAR", 13: "RANGER", 17: "ASSASSIN", 21: "ELEMENTALIST", 25: "SORCERER",
           29: "CLERIC", 33: "CHANTER", 45: "FIGHTER"}
PC_CLASSES = {inicio + k: classe for inicio, classe in _FAIXAS.items() for k in range(4)}


def classe_da_skill(skill_id: int) -> str | None:
    if skill_id > 99_999_999:          # mesma normalização do meter para IDs longos
        skill_id = (skill_id >> 1) // 50
    if skill_id < 10_000_000:
        return None
    return POR_PREFIXO.get(skill_id // 1_000_000)


def classe_do_pc(pc_id: int) -> str | None:
    return PC_CLASSES.get(pc_id) or None


class DetectorClasse:
    """Sua classe: o 0x3633 dá a resposta logo na entrada da zona; os seus casts confirmam."""

    def __init__(self) -> None:
        self.votos: Counter = Counter()
        self.do_pacote: str | None = None

    def reset(self) -> None:
        self.votos.clear()
        self.do_pacote = None

    def skill(self, skill_id: int) -> None:
        c = classe_da_skill(skill_id)
        if c:
            self.votos[c] += 1

    @property
    def classe(self) -> str | None:
        if self.votos:
            c, n = self.votos.most_common(1)[0]
            if n >= 3 or not self.do_pacote:
                return c
        return self.do_pacote
