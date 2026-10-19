"""'Tudo funcionando?': confere o que costuma impedir o app de funcionar e diz o que fazer.

`verificar(estado)` recebe um retrato do app (montado pelo overlay) e devolve as linhas da aba, cada uma com o
nível, o texto e, quando há conserto, a ação do botão. `texto(...)` monta o diagnóstico para copiar: sem nomes
de personagem, sem IPs e sem caminhos com o nome do usuário.
"""

from __future__ import annotations

import platform

from .idioma import t

OK, AVISO, ERRO, INFO = "ok", "aviso", "erro", "info"
RELOGIO_MAX = 60.0       # s de diferença entre o relógio do PC e o do servidor que já atrapalha os eventos
SEM_MENSAGEM = 60.0      # s conectado sem nenhuma mensagem do jogo, com o jogo aberto


def verificar(e: dict) -> list[dict]:
    """e: npcap, npcap_versao, npcap_so_admin, admin, loopback, jogo_aberto, janela, tela_exclusiva, conectado, proxy,
    sem_mensagem_s, latencia, relogio_s, erro, nova_versao. Devolve [{"nivel", "texto", "acao"}]."""
    linhas: list[dict] = []

    def linha(nivel, chave, acao=None, **v):
        linhas.append({"nivel": nivel, "texto": t(chave, **v), "acao": acao})

    # captura
    if e.get("npcap"):
        if e.get("npcap_so_admin") and not e.get("admin"):
            linha(ERRO, "dg_npcap_so_admin", "admin")
        else:
            linha(OK, "dg_npcap_ok", versao=e.get("npcap_versao") or "?")
    elif e.get("admin"):
        linha(AVISO, "dg_sem_npcap_admin", "npcap")
    else:
        linha(ERRO, "dg_sem_npcap", "admin")
    if e.get("proxy"):
        if e.get("npcap") and e.get("loopback") is False:
            linha(ERRO, "dg_sem_loopback", "npcap", proxy=e["proxy"])
        else:
            linha(OK, "dg_proxy", proxy=e["proxy"])

    # jogo
    if not e.get("jogo_aberto"):
        linha(INFO, "dg_sem_jogo")
    else:
        if e.get("janela") == "min":
            linha(INFO, "dg_jogo_min")
        elif e.get("tela_exclusiva"):           # janela sem bordas ocupa a tela toda e funciona: só a exclusiva atrapalha
            linha(AVISO, "dg_tela_cheia")
        else:
            linha(OK, "dg_jogo_ok")
        if e.get("erro"):
            linha(ERRO, "dg_erro_captura", "tentar", erro=e["erro"])
        elif not e.get("conectado"):
            linha(INFO, "dg_procurando")
        elif (e.get("sem_mensagem_s") or 0) > SEM_MENSAGEM:
            linha(ERRO, "dg_sem_mensagem", "tentar", s=int(e["sem_mensagem_s"]))
        else:
            linha(OK, "dg_recebendo")

    # conexão e relógio
    lat = e.get("latencia")
    if lat:
        nivel = {"bom": OK, "medio": AVISO}.get(lat["nivel"], ERRO)
        linha(nivel, "dg_parado" if lat["tipo"] == "parado" else "dg_ping", ms=lat["ms"])
    rel = e.get("relogio_s")
    if rel is not None:
        if abs(rel) > RELOGIO_MAX:
            linha(ERRO, "dg_relogio_errado", "relogio", s=int(abs(rel)),
                  lado=t("dg_adiantado" if rel > 0 else "dg_atrasado"))
        else:
            linha(OK, "dg_relogio_ok")

    # versão
    if e.get("nova_versao"):
        linha(AVISO, "dg_nova_versao", "atualizar", v=e["nova_versao"])
    return linhas


def texto(e: dict, linhas: list[dict], versao: str, placas: list[str]) -> str:
    """Diagnóstico para colar numa conversa: o que foi conferido, a máquina e as placas de rede (só os nomes)."""
    marca = {OK: "[ok]", AVISO: "[!] ", ERRO: "[X] ", INFO: "[i] "}
    partes = [f"Nebula Overlay {versao} - diagnostico",
              f"Windows {platform.release()} ({platform.version()}), {platform.machine()}",
              f"Administrador: {'sim' if e.get('admin') else 'nao'} | Npcap: {e.get('npcap_versao') or 'nao'}"
              f" | so administrador: {e.get('npcap_so_admin')}",
              f"Rota: {e.get('proxy') or 'direto'} | conectado: {bool(e.get('conectado'))}"
              f" | sem mensagem do jogo ha: {e.get('sem_mensagem_s')}",
              f"Ping: {(e.get('latencia') or {}).get('ms')} | relogio do PC - servidor: {e.get('relogio_s')} s", ""]
    partes += [f"{marca[l['nivel']]} {l['texto']}" for l in linhas]
    if placas:
        partes += ["", "Placas de rede:"] + [f"  - {p}" for p in placas]
    return "\n".join(partes)
