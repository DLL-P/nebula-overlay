"""Nebula Overlay: alertas de mecânica do Aion 2 por cima do jogo.

  python overlay.py                     abre o app (janela principal + camadas por cima do jogo)
  python overlay.py --mover             abre com o cadeado aberto (dá pra arrastar as janelas)
  python overlay.py --repetir capturas/X.pcap --a-partir 9:00
                                        reproduz uma captura gravada em tempo real (teste sem o jogo)
  python overlay.py --demo              mostra alertas de exemplo para ajustar posição e tamanho

Só lê o tráfego que já chega ao PC. As camadas são janelas do próprio programa
(transparentes, sempre por cima, com o mouse atravessando): nada é desenhado
dentro do jogo e nada é enviado a ele. Use o jogo em janela ou janela sem bordas;
em tela cheia exclusiva o Windows não deixa nenhuma janela aparecer por cima.

As opções ficam na engrenagem (salvas em overlay.json, na pasta do usuário); as de linha de
comando são para testes e têm prioridade.
"""

from __future__ import annotations

import argparse
import ctypes as C
import datetime as dt
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

from a2parse import idioma
from a2parse.alertas import Alerta, carregar_mecanicas
from a2parse.caminhos import INSTALADO, app, pasta_usuario, usuario
from a2parse.idioma import t, tr
from a2parse.roteiro import carregar as carregar_roteiros
from a2parse.aovivo import Sessao
from a2parse.classes import NOME as NOME_CLASSE
from a2parse.eventos import Eventos, nome as nome_evento
from a2parse.versao import VERSAO
from a2parse.captura import _decodificar, ler_segmentos
from a2parse.fontes import ler_tempo

CONFIG = usuario("overlay.json")
CHAVE = "#010101"                        # cor transparente das janelas
NIVEL = {"info": "#46d18a", "alerta": "#f2c53b", "alarme": "#ff4d4d"}
ACAO = {"azul": "#4aa3ff", "ambar": "#f2a93b", "vermelho": "#ff4d4d", "roxo": "#b36bff", "verde": "#46d18a", "cinza": "#b9b3c9"}
TEXTO = "#ece7f5"
DICA = "#e0b45a"                         # dica da sua classe
# meter: cor e sigla por classe
CLASSE_COR = {"GLADIATOR": "#d9873f", "TEMPLAR": "#5fa8d3", "ASSASSIN": "#b36bff", "RANGER": "#46d18a",
              "SORCERER": "#4a7cff", "ELEMENTALIST": "#e05fb0", "CLERIC": "#f0e2a0", "CHANTER": "#f2c53b",
              "FIGHTER": "#e0563b"}
CLASSE_SIGLA = {"GLADIATOR": "GLA", "TEMPLAR": "TEM", "ASSASSIN": "ASS", "RANGER": "ARQ", "SORCERER": "MAG",
                "ELEMENTALIST": "ESP", "CLERIC": "CLÉ", "CHANTER": "ENC", "FIGHTER": "LUT"}
MOVEIS = ("alertas", "meter", "eventos")
EVENTO = "#4fd1c5"                       # cor dos eventos de campo (como o cartão do Festival Shugo)
CARTAO, CARTAO_BORDA, CARTAO_LINHA = "#1a1c25", "#2c2f3d", "#242733"   # cartões no estilo do seu meter
VOCE = "#7b5cf0"                                                        # sua linha no meter
FONTE = "Segoe UI"


# ---------------- Windows ----------------

def dpi_nitido() -> None:
    try:
        C.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            C.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def atravessar(janela: tk.Misc, sim: bool = True) -> None:
    """Deixa o clique atravessar a janela e a tira da barra de tarefas e do Alt+Tab."""
    try:
        u = C.windll.user32
        hwnd = u.GetParent(janela.winfo_id()) or janela.winfo_id()
        GWL_EXSTYLE, LAYERED, TRANSP, TOOL, NOACT = -20, 0x80000, 0x20, 0x80, 0x8000000
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE) | LAYERED | TOOL | NOACT
        ex = ex | TRANSP if sim else ex & ~TRANSP
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    except Exception:
        pass


def por_cima(janela: tk.Misc) -> None:
    try:
        u = C.windll.user32
        hwnd = u.GetParent(janela.winfo_id()) or janela.winfo_id()
        u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)   # HWND_TOPMOST, NOSIZE|NOMOVE|NOACTIVATE
    except Exception:
        pass


def janela_do_jogo(pids: set[int]) -> tuple[int, int, int, int] | str | None:
    """Área útil (x, y, largura, altura) da janela do AION2 na tela; "min" se minimizada; None se não achou."""
    import ctypes.wintypes as W
    u = C.windll.user32
    achadas: list = []

    @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cada(h, _):
        pid = W.DWORD()
        u.GetWindowThreadProcessId(h, C.byref(pid))
        if pid.value in pids and u.IsWindowVisible(h):
            if u.IsIconic(h):
                achadas.append((0, "min"))
                return True
            r, p = W.RECT(), W.POINT(0, 0)
            u.GetClientRect(h, C.byref(r))
            u.ClientToScreen(h, C.byref(p))
            if r.right > 300 and r.bottom > 300:
                achadas.append((r.right * r.bottom, (p.x, p.y, r.right, r.bottom)))
        return True

    try:
        u.EnumWindows(cada, 0)
    except Exception:
        return None
    return max(achadas, key=lambda a: a[0])[1] if achadas else None


def processo_em_foco() -> int | None:
    """PID da janela em primeiro plano (a que recebe o teclado)."""
    import ctypes.wintypes as W
    try:
        u = C.windll.user32
        pid = W.DWORD()
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), C.byref(pid))
        return pid.value
    except Exception:
        return None


def pids_do_jogo() -> set[int]:
    try:
        import gravar
        return set(gravar.pids_de("AION2.exe"))
    except Exception:
        return set()


# ---------------- desenho ----------------

def ret_arredondado(cv: tk.Canvas, x0, y0, x1, y1, r, **kw):
    p = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(p, smooth=True, **kw)


def misturar(cor: str, fundo: str, quanto: float) -> str:
    """Mistura duas cores #rrggbb: quanto=1 é só a cor, 0 é só o fundo (o Tk não tem transparência por item)."""
    a = [int(cor[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(fundo[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * quanto + y * (1 - quanto)):02x}" for x, y in zip(a, b))


numero = idioma.numero


def icone(cv: tk.Canvas, tipo: str, cx: float, cy: float, s: float, cor: str) -> None:
    """Ícones vetoriais simples por ação (mesma ideia dos SVG da prévia)."""
    w = max(2, int(s / 9))
    L = lambda *p: cv.create_line(*[cx + a * s if i % 2 == 0 else cy + a * s for i, a in enumerate(p)], fill=cor, width=w, capstyle="round", joinstyle="round")
    O = lambda x, y, r, fill="": cv.create_oval(cx + (x - r) * s, cy + (y - r) * s, cx + (x + r) * s, cy + (y + r) * s, outline=cor, width=w, fill=fill)
    if tipo == "empilhar":
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            L(dx * .45, dy * .45, dx * .18, dy * .18)
            L(dx * .18, dy * .18, dx * .18, dy * .34)
            L(dx * .18, dy * .18, dx * .34, dy * .18)
        O(0, 0, .1, cor)
    elif tipo == "espalhar":
        O(0, 0, .08, cor)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            L(dx * .14, dy * .14, dx * .45, dy * .45)
            L(dx * .45, dy * .45, dx * .45, dy * .28)
            L(dx * .45, dy * .45, dx * .28, dy * .45)
    elif tipo == "pular":
        cv.create_oval(cx - .4 * s, cy + .22 * s, cx + .4 * s, cy + .42 * s, outline=cor, width=w)
        L(0, .25, 0, -.42)
        L(-.2, -.22, 0, -.42, .2, -.22)
    elif tipo in ("parar_dano", "enrage"):
        pts = []
        for k in range(8):
            a = math.pi / 8 + k * math.pi / 4
            pts += [cx + .44 * s * math.cos(a), cy + .44 * s * math.sin(a)]
        cv.create_polygon(pts, outline=cor, width=w, fill="")
        L(-.22, 0, .22, 0) if tipo == "parar_dano" else L(0, -.2, 0, .12)
    elif tipo == "sair":
        cv.create_oval(cx - .45 * s, cy - .25 * s, cx + .05 * s, cy + .25 * s, outline=cor, width=w, dash=(3, 3))
        L(-.1, 0, .45, 0)
        L(.3, -.15, .45, 0, .3, .15)
    elif tipo == "borda":
        O(0, 0, .42)
        O(0, 0, .06, cor)
        L(.08, 0, .32, 0)
        L(.22, -.1, .32, 0, .22, .1)
    elif tipo == "atras":
        cv.create_polygon(cx, cy - .42 * s, cx + .32 * s, cy - .02 * s, cx - .32 * s, cy - .02 * s, outline=cor, width=w, fill="")
        O(0, .3, .1, cor)
    elif tipo == "stagger":
        cv.create_polygon(cx + .08 * s, cy - .45 * s, cx - .25 * s, cy + .05 * s, cx - .02 * s, cy + .05 * s, cx - .1 * s, cy + .45 * s,
                          cx + .25 * s, cy - .08 * s, cx + .02 * s, cy - .08 * s, outline=cor, width=w, fill="")
    elif tipo == "matar_alvo":
        O(0, 0, .3)
        O(0, 0, .07, cor)
        for a, b, c, d in ((0, -.46, 0, -.18), (0, .18, 0, .46), (-.46, 0, -.18, 0), (.18, 0, .46, 0)):
            L(a, b, c, d)
    elif tipo == "esquivar":
        O(.25, 0, .12, cor)
        for y in (-.18, 0, .18):
            L(-.45, y, -.02, y)
    elif tipo == "esconder":
        cv.create_rectangle(cx + .08 * s, cy - .42 * s, cx + .3 * s, cy + .42 * s, outline=cor, width=w)
        O(-.22, -.18, .08)
        L(-.22, -.08, -.22, .2)
    elif tipo == "engajar":         # seta entrando no alvo
        O(.2, 0, .22)
        O(.2, 0, .05, cor)
        L(-.46, 0, -.06, 0)
        L(-.2, -.14, -.04, 0, -.2, .14)
    elif tipo == "burst":           # estrela de explosão
        pts = []
        for k in range(16):
            r = .46 if k % 2 == 0 else .2
            a = k * math.pi / 8
            pts += [cx + r * s * math.cos(a), cy + r * s * math.sin(a)]
        cv.create_polygon(pts, outline=cor, width=w, fill="")
    elif tipo == "segurar_burst":   # pausa: duas barras
        cv.create_rectangle(cx - .3 * s, cy - .36 * s, cx - .08 * s, cy + .36 * s, outline=cor, width=w)
        cv.create_rectangle(cx + .08 * s, cy - .36 * s, cx + .3 * s, cy + .36 * s, outline=cor, width=w)
    elif tipo == "debuff":          # gota
        cv.create_polygon(cx, cy - .44 * s, cx + .3 * s, cy + .08 * s, cx + .3 * s, cy + .2 * s, cx, cy + .42 * s,
                          cx - .3 * s, cy + .2 * s, cx - .3 * s, cy + .08 * s, outline=cor, width=w, fill="", smooth=True)
    else:  # atencao
        cv.create_polygon(cx, cy - .42 * s, cx + .44 * s, cy + .36 * s, cx - .44 * s, cy + .36 * s, outline=cor, width=w, fill="")
        L(0, -.14, 0, .1)
        O(0, .22, .03, cor)


class Overlay:
    def __init__(self, args) -> None:
        import painel
        self.args = args
        self.cfg = self._ler_cfg()
        idioma.definir(args.idioma or self.cfg.get("idioma"))
        self.escala = args.escala or self.cfg.get("escala", 1.0)
        self.dicas_on = not args.sem_dicas and self.cfg.get("dicas", True)
        self.ao_vivo = not (args.repetir or args.demo)
        self.eventos = Eventos()                 # sobrevive às reconexões (a sessão é refeita a cada uma)
        self._eventos_avisados: set = set()
        self.sessao = self._nova_sessao()
        self.cats = self.sessao.dados["categorias_alerta"]
        self.fonte = None
        self.erro_captura = None               # problema para abrir a captura (Npcap): fica na janela principal
        self._sem_jogo_desde: float | None = None
        self._procurando = False               # thread olhando a conexão do jogo
        self._rota: dict | None = None
        self._recarregar_roteiros = False
        self._info_atualizacao: dict | None = None
        self._atualizacao_vista = False
        self._download: tuple | None = None
        self.inicio = None
        self._config = None
        self.vistos: set = set()
        self._fontes: dict = {}
        self.voz = None
        self.modo_som = "bipes"
        dpi_nitido()
        self.root = tk.Tk()
        self.root.withdraw()
        self.sw, self.sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        # tudo fica ancorado na janela do jogo (em janela, ele não ocupa a tela toda)
        self.pids, self._pids_em = (pids_do_jogo() if self.ao_vivo else set()), time.monotonic()
        r = janela_do_jogo(self.pids) if self.pids else None
        self.base = r if isinstance(r, tuple) else (0, 0, self.sw, self.sh)
        self.escondido = False
        self._minimizado = False
        self._testando = not self.ao_vivo
        self._n_quadro = 0
        self._st: dict | None = None
        self.tam: dict[str, tuple[int, int]] = {}
        e = self.escala
        self.travado = not args.mover           # cadeado: travado = o clique atravessa; aberto = dá pra arrastar
        self.janelas: dict[str, tuple] = {}     # nome -> (janela, canvas)
        self.cadeados: list[tuple] = []         # (janela do cadeado, canvas, dona, canto, só quando aberto)
        self.t_cad = int(20 * e)                # tamanho do cadeado
        sem_meter = args.sem_meter or not self.cfg.get("meter", True)
        sem_borda = args.sem_borda or not self.cfg.get("borda", True)
        self.w_al, self.cv_al = self._janela("alertas", int(1100 * e), int(270 * e))
        self.w_pa, self.cv_pa = None, None            # o painel do boss mora no topo do meter
        self.w_me, self.cv_me = (None, None) if sem_meter else self._janela("meter", int(400 * e), int(420 * e))
        self.w_bo, self.cv_bo = (None, None) if sem_borda else self._janela("borda", self.sw, self.sh, fixo=True)
        self.w_ev, self.cv_ev = self._janela("eventos", int(300 * e), int(170 * e))
        # um cadeado em cada janela; qualquer um trava ou destrava todas
        if self.w_me:
            self._cadeado(self.w_me, canto="base")     # cadeado no rodapé do painel
            self._cadeado(self.w_me, canto="base", tipo="engrenagem")   # configurações, ao lado
        # o do alerta só aparece destravado: travado, ele ficaria solto em cima do personagem
        self._cadeado(self.w_al, so_aberto=bool(self.w_me or self.w_pa))
        self._cadeado(self.w_ev, so_aberto=True)
        self._reposicionar()
        self._aplicar_trava()
        self.root.report_callback_exception = self._erro
        self.inicio = painel.Inicio(self)
        if args.demo:
            self.fonte = FonteDemo()
        elif args.repetir:
            self.fonte = FonteRepeticao(args.repetir, ler_tempo(args.a_partir), args.velocidade)
        if self.fonte:
            self.inicio.status("testando", self.fonte.rotulo)
        # voz: grava os áudios que faltarem sem travar a janela (na 1ª vez leva alguns segundos)
        import voz as voz_curta
        modo = "mudo" if args.sem_som else (args.idioma_voz or self.cfg.get("voz")
                                             or voz_curta.VOZ_DO_IDIOMA.get(idioma.atual(), "pt-BR"))
        threading.Thread(target=self.aplicar_voz, args=(modo, False), daemon=True).start()
        self.root.after(50, self._quadro)
        self.root.after(500, self._vigiar_jogo)
        self.root.after(2000, self._reafirmar)
        if not atualizar_dev() and self.cfg.get("atualizar_auto", True):
            self.root.after(3000, lambda: self.procurar_atualizacao(mostrar=False, em_segundo_plano=True))

    def _nova_sessao(self) -> Sessao:
        a, c = self.args, self.cfg
        s = Sessao(carregar_mecanicas(), pre_aviso=not a.sem_pre_aviso,
                   burst=not a.sem_burst and c.get("burst", True),
                   papel_fixo=a.papel or c.get("papel"), classe_fixa=a.classe or c.get("classe"),
                   antecipar=a.antecipar, eventos=self.eventos)
        if "centro_antes" in c:
            s.centro_antes = float(c["centro_antes"])
        return s

    # ---------- conexão com o jogo ----------
    def _vigiar_jogo(self) -> None:
        """Uma vez por segundo: acha o jogo, conecta quando ele estiver online, desconecta quando ele fechar."""
        try:
            self._vigiar()
        finally:
            self.root.after(1000, self._vigiar_jogo)

    def _vigiar(self) -> None:
        self._acompanhar_atualizacao()
        if self._recarregar_roteiros:
            self._recarregar_roteiros = False
            self.sessao.roteiros = carregar_roteiros()
        if not self.ao_vivo:
            return
        pids = pids_do_jogo()
        self.pids = pids
        if self.fonte is not None:
            if pids:
                self._sem_jogo_desde = None
            else:
                self._sem_jogo_desde = self._sem_jogo_desde or time.monotonic()
                if time.monotonic() - self._sem_jogo_desde > 15:      # o jogo fechou
                    self.fonte.parar()
                    self.fonte = None
                    self.inicio.status("esperando")
            return
        if self.erro_captura is not None:
            return                                   # espera o "Tentar de novo"
        if not pids:
            self.inicio.status("esperando")
            return
        if self._rota is not None:
            rota, self._rota = self._rota, None
            if rota.get("conexoes"):
                self._conectar(rota)
                return
        if not self._procurando:                    # o netstat demora: olha a conexão do jogo numa thread
            self._procurando = True

            def olhar():
                import gravar
                try:
                    self._rota = gravar.rota_do_jogo() or {}
                finally:
                    self._procurando = False
            threading.Thread(target=olhar, daemon=True).start()

    def _conectar(self, rota: dict) -> None:
        from gravar import ErroCaptura
        try:
            fonte = FonteAoVivo(salvar=self.cfg.get("gravar", True) and not self.args.sem_salvar,
                                sempre=self.args.sempre_gravar, rota=rota)
        except ErroCaptura as e:
            self.erro_captura = e
            self.inicio.status("erro", erro=e)
            return
        self.sessao = self._nova_sessao()
        self.vistos.clear()
        self.fonte = fonte
        self.inicio.status("conectado", fonte.rotulo)
        try:
            self.inicio.j.iconify()                  # a janela principal sai da frente do jogo
        except tk.TclError:
            pass

    def tentar_de_novo(self) -> None:
        self.erro_captura = None
        self.inicio.status("esperando")

    # ---------- atualização ----------
    def procurar_atualizacao(self, mostrar: bool = True, em_segundo_plano: bool = False) -> str:
        """Olha no GitHub se há versão nova. Devolve uma mensagem para a aba Sobre."""
        from a2parse import atualizar

        def olhar():
            try:
                self._info_atualizacao = atualizar.mais_nova() or {}
                return ""
            except Exception as e:
                return t("sem_internet", erro=str(e)[:80])
        if em_segundo_plano:
            threading.Thread(target=olhar, daemon=True).start()
            return ""
        erro = olhar()
        self._atualizacao_vista = False
        self._acompanhar_atualizacao(automatica=False)
        if erro:
            return erro
        return t("nova_versao", v=self._info_atualizacao["versao"]) if self._info_atualizacao else t("em_dia")

    def _acompanhar_atualizacao(self, automatica: bool = True) -> None:
        info = self._info_atualizacao
        if info and not self._atualizacao_vista:
            self._atualizacao_vista = True
            self.inicio.nova_versao(info)
            # sozinho só fora do jogo: no meio da masmorra, fica o botão
            if automatica and self.cfg.get("atualizar_auto", True) and self.fonte is None and not self.pids:
                self.atualizar_agora()
        if self._download:
            tipo, valor = self._download
            if tipo == "progresso":
                self.inicio.baixando_atualizacao(f"{t('baixando')} {valor:.0%}")
            elif tipo == "pronto":
                self._download = None
                from a2parse import atualizar
                self.inicio.baixando_atualizacao(t("instalando"))
                atualizar.instalar(valor)
                self.root.after(1200, self.fechar)
            elif tipo == "erro":
                self._download = None
                self.inicio.baixando_atualizacao(t("sem_internet", erro=valor))

    def atualizar_agora(self) -> None:
        info = self._info_atualizacao
        if not info or self._download:
            return
        from a2parse import atualizar
        self._download = ("progresso", 0.0)

        def baixar():
            try:
                caminho = atualizar.baixar(info, lambda f: setattr(self, "_download", ("progresso", f)))
                self._download = ("pronto", caminho)
            except Exception as e:
                self._download = ("erro", str(e)[:80])
        threading.Thread(target=baixar, daemon=True).start()

    # ---------- ferramentas e reinício ----------
    def ferramenta(self, nome: str) -> None:
        import painel

        def rodar():
            import importlib
            importlib.import_module(nome).main([])
            if nome == "roteiros":
                self._recarregar_roteiros = True
        painel.Saida(self, t("aprender" if nome == "roteiros" else "relatorio"), rodar)

    def reiniciar(self) -> None:
        import subprocess
        cmd = [sys.executable] + ([] if INSTALADO else [os.path.abspath(sys.argv[0])]) + sys.argv[1:]
        self.fechar()
        subprocess.Popen(cmd)

    # ---------- janelas ----------
    def _ler_cfg(self) -> dict:
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _janela(self, nome: str, w: int, h: int, fixo: bool = False):
        self.tam[nome] = (w, h)
        j = tk.Toplevel(self.root)
        j.overrideredirect(True)
        j.geometry(f"{w}x{h}+0+0")
        j.attributes("-topmost", True)
        j.configure(bg=CHAVE)
        j.attributes("-transparentcolor", CHAVE)
        cv = tk.Canvas(j, width=w, height=h, bg=CHAVE, highlightthickness=0)
        cv.pack(fill="both", expand=True)
        j.update_idletasks()
        if fixo:
            atravessar(j, True)
        else:
            self._arrastavel(j, nome)
            self.janelas[nome] = (j, cv)
        return j, cv

    def _padrao(self, nome: str, w: int, h: int) -> tuple[int, int]:
        """Posições iniciais pensadas no seu layout: objetivos no alto à direita, chat embaixo à esquerda."""
        bx, by, bw, bh = self.base
        e = self.escala
        if nome == "alertas":       # centro, um pouco acima do personagem
            return bx + (bw - w) // 2, by + int(bh * 0.36 - h / 2)
        if nome == "painel":        # direita, abaixo da lista de objetivos
            return bx + bw - w - int(30 * e), by + int(bh * 0.42)
        if nome == "eventos":       # direita, abaixo do minimapa
            return bx + bw - w - int(24 * e), by + int(bh * 0.30)
        if nome == "meter":         # embaixo à esquerda, acima do chat
            return bx + int(20 * e), by + int(bh * 0.77) - h
        return bx, by

    def _reposicionar(self) -> None:
        bx, by, bw, bh = self.base
        rel = self.cfg.get("rel", {})
        for nome, (j, _cv) in self.janelas.items():
            w, h = self.tam[nome]
            x, y = (bx + rel[nome][0], by + rel[nome][1]) if nome in rel else self._padrao(nome, w, h)
            x = max(bx - w // 2, min(x, bx + bw - w // 2))       # nunca some inteira para fora do jogo
            y = max(by, min(y, by + bh - 30))
            j.geometry(f"{w}x{h}+{x}+{y}")
        if self.w_bo:
            self.w_bo.geometry(f"{bw}x{bh}+{bx}+{by}")
            self.cv_bo.config(width=bw, height=bh)
            self._criar_brilho()
        self._posicionar_cadeados()

    def _seguir_jogo(self) -> None:
        """Acompanha a janela do jogo: se ela mover ou mudar de tamanho, o overlay vai junto; minimizada, ele some."""
        r = janela_do_jogo(self.pids) if self.pids else None
        if r == "min" and self._testando:
            r = None                     # testando sem jogar: o overlay fica na tela mesmo com o jogo minimizado
        self._minimizado = r == "min"
        self._checar_foco()
        if isinstance(r, tuple) and r != self.base:
            self.base = r
            self._reposicionar()

    def _checar_foco(self) -> None:
        """Mostra o overlay só com o jogo em primeiro plano: no Alt+Tab ele some, e volta junto com o jogo.
        Clicar no cadeado não conta como trocar de janela (ele não rouba o foco)."""
        visivel = not self._minimizado
        if not (self._testando or self.args.sempre_visivel):
            # ao vivo, só com o jogo conectado e em primeiro plano (no Alt+Tab ele some)
            visivel = visivel and self.fonte is not None and bool(self.pids) and \
                processo_em_foco() in self.pids | {os.getpid()}
        if visivel == (not self.escondido):
            return
        todas = [j for j in (self.w_al, self.w_pa, self.w_me, self.w_bo, self.w_ev) if j] + [c[0] for c in self.cadeados]
        if not visivel:
            for j in todas:
                j.withdraw()
            self.escondido = True
            return
        for j in todas:
            j.deiconify()
        self.escondido = False
        self._aplicar_trava()            # ao reaparecer, o Windows esquece o "clique atravessa"
        if self.w_bo:
            atravessar(self.w_bo, True)

    # ---------- cadeado: trava e destrava as janelas ----------
    def _cadeado(self, dono: tk.Toplevel, canto: str = "topo", so_aberto: bool = False, tipo: str = "cadeado") -> None:
        """Botão pequeno sempre clicável no canto da janela. No jogo: segure Alt para soltar o mouse e clique."""
        t = self.t_cad
        j = tk.Toplevel(self.root)
        j.overrideredirect(True)
        j.attributes("-topmost", True)
        j.configure(bg=CHAVE)
        j.attributes("-transparentcolor", CHAVE)
        cv = tk.Canvas(j, width=t, height=t, bg=CHAVE, highlightthickness=0, cursor="hand2")
        cv.pack()
        j.update_idletasks()
        atravessar(j, False)                       # clicável, mas sem roubar o foco do jogo
        cv.bind("<Button-1>", lambda _e: self._alternar_trava() if tipo == "cadeado" else self.abrir_config())
        self.cadeados.append((j, cv, dono, canto, so_aberto, tipo))

    def _desenhar_cadeado(self, cv: tk.Canvas) -> None:
        cv.delete("all")
        t = int(cv.cget("width"))
        cor = "#e0b45a" if self.travado else "#46d18a"
        ret_arredondado(cv, 1, 1, t - 1, t - 1, t * .25, fill="#14111d", outline=cor, width=1)
        cv.create_rectangle(t * .28, t * .48, t * .72, t * .80, fill=cor, outline="")
        if self.travado:
            cv.create_arc(t * .34, t * .20, t * .66, t * .64, start=0, extent=180, style="arc", outline=cor, width=2)
        else:   # aberto: a alça sobe deslocada para o lado
            cv.create_arc(t * .46, t * .12, t * .78, t * .56, start=0, extent=180, style="arc", outline=cor, width=2)

    def _posicionar_cadeados(self) -> None:
        """Põe cada cadeado no canto da sua janela e na frente dela (clicar numa janela a traz para a frente)."""
        self.root.update_idletasks()
        t = self.t_cad
        for j, cv, dono, canto, so_aberto, tipo in self.cadeados:
            if so_aberto and self.travado:
                j.withdraw()
                continue
            if not self.escondido and j.state() == "withdrawn":
                j.deiconify()
                atravessar(j, False)
            y = dono.winfo_y() + 5 if canto == "topo" else dono.winfo_y() + self._altura_conteudo(dono) - t - 5
            x = dono.winfo_x() + dono.winfo_width() - t - 7 - (t + 5 if tipo == "engrenagem" else 0)
            j.geometry(f"{t}x{t}+{x}+{y}")
            (self._desenhar_engrenagem if tipo == "engrenagem" else self._desenhar_cadeado)(cv)
            por_cima(j)

    def _desenhar_engrenagem(self, cv: tk.Canvas) -> None:
        import math as _m
        cv.delete("all")
        t = int(cv.cget("width"))
        cor, c = "#b9b3c9", t / 2
        ret_arredondado(cv, 1, 1, t - 1, t - 1, t * .25, fill="#14111d", outline="#4a4560", width=1)
        for k in range(8):
            a = k * _m.pi / 4
            cv.create_line(c + t * .18 * _m.cos(a), c + t * .18 * _m.sin(a), c + t * .36 * _m.cos(a), c + t * .36 * _m.sin(a),
                           fill=cor, width=max(2, int(t / 8)))
        cv.create_oval(c - t * .22, c - t * .22, c + t * .22, c + t * .22, fill="#14111d", outline=cor, width=2)
        cv.create_oval(c - t * .07, c - t * .07, c + t * .07, c + t * .07, fill=cor, outline="")

    # ---------- configurações (engrenagem) ----------
    def aplicar_voz(self, modo: str, salvar: bool = True) -> str:
        """Troca a voz na hora (grava os áudios que faltarem). Devolve uma mensagem curta para a engrenagem."""
        import voz as voz_curta
        if modo in voz_curta.FRASES_POR_IDIOMA:
            v = voz_curta.preparar(modo, avisar=print)
            if v:
                self.voz, self.modo_som = v, modo
                msg = t("voz_pronta")
            else:
                self.voz, self.modo_som = None, "bipes"
                msg = t("sem_voz", idioma={"pt-BR": "Português", "en-US": "English", "es": "Español"}[modo])
        else:
            self.voz, self.modo_som = None, modo
            msg = ""
        if salvar:
            self.cfg["voz"] = modo if self.voz or modo in ("bipes", "mudo") else self.cfg.get("voz")
            self.salvar_cfg(forcar=True)
        return msg

    def testar_som(self) -> None:
        if self.voz:
            self.voz.falar("sair")
        elif self.modo_som == "bipes":
            tocar("alarme")

    def abrir_config(self, perto_do_meter: bool = True) -> None:
        """Janela normal (clicável e com foco): ao lado do painel quando aberta pela engrenagem."""
        import painel
        if self._config is not None and self._config.j.winfo_exists():
            self._config.j.deiconify()
            self._config.j.lift()
            return
        self._config = painel.Configuracoes(self, perto_do_meter)

    def _altura_conteudo(self, dono: tk.Toplevel) -> int:
        """O cartão do meter cresce com o número de jogadores: o cadeado acompanha o rodapé."""
        return getattr(self, "_alt_meter", dono.winfo_height()) if dono is self.w_me else dono.winfo_height()

    def _alternar_trava(self) -> None:
        self.travado = not self.travado
        self._aplicar_trava()
        if self.travado:
            self.salvar_cfg()

    def _aplicar_trava(self) -> None:
        """Travado: o clique atravessa. Aberto: fundo pontilhado e moldura para arrastar."""
        for nome, (j, cv) in self.janelas.items():
            cv.delete("moldura")
            if not self.travado:
                w, h = int(cv.cget("width")), int(cv.cget("height"))
                cv.create_rectangle(0, 0, w, h, fill="#e0b45a", outline="", stipple="gray25", tags="moldura")
                cv.create_rectangle(2, 2, w - 2, h - 2, outline="#e0b45a", dash=(6, 4), width=2, tags="moldura")
                cv.create_text(10, h - 10, text=t("arraste", nome=t("janela_" + nome)), anchor="w",
                               fill="#e0b45a", font=(FONTE, int(9 * self.escala), "bold"), tags="moldura")
                cv.tag_lower("moldura")
            atravessar(j, self.travado)
        self._posicionar_cadeados()

    def _arrastavel(self, j: tk.Toplevel, nome: str) -> None:
        estado = {}
        j.bind("<ButtonPress-1>", lambda e: estado.update(x=e.x, y=e.y))

        def mover(e):
            if self.travado or "x" not in estado:
                return
            nx, ny = j.winfo_x() + e.x - estado["x"], j.winfo_y() + e.y - estado["y"]
            j.geometry(f"+{nx}+{ny}")
            self.cfg.setdefault("rel", {})[nome] = [nx - self.base[0], ny - self.base[1]]   # relativa ao jogo
            self._posicionar_cadeados()
        j.bind("<B1-Motion>", mover)
        j.bind("<ButtonRelease-1>", lambda _e: self._posicionar_cadeados())   # o cadeado volta para a frente

    def salvar_cfg(self, forcar: bool = False) -> None:
        if self.cfg.get("rel") or forcar:
            self.cfg.setdefault("escala", self.escala)
            os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2, ensure_ascii=False)

    def _reafirmar(self) -> None:
        self._seguir_jogo()
        for j in (self.w_al, self.w_pa, self.w_me, self.w_bo, self.w_ev, *(c[0] for c in self.cadeados)):
            if j and not self.escondido:
                por_cima(j)
        if self.travado:
            self._posicionar_cadeados()
        self.root.after(2000, self._reafirmar)

    def _erro(self, tipo, valor, tb) -> None:
        if tipo is KeyboardInterrupt:
            self.fechar()
        else:
            import traceback
            traceback.print_exception(tipo, valor, tb)       # no app instalado vai para nebula.log

    def fechar(self) -> None:
        if self.fonte:
            self.fonte.parar()
        self.salvar_cfg()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ---------- laço ----------
    def _quadro(self) -> None:
        self._n_quadro += 1
        if self._n_quadro % 5 == 0:      # 4 vezes por segundo: o Alt+Tab some com o overlay na hora
            self._checar_foco()
        agora = self.fonte.processar(self.sessao) if self.fonte else time.time()
        self.sessao.tick(agora)
        st = self.sessao.estado(agora)
        self._st = st
        self._desenhar_alertas(st, agora)
        if self.cv_me:
            self._desenhar_meter(st.get("meter"), agora)
        if self.cv_bo:
            self._desenhar_borda(st, agora)
        self._sons(st, agora)
        self._desenhar_eventos(agora)
        self.root.after(50, self._quadro)

    def _cor_acao(self, tipo: str) -> str:
        return ACAO.get(self.cats.get(tipo, self.cats["atencao"])["cor"], "#b9b3c9")

    def _texto(self, cv, x, y, texto, fonte, cor, anchor="center", borda=2, tags="dyn"):
        """Texto com contorno preto, legível sobre qualquer parte do jogo (estilo WeakAuras)."""
        for dx in (-borda, 0, borda):
            for dy in (-borda, 0, borda):
                if dx or dy:
                    cv.create_text(x + dx, y + dy, text=texto, font=fonte, fill="#000000", anchor=anchor, tags=tags)
        cv.create_text(x, y, text=texto, font=fonte, fill=cor, anchor=anchor, tags=tags)

    def _icone(self, cv, tipo, cx, cy, tam, cor, tags="dyn"):
        ultimo = max(cv.find_all() or (0,))
        icone(cv, tipo, cx + 1, cy + 1, tam, "#000000")   # sombra
        icone(cv, tipo, cx, cy, tam, cor)
        for item in cv.find_all():
            if item > ultimo:
                cv.addtag_withtag(tags, item)             # o ícone também sai no próximo quadro

    def _medir(self, texto: str, fonte: tuple) -> int:
        if fonte not in self._fontes:
            self._fontes[fonte] = tkfont.Font(root=self.root, family=fonte[0], size=fonte[1],
                                              weight=fonte[2] if len(fonte) > 2 else "normal")
        return self._fontes[fonte].measure(texto)

    def _linha(self, cv, cx, y, tipo, texto, fonte, cor, tam_icone, extra="", fonte_extra=None):
        """Ícone + texto (+ texto extra) centralizados como um grupo em cx."""
        gap = 8 * self.escala
        largura = tam_icone + gap + self._medir(texto, fonte) + (gap + self._medir(extra, fonte_extra) if extra else 0)
        x = cx - largura / 2
        self._icone(cv, tipo, x + tam_icone / 2, y, tam_icone, self._cor_acao(tipo))
        x += tam_icone + gap
        self._texto(cv, x, y, texto, fonte, cor, anchor="w")
        if extra:
            self._texto(cv, x + self._medir(texto, fonte) + gap, y, extra, fonte_extra, TEXTO, anchor="w", borda=1)

    def _desenhar_alertas(self, st: dict, agora: float) -> None:
        cv, e = self.cv_al, self.escala
        cv.delete("dyn")
        W = int(cv.winfo_width())
        y = 8 * e
        c = st.get("centro")
        if c:
            cor = self._cor_acao(c["tipo"])
            self._linha(cv, W / 2, y + 14 * e, c["tipo"], t("em_s", s=f"{max(0.0, c['eta']):.0f}", texto=tr(c["texto"])),
                        (FONTE, int(15 * e), "bold"), cor, 24 * e, "" if c["exata"] else t("previsto"), (FONTE, int(9 * e)))
            y += 38 * e
        if st["breve"] and not st["cartoes"] and not c:
            a = st["breve"]
            self._linha(cv, W / 2, y + 14 * e, a.tipo, tr(a.texto), (FONTE, int(13 * e), "bold"), NIVEL["info"], 22 * e,
                        tr(a.sub), (FONTE, int(10 * e)))
            y += 36 * e
        for i, a in enumerate(st["cartoes"]):
            y = (self._principal if i == 0 else self._secundario)(a, W / 2, y, agora) + 8 * e
        if st.get("status"):
            self._faixa_status(st["status"][:4], W, y + 4 * e)

    def _faixa_status(self, lista: list[dict], W: float, y: float) -> None:
        """Status do boss e dos jogadores, lado a lado: ícone, texto, segundos e barrinha de duração."""
        cv, e = self.cv_al, self.escala
        f_t, f_s = (FONTE, int(12 * e), "bold"), (FONTE, int(10 * e), "bold")
        ic, gap, sep = 18 * e, 6 * e, 22 * e
        itens = []
        for s in lista:
            nome = t("voce") if s.get("voce") else (s["nome"] or t("jogador"))
            texto = tr(s["texto"]) + (f" → {nome}" if s["em"] == "alvo" else "")
            seg = f"{max(0.0, s['restante']):.1f}s"
            larg = ic + gap + self._medir(texto, f_t) + gap + self._medir(seg, f_s)
            itens.append((s, texto, seg, larg))
        x = W / 2 - (sum(i[3] for i in itens) + sep * (len(itens) - 1)) / 2
        for s, texto, seg, larg in itens:
            cor_i = self._cor_acao(s["tipo"])
            cor_t = NIVEL["alarme"] if s.get("voce") else TEXTO
            self._icone(cv, s["tipo"], x + ic / 2, y + 10 * e, ic, cor_i)
            tx = x + ic + gap
            self._texto(cv, tx, y + 10 * e, texto, f_t, cor_t, anchor="w", borda=1)
            self._texto(cv, tx + self._medir(texto, f_t) + gap, y + 10 * e, seg, f_s, "#c9c3d6", anchor="w", borda=1)
            frac = max(0.0, min(1.0, s["restante"] / s["total"])) if s.get("total") else 0
            cv.create_rectangle(tx, y + 21 * e, x + larg, y + 24 * e, fill="#000000", outline="", tags="dyn")
            cv.create_rectangle(tx, y + 21 * e, tx + (x + larg - tx) * frac, y + 24 * e, fill=cor_i, outline="", tags="dyn")
            x += larg + sep

    def _principal(self, a: Alerta, cx: float, y: float, agora: float) -> float:
        """Contagem gigante no centro, ação embaixo."""
        e = self.escala
        cor = NIVEL.get(a.nivel, TEXTO)
        if a.contagem:
            restante = max(0.0, a.t + a.contagem - agora)
            tam = int((60 if restante <= 3 else 50) * e)
            numero = str(math.ceil(restante)) if restante > 0 else "!"
            self._texto(self.cv_al, cx, y + 44 * e, numero, (FONTE, tam, "bold"), cor, borda=3)
            y += 92 * e
        self._linha(self.cv_al, cx, y + 16 * e, a.tipo, tr(a.texto), (FONTE, int(22 * e), "bold"), cor, 34 * e)
        y += 34 * e
        if a.sub:
            self._texto(self.cv_al, cx, y + 10 * e, tr(a.sub), (FONTE, int(11 * e)), TEXTO, borda=1)
            y += 22 * e
        if a.dica and self.dicas_on:
            self._texto(self.cv_al, cx, y + 10 * e, f"▸ {tr(a.dica)}", (FONTE, int(11 * e), "bold"), DICA, borda=1)
            y += 22 * e
        return y

    def _secundario(self, a: Alerta, cx: float, y: float, agora: float) -> float:
        e = self.escala
        extra = f"{max(0.0, a.t + a.contagem - agora):.1f}s" if a.contagem else ""
        self._linha(self.cv_al, cx, y + 12 * e, a.tipo, tr(a.texto), (FONTE, int(14 * e), "bold"), NIVEL.get(a.nivel, TEXTO),
                    22 * e, extra, (FONTE, int(11 * e), "bold"))
        return y + 24 * e

    def _simbolo_classe(self, chave: str):
        """Imagem do símbolo da classe no tamanho mais próximo da escala (guardada: o Tk apaga imagens sem referência)."""
        if not hasattr(self, "_simbolos"):
            self._simbolos = {}
        if chave not in self._simbolos:
            alvo = (14 if chave == "ODYLE" else 18) * self.escala
            alt = min((14, 18, 22) if chave == "ODYLE" else (18, 24, 30), key=lambda a: abs(a - alvo))
            caminho = app("dados", "classes", f"{chave}_{alt}.png")
            try:
                self._simbolos[chave] = tk.PhotoImage(file=caminho) if chave and os.path.exists(caminho) else None
            except tk.TclError:
                self._simbolos[chave] = None
        return self._simbolos[chave]

    def _cartao_fundo(self, cv, W: float, H: float) -> None:
        """Cartão escuro de cantos arredondados, como o do seu meter."""
        e = self.escala
        ret_arredondado(cv, 1, 1, W - 1, H - 1, 10 * e, fill=CARTAO, outline=CARTAO_BORDA, width=1, tags="dyn")

    def _desenhar_meter(self, m: dict | None, agora: float) -> None:
        """Cartão único:
        - cabeçalho: boss, tempo de luta e % de HP (com a barra de vida enquanto ele está vivo);
        - próximas mecânicas que chegam em até 15 s (o antigo painel do boss);
        - uma barra por jogador na cor da classe (você em roxo, com "EU"), DPS e %;
        - rodapé: você, classe, conexão e o cadeado."""
        cv, e = self.cv_me, self.escala
        cv.delete("dyn")
        W = int(cv.winfo_width())
        mg = 10 * e
        f_t, f_n, f_s, f_d = (FONTE, int(10 * e), "bold"), (FONTE, int(9 * e), "bold"), (FONTE, int(8 * e)), (FONTE, int(10 * e), "bold")
        st = self._st or {}
        b = st.get("boss") if st.get("jogo") else None
        proximas = [p for p in (st.get("linha") or []) if p["eta"] <= 30][:4]
        linhas = (m or {}).get("linhas", [])[:8]
        h, gap = 26 * e, 3 * e
        desenhos = []                    # tudo depois do fundo, que depende da altura total
        y = 17 * e
        # cabeçalho
        nome = b.nome if b else (m["boss"] if m else "DPS")
        ativo = bool(b) or bool(m and m["ativa"])
        tempo = ""
        if m and (not b or m["boss"] == b.nome):
            tempo = f"{int(m['duracao'] // 60)}:{int(m['duracao'] % 60):02d}" + ("" if m["ativa"] else t("ultima"))
        direita = f"{b.pct:.1f}%" if b else (f"{numero(m['dps_total'])}/s" if m else "")

        def cab(y=y, nome=nome, ativo=ativo, tempo=tempo, direita=direita):
            cv.create_oval(mg, y - 4 * e, mg + 8 * e, y + 4 * e, fill=NIVEL["alerta"] if ativo else "#6b6880", outline="", tags="dyn")
            cv.create_text(mg + 14 * e, y, text=nome, anchor="w", fill=TEXTO, font=f_t, tags="dyn")
            if tempo:
                cv.create_text(mg + 22 * e + self._medir(nome, f_t), y, text=tempo, anchor="w", fill="#8d8aa0", font=f_t, tags="dyn")
            cv.create_text(W - mg, y, text=direita, anchor="e", fill=TEXTO if b else "#8d8aa0", font=f_t if b else f_s, tags="dyn")
        desenhos.append(cab)
        y += 12 * e
        if b:
            def vida(y=y, pct=b.pct):
                cv.create_rectangle(mg, y, W - mg, y + 5 * e, fill="#2a1d24", outline="", tags="dyn")
                cv.create_rectangle(mg, y, mg + (W - 2 * mg) * pct / 100, y + 5 * e, fill="#e2706a", outline="", tags="dyn")
            desenhos.append(vida)
            y += 9 * e
            atord = st.get("atordoamento")
            if atord and atord[1]:
                cheio = 1 - atord[0] / atord[1]        # o medidor desce de 1200 a 0: quanto falta para atordoar

                def medidor(y=y, cheio=cheio):
                    cv.create_rectangle(mg, y, W - mg - 46 * e, y + 4 * e, fill="#231d33", outline="", tags="dyn")
                    cv.create_rectangle(mg, y, mg + (W - 2 * mg - 46 * e) * cheio, y + 4 * e, fill="#9b6bff", outline="",
                                        tags="dyn")
                    cv.create_text(W - mg, y + 2 * e, text=t("atord", p=f"{cheio * 100:.0f}"), anchor="e", fill="#9b8fc9",
                                   font=f_s, tags="dyn")
                desenhos.append(medidor)
                y += 9 * e
        # próximas mecânicas (antes era o painel do boss)
        for p in proximas:
            confiavel = p["confianca"] >= 0.75
            cor = self._cor_acao(p["tipo"]) if confiavel else misturar(self._cor_acao(p["tipo"]), CARTAO, 0.55)
            perto = p["eta"] <= 6 and confiavel
            lado = ("" if p["exata"] else "~") + (f"{p['eta']:.1f}s" if p["eta"] >= 0.5 else t("agora"))
            frac = max(0.0, min(1.0, 1 - p["eta"] / 30))
            yy = y + 11 * e
            cor_txt = (cor if perto else TEXTO) if confiavel else "#8d8aa0"

            def prox(yy=yy, p=p, cor=cor, perto=perto, lado=lado, frac=frac, cor_txt=cor_txt):
                cv.create_rectangle(mg, yy - 10 * e, W - mg, yy + 10 * e, fill=CARTAO_LINHA, outline=cor if perto else "", tags="dyn")
                if frac:
                    cv.create_rectangle(mg, yy + 8 * e, mg + (W - 2 * mg) * frac, yy + 10 * e, fill=cor, outline="", tags="dyn")
                self._icone(cv, p["tipo"], mg + 12 * e, yy, 13 * e, cor)
                cv.create_text(mg + 24 * e, yy, text=tr(p["texto"]), anchor="w", fill=cor_txt, font=f_n, tags="dyn")
                cv.create_text(W - mg - 6 * e, yy, text=lado, anchor="e", fill=cor_txt, font=f_n, tags="dyn")
            desenhos.append(prox)
            y += 23 * e
        y += 6 * e
        # jogadores
        if not linhas:
            msg = t("aguardando_boss") if not b else t("aguardando_golpe")
            desenhos.append(lambda y=y, msg=msg: cv.create_text(mg, y + h / 2, text=msg, anchor="w", fill="#8d8aa0", font=f_n, tags="dyn"))
            y += h + gap
        topo_pct = linhas[0]["pct"] if linhas else 1.0
        for l in linhas:
            def jogador(y0=y, l=l):
                meio = y0 + h / 2
                base_cor = CLASSE_COR.get(l["chave"], "#9d96b0")
                cor_barra = misturar(VOCE if l["voce"] else base_cor, CARTAO_LINHA, 0.55 if l["voce"] else 0.38)
                cv.create_rectangle(mg, y0, W - mg, y0 + h, fill=CARTAO_LINHA, outline="", tags="dyn")
                cv.create_rectangle(mg, y0, mg + (W - 2 * mg) * l["pct"] / max(1.0, topo_pct), y0 + h, fill=cor_barra,
                                    outline="", tags="dyn")
                cx = mg + 13 * e
                img = self._simbolo_classe(l["chave"])
                if img:      # o símbolo da classe como no jogo (dados/classes)
                    cv.create_image(cx, meio, image=img, tags="dyn")
                else:        # sem símbolo (Lutador, ou classe desconhecida): a inicial na cor da classe
                    cv.create_oval(cx - 8 * e, meio - 8 * e, cx + 8 * e, meio + 8 * e, fill=misturar(base_cor, CARTAO, 0.35),
                                   outline=base_cor, width=1, tags="dyn")
                    cv.create_text(cx, meio, text=CLASSE_SIGLA.get(l["chave"], "?")[0], fill=base_cor, font=f_s, tags="dyn")
                x = cx + 14 * e
                nome = l["nome"] if len(l["nome"]) <= 14 else l["nome"][:13] + "…"
                cv.create_text(x, meio, text=nome, anchor="w", fill=TEXTO, font=f_n, tags="dyn")
                x += self._medir(nome, f_n) + 5 * e
                if l["voce"]:
                    cv.create_text(x, meio, text=t("eu"), anchor="w", fill="#c9b8ff", font=f_s, tags="dyn")
                    x += self._medir(t("eu"), f_s) + 5 * e
                cv.create_text(x, meio, text=numero(l["dano"]), anchor="w", fill="#8d8aa0", font=f_s, tags="dyn")
                x += self._medir(numero(l["dano"]), f_s) + 6 * e
                for st_txt in l["status"][:2]:      # mecânica em cima do jogador: POÇA, MERGULHO, AGARRADO
                    st_txt = tr(st_txt)
                    lw = self._medir(st_txt, f_s) + 8 * e
                    cv.create_rectangle(x, meio - 7 * e, x + lw, meio + 7 * e, fill="#5a1520", outline=NIVEL["alarme"], tags="dyn")
                    cv.create_text(x + lw / 2, meio, text=st_txt, font=f_s, fill="#ffffff", tags="dyn")
                    x += lw + 4 * e
                cv.create_text(W - mg - 52 * e, meio, text=numero(l["dps"]), anchor="e", fill=TEXTO, font=f_d, tags="dyn")
                cv.create_text(W - mg - 6 * e, meio, text=f"{l['pct']:.1f}%".replace(".", ","), anchor="e", fill="#8d8aa0",
                               font=f_s, tags="dyn")
            desenhos.append(jogador)
            y += h + gap
        # rodapé: você, classe e conexão (o cadeado fica no canto direito, numa janelinha própria)
        nome_c, papel = idioma.nome_classe(st.get("classe_chave")), idioma.nome_papel(st.get("papel"))
        classe = f"{nome_c} ({papel})" if nome_c else papel
        rotulo = self.fonte.rotulo if self.fonte else ""
        quem = " · ".join(x for x in (st.get("eu"), classe, rotulo) if x) or t("procurando")
        y += 14 * e
        desenhos.append(lambda y=y, quem=quem: cv.create_text(mg, y, text=quem, anchor="w", fill="#8d8aa0", font=f_s, tags="dyn"))
        if st.get("odyle"):
            # energia Odyle no rodapé, à esquerda da engrenagem: restante (+recarga)
            base_, extra = st["odyle"]
            texto_o = f"{base_}" + (f" (+{extra})" if extra else "")
            x_o = W - mg - 2 * self.t_cad - 16 * e
            img = self._simbolo_classe("ODYLE")

            def odyle(y=y, x_o=x_o, texto_o=texto_o, img=img):
                cv.create_text(x_o, y, text=texto_o, anchor="e", fill="#d8c9ff", font=f_s, tags="dyn")
                if img:
                    cv.create_image(x_o - self._medir(texto_o, f_s) - 4 * e, y, image=img, anchor="e", tags="dyn")
            desenhos.append(odyle)
        altura = y + 14 * e
        if int(altura) != getattr(self, "_alt_meter", None):
            self._alt_meter = int(altura)
            self._posicionar_cadeados()      # o cartão cresceu ou encolheu: o cadeado do rodapé acompanha
        self._cartao_fundo(cv, W, altura)
        for d in desenhos:
            d()
        cv.tag_lower("moldura")

    # ---------- eventos de campo ----------
    def _lista_eventos(self, agora: float) -> list[dict]:
        if not self.cfg.get("eventos", True):
            return []
        aviso = float(self.cfg.get("eventos_aviso_min", 5)) * 60
        return self.eventos.estado(agora, janela=aviso, desligados=set(self.cfg.get("eventos_desligados", [])))[:3]

    def _desenhar_eventos(self, agora: float) -> None:
        """Cartões dos eventos: "Festival Shugo · 5 min" antes, "aberto · 3:40" durante. Avisa com voz uma vez."""
        cv, e = self.cv_ev, self.escala
        cv.delete("dyn")
        lista = self._lista_eventos(agora)
        self._avisar_eventos(lista, agora)
        W = int(cv.winfo_width())
        h, gap = 46 * e, 6 * e
        f_n, f_s, f_t = (FONTE, int(10 * e), "bold"), (FONTE, int(8 * e)), (FONTE, int(13 * e), "bold")
        for i, ev in enumerate(lista):
            y0 = i * (h + gap)
            aberto = ev["estado"] == "aberto"
            cor = NIVEL["info"] if aberto else EVENTO
            ret_arredondado(cv, 1, y0 + 1, W - 1, y0 + h - 1, 9 * e, fill=CARTAO, outline=CARTAO_BORDA, width=1, tags="dyn")
            cx, cy = 22 * e, y0 + h / 2
            ret_arredondado(cv, cx - 14 * e, cy - 14 * e, cx + 14 * e, cy + 14 * e, 7 * e,
                            fill=misturar(cor, CARTAO, 0.18), outline="", tags="dyn")
            self._icone(cv, "burst", cx, cy, 18 * e, cor)
            cv.create_text(44 * e, y0 + 16 * e, text=nome_evento(ev, idioma.atual()), anchor="w", fill=TEXTO, font=f_n, tags="dyn")
            if aberto:
                sub = t("aberto") + (f" · {t('fase', n=ev['fase'])}" if ev.get("fase") else "")
                restam = max(0, int(ev["restam"]))
                valor = f"{restam // 60}:{restam % 60:02d}"
            else:
                inicio_pc = ev["inicio"] - self.eventos.atraso
                sub = t("comeca_as", h=time.strftime("%H:%M", time.localtime(inicio_pc)))
                faltam = max(0, ev["faltam"])
                valor = t("em_min", m=math.ceil(faltam / 60)) if faltam >= 60 else f"{int(faltam)} s"
            cv.create_text(44 * e, y0 + 32 * e, text=sub, anchor="w", fill="#8d8aa0", font=f_s, tags="dyn")
            cv.create_text(W - 12 * e, cy, text=valor, anchor="e", fill=cor, font=f_t, tags="dyn")
            if not aberto:                       # barrinha: quanto da espera já passou
                frac = 1 - max(0.0, ev["faltam"]) / max(1.0, float(self.cfg.get("eventos_aviso_min", 5)) * 60)
                cv.create_rectangle(10 * e, y0 + h - 4 * e, 10 * e + (W - 20 * e) * frac, y0 + h - 2 * e,
                                    fill=cor, outline="", tags="dyn")
        cv.tag_lower("moldura")

    def _avisar_eventos(self, lista: list[dict], agora: float) -> None:
        if self.modo_som == "mudo" or not self.cfg.get("eventos_voz", True):
            return
        aviso = int(self.cfg.get("eventos_aviso_min", 5))
        for ev in lista:
            if ev["estado"] == "em_breve":
                chave, fala = (ev["chave"], round(ev["inicio"]), "antes"), f"evento_{aviso}"
            elif ev["faltam"] > -60:                 # acabou de abrir (não avisa evento que já estava aberto)
                chave, fala = (ev["chave"], round(ev["inicio"]), "abriu"), "evento_agora"
            else:
                continue
            if chave in self._eventos_avisados:
                continue
            self._eventos_avisados.add(chave)
            if not (self.voz and self.voz.falar(fala)):
                tocar("sino")

    def _criar_brilho(self) -> None:
        """Brilho vermelho nas bordas: faixas cada vez mais ralas, para parecer um degradê."""
        cv, W, H, f = self.cv_bo, self.base[2], self.base[3], int(9 * self.escala)
        cv.delete("all")
        for k, pont in enumerate(("", "gray75", "gray50", "gray25", "gray12")):
            a, b = k * f, (k + 1) * f
            for x0, y0, x1, y1 in ((a, a, W - a, b), (a, H - b, W - a, H - a), (a, b, b, H - b), (W - b, b, W - a, H - b)):
                cv.create_rectangle(x0, y0, x1, y1, fill="#ff2a2a", outline="", stipple=pont)
        self.w_bo.attributes("-alpha", 0.0)
        self._alfa = 0.0

    def _desenhar_borda(self, st: dict, agora: float) -> None:
        """Pulsa devagar (1,6 vez por segundo) enquanto houver alarme a 3 s ou menos."""
        urg = any(a.nivel == "alarme" and (not a.contagem or a.t + a.contagem - agora <= 3) for a in st["cartoes"])
        alfa = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(time.monotonic() * 2 * math.pi * 1.6)) if urg else 0.0
        if abs(alfa - self._alfa) > 0.02:
            self._alfa = alfa
            self.w_bo.attributes("-alpha", alfa)

    def _sons(self, st: dict, agora: float) -> None:
        falou_agora = False                  # um áudio novo corta o anterior: só o mais importante fala
        for a in st["cartoes"]:
            chave = (a.id, a.passo, round(a.t, 2))
            if chave in self.vistos:
                continue
            self.vistos.add(chave)
            if (a.nivel == "info" and a.tipo not in ("burst", "segurar_burst")) or self.modo_som == "mudo":
                continue
            if self.voz:
                import voz as voz_curta
                if falou_agora:
                    continue
                falou = self.voz.falar(voz_curta.chave_de(a))     # "Sai!", "Empilha!", "Em você! Sai!"...
                falou_agora = falou_agora or falou
                if a.contagem_voz and a.contagem:
                    self.voz.contagem(time.monotonic() + (a.t + a.contagem - agora) / getattr(self.fonte, "velocidade", 1.0))
                if falou:
                    continue
                from a2parse.sons import tocar
                tocar(self.cats.get(a.tipo, self.cats["atencao"])["som"])
            else:
                from a2parse.sons import tocar
                tocar(self.cats.get(a.tipo, self.cats["atencao"])["som"])

    def rodar(self) -> None:
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.fechar()


# ---------------- fontes de pacotes ----------------

class Gravador:
    """Grava a captura só dentro da masmorra, um arquivo por masmorra.

    Guarda sempre os últimos MEMORIA s de pacotes. Quando um boss aparece, abre o arquivo e grava essa
    memória primeiro (entrada na zona, seu personagem, spawns); ao sair da zona espera ESPERA s antes de
    fechar (morrer e voltar não divide a run em dois arquivos).
    """
    MEMORIA, ESPERA = 120.0, 60.0

    def __init__(self, linktype: int, pasta: str | None = None) -> None:
        import collections
        self.linktype = linktype
        self.pasta = pasta                # padrão: capturas/ na pasta do usuário
        self.memoria: collections.deque = collections.deque()
        self.arquivo = None
        self.caminho = ""
        self.ativo = False                # ligado pela interface: zona com boss
        self.fim_previsto: float | None = None

    def _abrir(self) -> None:
        import struct
        os.makedirs(self.pasta or pasta_usuario("capturas"), exist_ok=True)
        self.caminho = os.path.join(self.pasta or pasta_usuario("capturas"), f"aovivo_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.pcap")
        self.arquivo = open(self.caminho, "wb")
        self.arquivo.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, self.linktype))
        for p in self.memoria:
            self._escrever(*p)
        print(f"Masmorra: gravando em {os.path.basename(self.caminho)}")

    def _escrever(self, ts: float, dados: bytes, tam: int) -> None:
        import struct
        seg = int(ts)
        self.arquivo.write(struct.pack("<IIII", seg, int((ts - seg) * 1e6), len(dados), tam) + dados)

    def pacote(self, ts: float, dados: bytes, tam: int) -> None:
        self.memoria.append((ts, dados, tam))
        while self.memoria and ts - self.memoria[0][0] > self.MEMORIA:
            self.memoria.popleft()
        if self.ativo:
            self.fim_previsto = None
            if self.arquivo is None:
                self._abrir()
                return                                 # este pacote já foi junto com a memória
        elif self.arquivo is not None and self.fim_previsto is None:
            self.fim_previsto = ts + self.ESPERA
        if self.arquivo is not None:
            self._escrever(ts, dados, tam)
            if self.fim_previsto is not None and ts >= self.fim_previsto:
                self.fechar()

    def fechar(self) -> None:
        if self.arquivo is not None:
            self.arquivo.close()
            print(f"Fora da masmorra: gravação em espera ({os.path.basename(self.caminho)} fechado)")
        self.arquivo, self.fim_previsto = None, None


class FonteAoVivo:
    """Captura pelo Npcap numa thread; a interface processa os pacotes no seu próprio ritmo."""
    velocidade = 1.0

    def __init__(self, salvar: bool, sempre: bool = False, rota: dict | None = None) -> None:
        import gravar as g
        self.g = g
        self.fila: queue.Queue = queue.Queue()
        self.parado = threading.Event()
        w = g.carregar_wpcap()
        lista = g.placas(w)
        rota = rota if rota is not None else g.rota_do_jogo()
        self.proxy = None
        if rota and rota.get("proxy"):
            self.proxy = rota["proxy"].replace(".exe", "")
            placa = next((p for p in lista if "loopback" in (p["descricao"] + p["nome"]).lower()), None)
            if placa is None:
                raise g.ErroCaptura("erro_loopback", f"O jogo passa pelo {self.proxy}, mas o Npcap não tem a placa "
                                    "de loopback.", proxy=self.proxy)
            filtro = f"tcp port {rota['porta']}"
        else:
            ip = g.ip_local()
            placa = next((p for p in lista if ip and ip in p["ips"]), None)
            if placa is None:
                raise g.ErroCaptura("erro_placa", "Não consegui escolher a placa de rede.")
            filtro = g.FILTRO_PADRAO
        erro = C.create_string_buffer(256)
        self.h = w.pcap_open_live(placa["nome"].encode(), 65535, 0, 50, erro)
        if self.h:
            g.buffer_grande(w, self.h)
        if not self.h:
            texto = erro.value.decode(errors="replace")
            raise g.ErroCaptura("erro_abrir", "Não consegui abrir a placa: " + texto, erro=texto)
        prog = g.bpf_program()
        if w.pcap_compile(self.h, C.byref(prog), filtro.encode(), 1, 0xFFFFFFFF) != 0 or w.pcap_setfilter(self.h, C.byref(prog)) != 0:
            texto = (w.pcap_geterr(self.h) or b"").decode(errors="replace")
            raise g.ErroCaptura("erro_abrir", "Filtro inválido: " + texto, erro=texto)
        w.pcap_freecode(C.byref(prog))
        self.w, self.linktype = w, w.pcap_datalink(self.h)
        self.dumper = None
        self.gravador = None
        if salvar and sempre:
            arq = os.path.join(pasta_usuario("capturas"), f"aovivo_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.pcap")
            self.dumper = w.pcap_dump_open(self.h, arq.encode("mbcs"))
            print(f"Gravando tudo em {arq} (--sempre-gravar).")
        elif salvar:
            self.gravador = Gravador(self.linktype)
            print("Gravação em espera: começa sozinha quando um boss aparecer (masmorra). --sem-salvar desliga.")
        print(f"Capturando: {placa['descricao'] or placa['nome']} · {filtro}")
        threading.Thread(target=self._laco, daemon=True).start()

    @property
    def rotulo(self) -> str:
        return t("via", proxy=self.proxy) if self.proxy else t("direto")

    def _laco(self) -> None:
        g, w = self.g, self.w
        hdr, dados = C.POINTER(g.pcap_pkthdr)(), C.POINTER(C.c_ubyte)()
        while not self.parado.is_set():
            r = w.pcap_next_ex(self.h, C.byref(hdr), C.byref(dados))
            if r == 1:
                if self.dumper:
                    w.pcap_dump(self.dumper, hdr, dados)
                cap = hdr.contents.caplen
                ts = hdr.contents.ts.tv_sec + hdr.contents.ts.tv_usec / 1e6
                bruto = C.string_at(dados, cap)
                if self.gravador:
                    self.gravador.pacote(ts, bruto, hdr.contents.len)
                self.fila.put((ts, bruto))
            elif r < 0:
                break
        perdidos = self.g.descartados(w, self.h)
        if self.gravador:
            self.gravador.fechar()
        if self.dumper:
            w.pcap_dump_close(self.dumper)
        w.pcap_close(self.h)
        if perdidos:
            print(f"Atenção: o Npcap descartou {perdidos} pacotes (buffer cheio).")

    def processar(self, sessao: Sessao) -> float:
        if self.gravador:
            self.gravador.ativo = sessao.zona_com_boss     # a thread de captura liga/desliga a gravação
        for _ in range(5000):
            try:
                ts, dados = self.fila.get_nowait()
            except queue.Empty:
                break
            seg = _decodificar(self.linktype, dados, ts)
            if seg:
                sessao.segmento(seg)
        return time.time()

    def parar(self) -> None:
        self.parado.set()


class FonteRepeticao:
    """Reproduz uma captura gravada no tempo real (ou acelerado), como se fosse ao vivo."""

    def __init__(self, arquivo: str, a_partir: float, velocidade: float) -> None:
        print("Lendo a captura…")
        self.segs = list(ler_segmentos(arquivo))
        if not self.segs:
            sys.exit("Captura vazia.")
        self.t0 = self.segs[0].ts
        self.velocidade = velocidade
        self.inicio_cap = self.t0 + a_partir
        self.inicio_real = time.monotonic()
        self.i = 0
        print(f"{len(self.segs)} segmentos. Reproduzindo a partir de {int(a_partir // 60)}:{a_partir % 60:04.1f} da captura.")

    @property
    def rotulo(self) -> str:
        return t("repeticao", v=f"{self.velocidade:g}")

    def agora(self) -> float:
        return self.inicio_cap + (time.monotonic() - self.inicio_real) * self.velocidade

    def processar(self, sessao: Sessao) -> float:
        agora = self.agora()
        while self.i < len(self.segs) and self.segs[self.i].ts <= agora:
            sessao.segmento(self.segs[self.i])
            self.i += 1
        return agora

    def parar(self) -> None:
        pass


class FonteDemo:
    """Alertas de exemplo em ciclo, para posicionar as janelas e escolher o tamanho."""
    velocidade = 1.0

    @property
    def rotulo(self) -> str:
        return t("demo")

    def __init__(self) -> None:
        self.inicio = time.time()
        self.ultimo = -1

    def processar(self, sessao: Sessao) -> float:
        agora = time.time()
        k = int((agora - self.inicio) // 6)
        if k != self.ultimo:
            self.ultimo = k
            exemplos = [
                Alerta(agora, "ativo", "Divine Auldor", "demo", "EMPILHA NO CÍRCULO", "círculo vermelho com setas", "empilhar", 5.0, True, 0, "alarme"),
                Alerta(agora, "ativo", "Guardian Captain Raur", "demo", "PARA E VAI PRA BORDA", "explosão em ~5 s", "parar_dano", 5.0, True, 0, "alarme"),
                Alerta(agora, "ativo", "Judge Urahum", "demo", "SAI DO ALCANCE", "6 anéis em ~2 s", "sair", 2.0, False, 0, "alerta"),
                Alerta(agora, "ativo", "Divine Auldor", "demo", "FASE DO CÉU", "ele some em ~3 s", "atencao", 3.0, True, 0, "info"),
            ]
            sessao.alertas.append(exemplos[k % len(exemplos)])
            sessao.jogo_visto = True
        return agora

    def parar(self) -> None:
        pass


def atualizar_dev() -> bool:
    from a2parse import atualizar
    return atualizar.de_desenvolvimento()


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Nebula Overlay: alertas de mecânica do Aion 2.")
    ap.add_argument("--repetir", metavar="CAPTURA", help="reproduz uma captura .pcap/.pcapng em tempo real")
    ap.add_argument("--a-partir", default="0:00", help="início da repetição (m:s desde o começo da captura)")
    ap.add_argument("--velocidade", type=float, default=1.0, help="velocidade da repetição")
    ap.add_argument("--demo", action="store_true", help="alertas de exemplo para posicionar as janelas")
    ap.add_argument("--voz", action="store_true", help="(antigo; a voz agora vem da engrenagem)")
    ap.add_argument("--sem-som", action="store_true")
    ap.add_argument("--idioma", choices=["pt", "en", "es"], help="idioma da interface (padrão: o da engrenagem)")
    ap.add_argument("--idioma-voz", choices=["pt-BR", "en-US", "es"], help="voz (padrão: a da engrenagem)")
    ap.add_argument("--mover", action="store_true", help="abre com o cadeado aberto (dá pra arrastar as janelas)")
    ap.add_argument("--escala", type=float, help="tamanho (1 = padrão, 1.3 = maior)")
    ap.add_argument("--sem-meter", action="store_true", help="esconde o painel do boss e do grupo")
    ap.add_argument("--sempre-visivel", action="store_true", help="não esconde o overlay quando o jogo perde o foco")
    ap.add_argument("--antecipar", type=float, default=0.8, help="s que os passos previstos aparecem antes (padrão 0,8)")
    ap.add_argument("--sem-borda", action="store_true", help="desliga a borda vermelha piscando nos alarmes")
    ap.add_argument("--sem-salvar", action="store_true", help="ao vivo, não grava a captura em disco")
    ap.add_argument("--sempre-gravar", action="store_true", help="grava tudo, também fora da masmorra")
    ap.add_argument("--sem-pre-aviso", action="store_true")
    ap.add_argument("--classe", choices=sorted(NOME_CLASSE), help="força a classe (o padrão é detectar sozinho)")
    ap.add_argument("--papel", choices=["tank", "healer", "dps", "suporte"], help="força o papel (o padrão vem da classe)")
    ap.add_argument("--sem-burst", action="store_true", help="sem os avisos de segurar/soltar burst")
    ap.add_argument("--sem-dicas", action="store_true", help="sem a linha de dica da classe")
    args = ap.parse_args(argv)
    print(f"Nebula Overlay {VERSAO}")
    Overlay(args).rodar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
