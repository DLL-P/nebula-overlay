"""Fechar o app sozinho depois que o jogo fecha (qualidade de vida), sem nunca fechar no meio do jogo.

A regra olha só o processo AION2.exe, nunca o tráfego: parado na cidade por horas, carregando uma zona ou
desconectado, o processo continua aberto e o app não fecha. Só conta depois que o jogo foi visto aberto nesta
sessão (abrir o app antes do jogo não o fecha) e espera ESPERA s com o processo sumido o tempo todo: o jogo
travou e você reabriu, ou o launcher reiniciou o jogo para um patch, e a contagem zera. Com algo em andamento
(atualização baixando, ferramenta rodando, configurações abertas) a contagem também espera.
"""

from __future__ import annotations

ESPERA = 120.0      # s com o jogo fechado até o app fechar


class Fechamento:
    def __init__(self, espera: float = ESPERA) -> None:
        self.espera = espera
        self.jogo_visto = False
        self.sumiu_em: float | None = None
        self.mantido = False             # "Manter aberto": não fecha até o jogo abrir e fechar de novo

    def atualizar(self, jogo_aberto: bool, agora: float, ocupado: bool = False) -> float | None:
        """Chamado a cada segundo. Devolve None (nada a fazer), os segundos que faltam ou 0 (fechar agora)."""
        if jogo_aberto:
            self.jogo_visto, self.sumiu_em, self.mantido = True, None, False
            return None
        if not self.jogo_visto or self.mantido:
            return None
        if ocupado:
            self.sumiu_em = None         # recomeça a contar quando terminar
            return None
        if self.sumiu_em is None:
            self.sumiu_em = agora
        return max(0.0, self.espera - (agora - self.sumiu_em))

    def manter_aberto(self) -> None:
        self.mantido, self.sumiu_em = True, None
