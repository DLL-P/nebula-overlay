"""Idiomas da interface: português (pt), inglês (en) e espanhol (es).

- t(chave, **valores): textos fixos da interface (janelas, rodapé, botões).
- tr(texto): textos de alerta. O original é em português (mecanicas.json, dicas); a tradução vem de
  mecanicas/traducoes.json. Texto sem tradução aparece em português.
"""

from __future__ import annotations

import json

from .caminhos import app, usuario

IDIOMAS = {"pt": "Português", "en": "English", "es": "Español"}
_atual = ["pt"]


def detectar() -> str:
    """Idioma pelo formato regional do Windows (muita gente usa o Windows em inglês com região pt-BR ou es-XX);
    sem região portuguesa ou espanhola, vale o idioma da interface. O resto fica em inglês."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        b = ctypes.create_unicode_buffer(85)
        if k.GetUserDefaultLocaleName(b, 85) and b.value[:2] in ("pt", "es"):
            return b.value[:2]
        return {0x16: "pt", 0x0A: "es"}.get(k.GetUserDefaultUILanguage() & 0x3FF, "en")
    except Exception:
        return "pt"


def definir(cod: str | None) -> str:
    _atual[0] = cod if cod in IDIOMAS else detectar()
    return _atual[0]


def atual() -> str:
    return _atual[0]


UI: dict[str, tuple[str, str, str]] = {
    # overlay
    "em_s": ("EM {s}s · {texto}", "IN {s}s · {texto}", "EN {s}s · {texto}"),
    "previsto": ("previsto", "predicted", "previsto"),
    "atord": ("atord. {p}%", "stagger {p}%", "aturd. {p}%"),
    "agora": ("agora", "now", "ahora"),
    "ultima": (" · última", " · last", " · última"),
    "aguardando_boss": ("aguardando luta de boss", "waiting for a boss fight", "esperando pelea de jefe"),
    "aguardando_golpe": ("aguardando o 1º golpe", "waiting for the first hit", "esperando el primer golpe"),
    "eu": ("EU", "YOU", "YO"),
    "voce": ("VOCÊ", "YOU", "TÚ"),
    "jogador": ("jogador", "player", "jugador"),
    "procurando": ("procurando o jogo…", "looking for the game…", "buscando el juego…"),
    "arraste": ("{nome}: arraste · clique no cadeado para travar", "{nome}: drag · click the padlock to lock",
                "{nome}: arrastra · clic en el candado para fijar"),
    "janela_alertas": ("alertas", "alerts", "alertas"),
    "janela_meter": ("painel", "panel", "panel"),
    "via": ("via {proxy}", "via {proxy}", "vía {proxy}"),
    "direto": ("direto", "direct", "directo"),
    "repeticao": ("repetição {v}×", "replay {v}×", "repetición {v}×"),
    "demo": ("demonstração", "demo", "demostración"),
    "em_breve": ("EM BREVE: ", "SOON: ", "PRONTO: "),
    # janela principal
    "esperando": ("Esperando o Aion 2…", "Waiting for Aion 2…", "Esperando Aion 2…"),
    "conectado": ("Conectado · {rotulo}", "Connected · {rotulo}", "Conectado · {rotulo}"),
    "testando": ("Teste · {rotulo}", "Test · {rotulo}", "Prueba · {rotulo}"),
    "dica_alt": ("No jogo, segure Alt para clicar no cadeado e na engrenagem.",
                 "In game, hold Alt to click the padlock and the gear.",
                 "En el juego, mantén Alt para hacer clic en el candado y el engranaje."),
    "dica_janela": ("Use o jogo em janela ou janela sem bordas (tela cheia esconde o overlay).",
                    "Play in windowed or borderless mode (fullscreen hides the overlay).",
                    "Juega en ventana o ventana sin bordes (pantalla completa oculta el overlay)."),
    "btn_config": ("Configurações", "Settings", "Configuración"),
    "btn_pasta": ("Abrir pasta", "Open folder", "Abrir carpeta"),
    "btn_sair": ("Sair", "Quit", "Salir"),
    "nova_versao": ("Nova versão {v} disponível", "New version {v} available", "Nueva versión {v} disponible"),
    "btn_atualizar": ("Atualizar agora", "Update now", "Actualizar ahora"),
    "baixando": ("Baixando a atualização…", "Downloading the update…", "Descargando la actualización…"),
    "instalando": ("Instalando: o Nebula Overlay volta sozinho.", "Installing: Nebula Overlay will restart by itself.",
                   "Instalando: Nebula Overlay se reiniciará solo."),
    "erro_npcap": ("O Npcap não está instalado. Ele é necessário para ler a conexão do jogo.",
                   "Npcap is not installed. It is needed to read the game connection.",
                   "Npcap no está instalado. Es necesario para leer la conexión del juego."),
    "erro_loopback": ("O jogo passa pelo {proxy}, mas o Npcap foi instalado sem \"Support loopback traffic\". "
                      "Reinstale o Npcap marcando essa opção.",
                      "The game goes through {proxy}, but Npcap was installed without \"Support loopback traffic\". "
                      "Reinstall Npcap with that option checked.",
                      "El juego pasa por {proxy}, pero Npcap se instaló sin \"Support loopback traffic\". "
                      "Reinstala Npcap marcando esa opción."),
    "erro_placa": ("Não consegui escolher a placa de rede do jogo.", "Couldn't pick the game's network adapter.",
                   "No pude elegir el adaptador de red del juego."),
    "erro_abrir": ("Não consegui abrir a placa de rede: {erro}", "Couldn't open the network adapter: {erro}",
                   "No pude abrir el adaptador de red: {erro}"),
    "btn_npcap": ("Baixar o Npcap", "Download Npcap", "Descargar Npcap"),
    "btn_tentar": ("Tentar de novo", "Try again", "Reintentar"),
    # configurações
    "cfg_titulo": ("Nebula Overlay · configurações", "Nebula Overlay · settings", "Nebula Overlay · configuración"),
    "aba_geral": ("Geral", "General", "General"),
    "aba_alertas": ("Alertas", "Alerts", "Alertas"),
    "aba_ferramentas": ("Ferramentas", "Tools", "Herramientas"),
    "aba_sobre": ("Sobre", "About", "Acerca de"),
    "idioma": ("Idioma", "Language", "Idioma"),
    "voz_alertas": ("Voz dos alertas", "Alert voice", "Voz de las alertas"),
    "so_bipes": ("Só bipes", "Beeps only", "Solo pitidos"),
    "sem_som": ("Sem som", "No sound", "Sin sonido"),
    "testar": ("Testar", "Test", "Probar"),
    "aplicando": ("aplicando…", "applying…", "aplicando…"),
    "voz_pronta": ("voz pronta", "voice ready", "voz lista"),
    "sem_voz": ("sem voz {idioma} no Windows: ficou nos bipes. Instale em Configurações do Windows → Hora e idioma → Fala.",
                "no {idioma} voice in Windows: using beeps. Install it in Windows Settings → Time & language → Speech.",
                "sin voz {idioma} en Windows: se usan pitidos. Instálala en Configuración de Windows → Hora e idioma → Voz."),
    "tamanho": ("Tamanho", "Size", "Tamaño"),
    "mostrar": ("Mostrar", "Show", "Mostrar"),
    "painel_dano": ("Painel do boss e do grupo", "Boss and party panel", "Panel del jefe y del grupo"),
    "borda": ("Borda vermelha nos alarmes", "Red edge on alarms", "Borde rojo en las alarmas"),
    "reiniciar_aviso": ("Tamanho e painéis valem ao reiniciar.", "Size and panels apply after a restart.",
                        "El tamaño y los paneles se aplican al reiniciar."),
    "reiniciar": ("Reiniciar agora", "Restart now", "Reiniciar ahora"),
    "centro": ("Aviso antecipado no centro", "Early warning in the center", "Aviso anticipado en el centro"),
    "s_antes": ("{s} s antes", "{s} s before", "{s} s antes"),
    "desligado": ("Desligado", "Off", "Apagado"),
    "classe": ("Classe", "Class", "Clase"),
    "papel": ("Papel", "Role", "Rol"),
    "automatico": ("Automático", "Automatic", "Automático"),
    "automatica_c": ("Automática ({c})", "Automatic ({c})", "Automática ({c})"),
    "dicas": ("Dica da sua classe nos alertas", "Your class tip on alerts", "Consejo de tu clase en las alertas"),
    "burst_op": ("Avisos de segurar e soltar burst", "Hold and release burst warnings", "Avisos de guardar y soltar burst"),
    "gravar": ("Gravar as masmorras (para aprender os roteiros)", "Record dungeons (to learn boss timelines)",
               "Grabar las mazmorras (para aprender las rutinas)"),
    "vale_proximo": ("Classe, papel e burst valem a partir do próximo boss.", "Class, role and burst apply from the next boss.",
                     "Clase, rol y burst se aplican desde el próximo jefe."),
    "aprender": ("Aprender roteiros com as minhas capturas", "Learn boss timelines from my captures",
                 "Aprender rutinas con mis capturas"),
    "relatorio": ("Relatório da última run", "Last run report", "Informe de la última run"),
    "abrir_pasta": ("Abrir a pasta do Nebula Overlay", "Open the Nebula Overlay folder", "Abrir la carpeta de Nebula Overlay"),
    "contribuir": ("Contribuir com o projeto", "Contribute to the project", "Contribuir al proyecto"),
    "rodando": ("Rodando… pode levar alguns minutos.", "Running… this can take a few minutes.",
                "Ejecutando… puede tardar unos minutos."),
    "pronto": ("Pronto.", "Done.", "Listo."),
    "versao": ("Versão {v}", "Version {v}", "Versión {v}"),
    "atualizar_auto": ("Atualizar sozinho quando sair versão nova", "Update automatically when a new version comes out",
                       "Actualizar solo cuando salga una versión nueva"),
    "procurar": ("Procurar atualização", "Check for updates", "Buscar actualización"),
    "em_dia": ("Você está na versão mais nova.", "You're on the latest version.", "Tienes la versión más reciente."),
    "sem_internet": ("Não consegui ver as atualizações: {erro}", "Couldn't check for updates: {erro}",
                     "No pude buscar actualizaciones: {erro}"),
    "versao_dev": ("Versão de desenvolvimento: atualizações desligadas.", "Development build: updates are off.",
                   "Versión de desarrollo: actualizaciones desactivadas."),
    "aviso_legal": ("Projeto de fã, gratuito e não oficial, sem vínculo com a NCSOFT. Aion 2 e os símbolos das classes "
                    "pertencem à NCSOFT. O Nebula Overlay só lê o tráfego de rede que já chega ao seu PC e não mexe no jogo; "
                    "mesmo assim, os termos do jogo proíbem programas de terceiros: use por sua conta e risco.",
                    "Free, unofficial fan project, not affiliated with NCSOFT. Aion 2 and the class symbols belong to NCSOFT. "
                    "Nebula Overlay only reads the network traffic that already reaches your PC and does not touch the game; "
                    "even so, the game's terms forbid third-party programs: use at your own risk.",
                    "Proyecto de fans, gratuito y no oficial, sin vínculo con NCSOFT. Aion 2 y los símbolos de las clases "
                    "pertenecen a NCSOFT. Nebula Overlay solo lee el tráfico de red que ya llega a tu PC y no toca el juego; "
                    "aun así, los términos del juego prohíben programas de terceros: úsalo bajo tu propio riesgo."),
    "apoiar": ("Apoiar o desenvolvedor", "Support the developer", "Apoyar al desarrollador"),
    "fechar": ("Fechar", "Close", "Cerrar"),
    "sair_app": ("Fechar o Nebula Overlay", "Quit Nebula Overlay", "Cerrar Nebula Overlay"),
    "erro_inesperado": ("Erro inesperado. Os detalhes ficaram em {arquivo}.", "Unexpected error. Details saved to {arquivo}.",
                        "Error inesperado. Los detalles quedaron en {arquivo}."),
}

CLASSES = {
    "pt": {"GLADIATOR": "Gladiador", "TEMPLAR": "Templário", "ASSASSIN": "Assassino", "RANGER": "Arqueiro",
           "SORCERER": "Mago", "ELEMENTALIST": "Espiritualista", "CLERIC": "Clérigo", "CHANTER": "Encantador",
           "FIGHTER": "Lutador"},
    "en": {"GLADIATOR": "Gladiator", "TEMPLAR": "Templar", "ASSASSIN": "Assassin", "RANGER": "Ranger",
           "SORCERER": "Sorcerer", "ELEMENTALIST": "Elementalist", "CLERIC": "Cleric", "CHANTER": "Chanter",
           "FIGHTER": "Brawler"},
    "es": {"GLADIATOR": "Gladiador", "TEMPLAR": "Templario", "ASSASSIN": "Asesino", "RANGER": "Arquero",
           "SORCERER": "Hechicero", "ELEMENTALIST": "Elementalista", "CLERIC": "Clérigo", "CHANTER": "Cantor",
           "FIGHTER": "Luchador"},
}
PAPEIS = {
    "pt": {"tank": "tank", "healer": "healer", "dps": "dps", "suporte": "suporte"},
    "en": {"tank": "tank", "healer": "healer", "dps": "dps", "suporte": "support"},
    "es": {"tank": "tanque", "healer": "sanador", "dps": "dps", "suporte": "soporte"},
}
_POS = {"pt": 0, "en": 1, "es": 2}


def t(chave: str, **valores) -> str:
    textos = UI.get(chave)
    if not textos:
        return chave
    texto = textos[_POS[_atual[0]]]
    return texto.format(**valores) if valores else texto


def nome_classe(chave: str | None) -> str:
    return CLASSES[_atual[0]].get(chave or "", "")


def nome_papel(papel: str | None) -> str:
    return PAPEIS[_atual[0]].get(papel or "", papel or "")


_cache: dict[str, dict[str, str]] = {}


def _traducoes(cod: str) -> dict[str, str]:
    if cod not in _cache:
        tabela: dict[str, str] = {}
        # as do programa e, por cima, as suas (Documentos\Nebula Overlay\mecanicas\traducoes.json)
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
    prefixo = UI["em_breve"][0]
    if texto.startswith(prefixo):
        return t("em_breve") + tr(texto[len(prefixo):])
    return texto


def numero(v: float) -> str:
    """12345 → 12,3k · 1234567 → 1,23M (vírgula em português e espanhol, ponto em inglês)."""
    if v >= 1e6:
        s = f"{v / 1e6:.2f}M"
    elif v >= 1e3:
        s = f"{v / 1e3:.1f}k"
    else:
        return f"{v:.0f}"
    return s if _atual[0] == "en" else s.replace(".", ",")
