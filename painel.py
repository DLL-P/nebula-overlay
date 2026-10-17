"""Janelas normais do Nebula Overlay (com foco e clicáveis), ao contrário das camadas por cima do jogo:

- Inicio: a janela principal. Mostra se achou o jogo, avisa de problemas (Npcap) e de versão nova,
  e é por ela que se fecha o programa.
- Configuracoes: tudo o que antes era opção de linha de comando ou .bat, em abas.
- Saida: roda uma ferramenta (aprender roteiros, relatório) e mostra o que ela escreve.
"""

from __future__ import annotations

import contextlib
import os
import queue
import threading
import tkinter as tk
import webbrowser

from a2parse import atualizar, idioma
from a2parse.caminhos import USUARIO, app, pasta_usuario
from a2parse.idioma import IDIOMAS, t
from a2parse.versao import APOIO_URL, DISCORD_URL, FORMULARIO_URL, REPO, VERSAO

CARTAO, BORDA, TEXTO, SUAVE = "#1a1c25", "#2c2f3d", "#ece7f5", "#8d8aa0"
DESTAQUE, BOTAO, BOTAO_ATIVO = "#7b5cf0", "#2c2f3d", "#3a3e50"
VERDE, AMARELO, VERMELHO = "#46d18a", "#f2c53b", "#ff4d4d"
NPCAP_URL = "https://npcap.com/#download"
CONTRIBUIR_URL = f"https://github.com/{REPO}/blob/main/CONTRIBUTING.md"
FONTE = "Segoe UI"


def abrir(caminho: str) -> None:
    """Abre uma pasta no Explorador ou um link no navegador."""
    if caminho.startswith("http"):
        webbrowser.open(caminho)
    else:
        os.startfile(caminho)


def _botao(pai, texto: str, comando, destaque: bool = False, pequeno: bool = False) -> tk.Button:
    return tk.Button(pai, text=texto, command=comando, bg=DESTAQUE if destaque else BOTAO, fg=TEXTO,
                     activebackground=BOTAO_ATIVO, activeforeground=TEXTO, relief="flat", cursor="hand2",
                     font=(FONTE, 9 if pequeno else 10), padx=10 if pequeno else 12, pady=2 if pequeno else 4)


def _icone(janela: tk.Misc) -> None:
    try:
        janela.iconbitmap(app("dados", "icone.ico"))
    except tk.TclError:
        pass


# ---------------- janela principal ----------------

class Inicio:
    def __init__(self, ov) -> None:
        self.ov = ov
        self.j = tk.Toplevel(ov.root)
        self.j.title("Nebula Overlay")
        self.j.configure(bg=CARTAO)
        self.j.resizable(False, False)
        _icone(self.j)
        self.j.protocol("WM_DELETE_WINDOW", ov.fechar)
        self.estado = ("esperando", "", None)          # (tipo, texto, erro)
        self.atualizacao: dict | None = None
        self.baixando = ""
        self.construir()
        self.j.update_idletasks()
        x = (self.j.winfo_screenwidth() - self.j.winfo_width()) // 2
        y = (self.j.winfo_screenheight() - self.j.winfo_height()) // 3
        self.j.geometry(f"+{x}+{y}")

    def construir(self) -> None:
        for w in self.j.winfo_children():
            w.destroy()
        self.j.title("Nebula Overlay")
        topo = tk.Frame(self.j, bg=CARTAO)
        topo.pack(fill="x", padx=18, pady=(14, 2))
        tk.Label(topo, text="Nebula Overlay", bg=CARTAO, fg=TEXTO, font=(FONTE, 15, "bold")).pack(side="left")
        tk.Label(topo, text=VERSAO, bg=CARTAO, fg=SUAVE, font=(FONTE, 9)).pack(side="left", padx=(8, 0), pady=(6, 0))
        linha = tk.Frame(self.j, bg=CARTAO)
        linha.pack(fill="x", padx=18, pady=(6, 0))
        self.ponto = tk.Canvas(linha, width=12, height=12, bg=CARTAO, highlightthickness=0)
        self.ponto.pack(side="left", padx=(0, 8))
        self.l_status = tk.Label(linha, text="", bg=CARTAO, fg=TEXTO, font=(FONTE, 10), anchor="w")
        self.l_status.pack(side="left", fill="x")
        self.f_erro = tk.Frame(self.j, bg=CARTAO)
        self.f_atual = tk.Frame(self.j, bg="#231d33")
        botoes = tk.Frame(self.j, bg=CARTAO)
        botoes.pack(fill="x", padx=18, pady=(12, 6), side="bottom")
        _botao(botoes, t("btn_config"), lambda: self.ov.abrir_config(perto_do_meter=False), destaque=True).pack(side="left")
        _botao(botoes, t("btn_pasta"), lambda: abrir(USUARIO)).pack(side="left", padx=8)
        _botao(botoes, t("btn_sair"), self.ov.fechar).pack(side="right")
        dicas = tk.Frame(self.j, bg=CARTAO)
        dicas.pack(fill="x", padx=18, pady=(8, 0), side="bottom")
        for chave in ("dica_alt", "dica_janela"):
            tk.Label(dicas, text="· " + t(chave), bg=CARTAO, fg=SUAVE, font=(FONTE, 9), wraplength=360,
                     justify="left", anchor="w").pack(fill="x")
        self._mostrar_estado()
        self._mostrar_atualizacao()

    # estado da conexão
    def status(self, tipo: str, texto: str = "", erro=None) -> None:
        """tipo: esperando, conectado, testando ou erro."""
        if (tipo, texto, erro) != self.estado:
            self.estado = (tipo, texto, erro)
            self._mostrar_estado()

    def _mostrar_estado(self) -> None:
        tipo, texto, erro = self.estado
        cor = {"conectado": VERDE, "testando": AMARELO, "erro": VERMELHO}.get(tipo, SUAVE)
        self.ponto.delete("all")
        self.ponto.create_oval(2, 2, 11, 11, fill=cor, outline="")
        self.l_status.config(text=t(tipo, rotulo=texto) if tipo in ("conectado", "testando") else
                             t("esperando") if tipo == "esperando" else t("btn_tentar"))
        for w in self.f_erro.winfo_children():
            w.destroy()
        if tipo != "erro" or erro is None:
            self.f_erro.pack_forget()
            return
        self.l_status.config(text="")
        tk.Label(self.f_erro, text=t(erro.chave, **erro.valores), bg=CARTAO, fg=VERMELHO, font=(FONTE, 10),
                 wraplength=360, justify="left", anchor="w").pack(fill="x")
        b = tk.Frame(self.f_erro, bg=CARTAO)
        b.pack(fill="x", pady=(6, 0))
        if erro.chave in ("erro_npcap", "erro_loopback"):
            _botao(b, t("btn_npcap"), lambda: abrir(NPCAP_URL), destaque=True, pequeno=True).pack(side="left", padx=(0, 8))
        _botao(b, t("btn_tentar"), self.ov.tentar_de_novo, pequeno=True).pack(side="left")
        self.f_erro.pack(fill="x", padx=18, pady=(6, 0))

    # atualização
    def nova_versao(self, info: dict | None) -> None:
        self.atualizacao = info
        self._mostrar_atualizacao()

    def baixando_atualizacao(self, texto: str) -> None:
        self.baixando = texto
        self._mostrar_atualizacao()

    def _mostrar_atualizacao(self) -> None:
        for w in self.f_atual.winfo_children():
            w.destroy()
        if not self.atualizacao:
            self.f_atual.pack_forget()
            return
        texto = self.baixando or t("nova_versao", v=self.atualizacao["versao"])
        tk.Label(self.f_atual, text=texto, bg="#231d33", fg="#d8c9ff", font=(FONTE, 10), anchor="w").pack(
            side="left", padx=10, pady=6)
        if not self.baixando:
            _botao(self.f_atual, t("btn_atualizar"), self.ov.atualizar_agora, destaque=True, pequeno=True).pack(
                side="right", padx=8, pady=4)
        self.f_atual.pack(fill="x", padx=18, pady=(10, 0))


# ---------------- configurações ----------------

class Configuracoes:
    ABAS = ("aba_geral", "aba_alertas", "aba_eventos", "aba_ferramentas", "aba_sobre")

    def __init__(self, ov, perto_do_meter: bool) -> None:
        self.ov = ov
        self.j = tk.Toplevel(ov.root)
        self.j.configure(bg=CARTAO)
        self.j.resizable(False, False)
        self.j.attributes("-topmost", True)
        _icone(self.j)
        self.aba = "aba_geral"
        self.msg_voz = ""
        self.msg_atual = ""
        self.construir()
        self._posicionar(perto_do_meter)

    def _posicionar(self, perto_do_meter: bool) -> None:
        self.j.update_idletasks()
        w, h = self.j.winfo_width(), self.j.winfo_height()
        me = self.ov.w_me
        if perto_do_meter and me is not None and me.winfo_viewable():
            x = me.winfo_x() + me.winfo_width() + 8
            if x + w > self.ov.sw:
                x = max(0, me.winfo_x() - w - 8)
            y = max(0, min(me.winfo_y() + self.ov._altura_conteudo(me) - h, self.ov.sh - h - 40))
        else:
            x, y = (self.ov.sw - w) // 2, max(0, (self.ov.sh - h) // 3)
        self.j.geometry(f"+{x}+{y}")

    def construir(self) -> None:
        for w in self.j.winfo_children():
            w.destroy()
        self.j.title(t("cfg_titulo"))
        abas = tk.Frame(self.j, bg=CARTAO)
        abas.pack(fill="x", padx=12, pady=(10, 0))
        for chave in self.ABAS:
            ativa = chave == self.aba
            tk.Button(abas, text=t(chave), command=lambda c=chave: self._ir(c), relief="flat", cursor="hand2",
                      bg=DESTAQUE if ativa else BOTAO, fg=TEXTO, activebackground=BOTAO_ATIVO, activeforeground=TEXTO,
                      font=(FONTE, 10, "bold" if ativa else "normal"), padx=12, pady=3).pack(side="left", padx=(0, 4))
        corpo = tk.Frame(self.j, bg=CARTAO, width=430)
        corpo.pack(fill="both", expand=True, padx=16, pady=10)
        getattr(self, "_" + self.aba)(corpo)
        rodape = tk.Frame(self.j, bg=CARTAO)
        rodape.pack(fill="x", padx=16, pady=(0, 12))
        _botao(rodape, t("fechar"), self.j.destroy).pack(side="right")

    def _ir(self, aba: str) -> None:
        self.aba = aba
        self.construir()

    # elementos
    def _titulo(self, pai, texto: str) -> None:
        tk.Label(pai, text=texto, bg=CARTAO, fg=TEXTO, font=(FONTE, 10, "bold"), anchor="w").pack(fill="x", pady=(8, 2))

    def _nota(self, pai, texto: str, cor: str = SUAVE) -> tk.Label:
        l = tk.Label(pai, text=texto, bg=CARTAO, fg=cor, font=(FONTE, 9), wraplength=400, justify="left", anchor="w")
        l.pack(fill="x", pady=(2, 0))
        return l

    def _radios(self, pai, var: tk.Variable, opcoes, comando, lado: bool = False) -> None:
        f = tk.Frame(pai, bg=CARTAO)
        f.pack(fill="x", padx=(6, 0))
        for valor, rotulo in opcoes:
            tk.Radiobutton(f, text=rotulo, value=valor, variable=var, command=comando, bg=CARTAO, fg=TEXTO,
                           selectcolor=BORDA, activebackground=CARTAO, activeforeground=TEXTO, font=(FONTE, 10),
                           anchor="w").pack(side="left" if lado else "top", fill="x", padx=(0, 10) if lado else 0)

    def _caixa(self, pai, texto: str, chave: str, padrao: bool = True, aplicar=None) -> None:
        var = tk.BooleanVar(value=bool(self.ov.cfg.get(chave, padrao)))

        def mudou():
            self.ov.cfg[chave] = var.get()
            self.ov.salvar_cfg(forcar=True)
            if aplicar:
                aplicar(var.get())
        tk.Checkbutton(pai, text=texto, variable=var, command=mudou, bg=CARTAO, fg=TEXTO, selectcolor=BORDA,
                       activebackground=CARTAO, activeforeground=TEXTO, font=(FONTE, 10), anchor="w").pack(fill="x", padx=(6, 0))

    # abas
    def _aba_geral(self, c) -> None:
        self._titulo(c, t("idioma"))
        v_id = tk.StringVar(value=idioma.atual())
        self._radios(c, v_id, IDIOMAS.items(), lambda: self._trocar_idioma(v_id.get()), lado=len(IDIOMAS) <= 4)

        self._titulo(c, t("voz_alertas"))
        v_voz = tk.StringVar(value=self.ov.modo_som)
        estado = self._nota(c, self.msg_voz)

        def trocar_voz():
            estado.config(text=t("aplicando"))
            self.j.update_idletasks()
            self.msg_voz = self.ov.aplicar_voz(v_voz.get())
            estado.config(text=self.msg_voz)
            v_voz.set(self.ov.modo_som)
        estado.pack_forget()
        self._radios(c, v_voz, idioma.vozes() + [("bipes", t("so_bipes")), ("mudo", t("sem_som"))], trocar_voz)
        linha = tk.Frame(c, bg=CARTAO)
        linha.pack(fill="x", pady=(4, 0))
        _botao(linha, t("testar"), self.ov.testar_som, pequeno=True).pack(side="left", padx=(6, 0))
        estado.pack(fill="x", pady=(2, 0))

        self._titulo(c, t("tamanho"))
        v_esc = tk.DoubleVar(value=float(self.ov.cfg.get("escala", self.ov.escala)))

        def escala(_v=None):
            self.ov.cfg["escala"] = round(v_esc.get(), 1)
            self.ov.salvar_cfg(forcar=True)
        tk.Scale(c, from_=0.7, to=1.6, resolution=0.1, orient="horizontal", variable=v_esc, command=escala,
                 bg=CARTAO, fg=TEXTO, troughcolor=BORDA, highlightthickness=0, length=260,
                 activebackground=DESTAQUE).pack(anchor="w", padx=(6, 0))
        self._titulo(c, t("mostrar"))
        self._caixa(c, t("painel_dano"), "meter")
        self._caixa(c, t("perfis_op"), "perfis")
        self._caixa(c, t("borda"), "borda")
        self._caixa(c, t("latencia_op"), "latencia")
        fonte = self.ov.fonte
        if fonte is not None and hasattr(fonte, "proxy"):
            self._nota(c, t("latencia_proxy", proxy=fonte.proxy) if fonte.proxy else t("latencia_direta"))
        self._nota(c, t("reiniciar_aviso"))
        _botao(c, t("reiniciar"), self.ov.reiniciar, pequeno=True).pack(anchor="w", padx=(6, 0), pady=(6, 0))

    def _trocar_idioma(self, cod: str) -> None:
        anterior = idioma.atual()
        idioma.definir(cod)
        self.ov.cfg["idioma"] = cod
        if self.ov.modo_som == idioma.voz_de(anterior):     # a voz seguia o idioma: acompanha a troca
            self.msg_voz = self.ov.aplicar_voz(idioma.voz_de(cod))
        self.ov.salvar_cfg(forcar=True)
        self.construir()
        if self.ov.inicio:
            self.ov.inicio.construir()

    def _aba_alertas(self, c) -> None:
        self._titulo(c, t("centro"))
        v_c = tk.DoubleVar(value=self.ov.sessao.centro_antes)

        def centro():
            self.ov.sessao.centro_antes = v_c.get()
            self.ov.cfg["centro_antes"] = v_c.get()
            self.ov.salvar_cfg(forcar=True)
        self._radios(c, v_c, [(5.0, t("s_antes", s=5)), (3.0, t("s_antes", s=3)), (0.0, t("desligado"))], centro, lado=True)

        self._titulo(c, t("classe"))
        detectada = idioma.nome_classe(self.ov.sessao.classe.classe) or "?"
        rotulos = {t("automatica_c", c=detectada): ""}
        rotulos.update({nome: chave for chave, nome in idioma.classes().items()})
        atual = next((r for r, k in rotulos.items() if k == (self.ov.cfg.get("classe") or "")), next(iter(rotulos)))
        v_cl = tk.StringVar(value=atual)
        menu = tk.OptionMenu(c, v_cl, *rotulos, command=lambda r: self._classe(rotulos[r]))
        menu.config(bg=BOTAO, fg=TEXTO, activebackground=BOTAO_ATIVO, activeforeground=TEXTO, relief="flat",
                    highlightthickness=0, font=(FONTE, 10), width=24, anchor="w")
        menu["menu"].config(bg=BOTAO, fg=TEXTO, font=(FONTE, 10))
        menu.pack(anchor="w", padx=(6, 0))

        self._titulo(c, t("papel"))
        v_pa = tk.StringVar(value=self.ov.cfg.get("papel") or "")
        self._radios(c, v_pa, [("", t("automatico"))] + [(p, idioma.nome_papel(p)) for p in ("tank", "healer", "dps", "suporte")],
                     lambda: self._papel(v_pa.get()), lado=True)

        self._titulo(c, t("mostrar"))
        self._caixa(c, t("dicas"), "dicas", aplicar=lambda v: setattr(self.ov, "dicas_on", v))
        self._caixa(c, t("burst_op"), "burst", aplicar=lambda v: setattr(self.ov.sessao, "burst", v))
        self._caixa(c, t("controle_op"), "controle_em_voce", padrao=False,
                    aplicar=lambda v: setattr(self.ov.sessao, "controle", v))
        self._nota(c, t("controle_nota"))
        self._caixa(c, t("gravar"), "gravar")
        self._nota(c, t("vale_proximo"))

    def _classe(self, chave: str) -> None:
        self.ov.cfg["classe"] = chave or None
        self.ov.sessao.classe_fixa = chave or None
        self.ov.salvar_cfg(forcar=True)

    def _papel(self, papel: str) -> None:
        self.ov.cfg["papel"] = papel or None
        self.ov.sessao.papel_fixo = papel or None
        self.ov.salvar_cfg(forcar=True)

    def _aba_eventos(self, c) -> None:
        from a2parse.eventos import nome as nome_evento
        self._caixa(c, t("eventos_ligar"), "eventos")
        self._titulo(c, t("eventos_antes"))
        v_av = tk.IntVar(value=int(self.ov.cfg.get("eventos_aviso_min", 5)))

        def aviso():
            self.ov.cfg["eventos_aviso_min"] = v_av.get()
            self.ov.salvar_cfg(forcar=True)
        self._radios(c, v_av, [(10, t("em_min", m=10)), (5, t("em_min", m=5)), (1, t("em_min", m=1))], aviso, lado=True)
        self._caixa(c, t("eventos_voz"), "eventos_voz")
        self._titulo(c, t("eventos_quais"))
        desligados = set(self.ov.cfg.get("eventos_desligados", []))
        for ev in self.ov.eventos.definicoes:
            var = tk.BooleanVar(value=ev["chave"] not in desligados)

            def mudou(chave=ev["chave"], var=var):
                lista = set(self.ov.cfg.get("eventos_desligados", []))
                (lista.discard if var.get() else lista.add)(chave)
                self.ov.cfg["eventos_desligados"] = sorted(lista)
                self.ov.salvar_cfg(forcar=True)
            tk.Checkbutton(c, text=nome_evento(ev, idioma.atual()), variable=var, command=mudou, bg=CARTAO, fg=TEXTO,
                           selectcolor=BORDA, activebackground=CARTAO, activeforeground=TEXTO, font=(FONTE, 10),
                           anchor="w").pack(fill="x", padx=(6, 0))
        self._nota(c, t("eventos_nota"))

    def _aba_ferramentas(self, c) -> None:
        for chave, acao in (("aprender", lambda: self.ov.ferramenta("roteiros")),
                            ("relatorio", lambda: self.ov.ferramenta("relatorio")),
                            ("abrir_pasta", lambda: abrir(pasta_usuario())),
                            ("contribuir", lambda: Contribuir(self.ov))):
            _botao(c, t(chave), acao).pack(fill="x", pady=3)

    def _aba_sobre(self, c) -> None:
        tk.Label(c, text="Nebula Overlay", bg=CARTAO, fg=TEXTO, font=(FONTE, 13, "bold"), anchor="w").pack(fill="x")
        self._nota(c, t("versao", v=VERSAO))
        if atualizar.de_desenvolvimento():
            self._nota(c, t("versao_dev"))
        else:
            self._caixa(c, t("atualizar_auto"), "atualizar_auto")
            estado = self._nota(c, self.msg_atual)

            def procurar():
                estado.config(text=t("aplicando"))
                self.j.update_idletasks()
                self.msg_atual = self.ov.procurar_atualizacao(mostrar=True)
                self.construir()                     # mostra o botão "Atualizar agora" se houver versão nova
            linha_a = tk.Frame(c, bg=CARTAO)
            linha_a.pack(fill="x", pady=(4, 0))
            _botao(linha_a, t("procurar"), procurar, pequeno=True).pack(side="left", padx=(6, 0))
            if self.ov._info_atualizacao:
                _botao(linha_a, t("btn_atualizar"), self.ov.atualizar_agora, destaque=True, pequeno=True).pack(
                    side="left", padx=(8, 0))
                self._nota(c, t("nova_versao", v=self.ov._info_atualizacao["versao"]), cor="#d8c9ff")
        self._titulo(c, "")
        self._nota(c, t("aviso_legal"))
        linha = tk.Frame(c, bg=CARTAO)
        linha.pack(fill="x", pady=(10, 0))
        _botao(linha, "GitHub", lambda: abrir(f"https://github.com/{REPO}"), pequeno=True).pack(side="left")
        if APOIO_URL:
            _botao(linha, t("apoiar"), lambda: abrir(APOIO_URL), destaque=True, pequeno=True).pack(side="left", padx=8)
        _botao(linha, t("sair_app"), self.ov.fechar, pequeno=True).pack(side="right")


# ---------------- saída de uma ferramenta ----------------

class _Escritor:
    """sys.stdout de mentira: manda o texto para uma fila que a janela lê."""

    def __init__(self, fila: queue.Queue) -> None:
        self.fila = fila

    def write(self, texto: str) -> int:
        self.fila.put(texto)
        return len(texto)

    def flush(self) -> None:
        pass


class Saida:
    def __init__(self, ov, titulo: str, funcao) -> None:
        self.j = tk.Toplevel(ov.root)
        self.j.title(f"Nebula Overlay · {titulo}")
        self.j.configure(bg=CARTAO)
        self.j.attributes("-topmost", True)
        _icone(self.j)
        self.estado = tk.Label(self.j, text=t("rodando"), bg=CARTAO, fg=AMARELO, font=(FONTE, 10), anchor="w")
        self.estado.pack(fill="x", padx=12, pady=(10, 4))
        f = tk.Frame(self.j, bg=CARTAO)
        f.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        barra = tk.Scrollbar(f)
        barra.pack(side="right", fill="y")
        self.texto = tk.Text(f, width=96, height=30, bg="#14111d", fg=TEXTO, insertbackground=TEXTO, relief="flat",
                             font=("Consolas", 10), yscrollcommand=barra.set, wrap="word")
        self.texto.pack(side="left", fill="both", expand=True)
        barra.config(command=self.texto.yview)
        self.fila: queue.Queue = queue.Queue()
        self.fim = threading.Event()
        threading.Thread(target=self._rodar, args=(funcao,), daemon=True).start()
        self._ler()

    def _rodar(self, funcao) -> None:
        with contextlib.redirect_stdout(_Escritor(self.fila)):
            try:
                funcao()
            except SystemExit:
                pass
            except Exception as e:            # mostra o erro na janela em vez de sumir
                import traceback
                self.fila.put("\n" + "".join(traceback.format_exception(type(e), e, e.__traceback__)))
        self.fim.set()

    def _ler(self) -> None:
        if not self.j.winfo_exists():
            return
        partes = []
        while not self.fila.empty():
            partes.append(self.fila.get_nowait())
        if partes:
            self.texto.insert("end", "".join(partes))
            self.texto.see("end")
        if self.fim.is_set() and self.fila.empty():
            self.estado.config(text=t("pronto"), fg=VERDE)
            return
        self.j.after(150, self._ler)


# ---------------- contribuir ----------------

class Contribuir:
    """Monta o pacote de contribuição: os dados da run sem nomes (a2parse/contribuicao.py) + o relato da pessoa."""

    def __init__(self, ov) -> None:
        import datetime as dt
        import glob
        self.ov = ov
        self.j = tk.Toplevel(ov.root)
        self.j.title(f"Nebula Overlay · {t('contribuir')}")
        self.j.configure(bg=CARTAO)
        self.j.attributes("-topmost", True)
        self.j.resizable(False, False)
        _icone(self.j)
        self.pacote: str | None = None
        capturas = sorted(glob.glob(os.path.join(pasta_usuario("capturas"), "*.pcap*")), key=os.path.getmtime, reverse=True)
        c = tk.Frame(self.j, bg=CARTAO)
        c.pack(fill="both", expand=True, padx=16, pady=12)
        tk.Label(c, text=t("contrib_titulo"), bg=CARTAO, fg=TEXTO, font=(FONTE, 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(c, text=t("contrib_intro"), bg=CARTAO, fg=SUAVE, font=(FONTE, 9), wraplength=440, justify="left",
                 anchor="w").pack(fill="x", pady=(2, 8))

        def campo(rotulo: str) -> None:
            tk.Label(c, text=rotulo, bg=CARTAO, fg=TEXTO, font=(FONTE, 10, "bold"), anchor="w").pack(fill="x", pady=(6, 2))

        campo(t("contrib_run"))
        self.rotulos = {t("contrib_sem_captura"): None}
        for cap in capturas[:15]:
            quando = dt.datetime.fromtimestamp(os.path.getmtime(cap)).strftime("%d/%m %H:%M")
            self.rotulos[f"{quando} · {os.path.getsize(cap) / 1e6:.1f} MB"] = cap
        self.v_run = tk.StringVar(value=list(self.rotulos)[1 if capturas else 0])
        menu = tk.OptionMenu(c, self.v_run, *self.rotulos)
        menu.config(bg=BOTAO, fg=TEXTO, activebackground=BOTAO_ATIVO, activeforeground=TEXTO, relief="flat",
                    highlightthickness=0, font=(FONTE, 10), width=30, anchor="w")
        menu["menu"].config(bg=BOTAO, fg=TEXTO, font=(FONTE, 10))
        menu.pack(anchor="w")
        entrada = dict(bg="#14111d", fg=TEXTO, insertbackground=TEXTO, relief="flat", font=(FONTE, 10))
        campo(t("contrib_conteudo"))
        self.e_conteudo = tk.Entry(c, width=56, **entrada)
        self.e_conteudo.pack(fill="x", ipady=3)
        campo(t("contrib_relato"))
        self.t_relato = tk.Text(c, width=56, height=6, wrap="word", **entrada)
        self.t_relato.pack(fill="x")
        campo(t("contrib_video"))
        self.e_video = tk.Entry(c, width=56, **entrada)
        self.e_video.pack(fill="x", ipady=3)
        self.v_bruta, self.v_ok = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        for var, chave in ((self.v_bruta, "contrib_bruta"), (self.v_ok, "contrib_consentimento")):
            tk.Checkbutton(c, text=t(chave), variable=var, bg=CARTAO, fg=TEXTO, selectcolor=BORDA, activebackground=CARTAO,
                           activeforeground=TEXTO, font=(FONTE, 9), anchor="w", wraplength=430, justify="left").pack(
                fill="x", pady=(6, 0))
        self.estado = tk.Label(c, text="", bg=CARTAO, fg=SUAVE, font=(FONTE, 9), wraplength=440, justify="left", anchor="w")
        self.estado.pack(fill="x", pady=(8, 0))
        self.botoes = tk.Frame(c, bg=CARTAO)
        self.botoes.pack(fill="x", pady=(8, 0))
        self._botoes()
        self.j.update_idletasks()
        self.j.geometry(f"+{(ov.sw - self.j.winfo_width()) // 2}+{max(0, (ov.sh - self.j.winfo_height()) // 4)}")

    def _botoes(self) -> None:
        for w in self.botoes.winfo_children():
            w.destroy()
        _botao(self.botoes, t("contrib_gerar"), self._gerar, destaque=not self.pacote).pack(side="left")
        if self.pacote:
            _botao(self.botoes, t("btn_pasta"), lambda: abrir(os.path.dirname(self.pacote))).pack(side="left", padx=8)
            _botao(self.botoes, t("contrib_enviar"), lambda: abrir(FORMULARIO_URL or CONTRIBUIR_URL),
                   destaque=True).pack(side="left")
        if DISCORD_URL:
            _botao(self.botoes, "Discord", lambda: abrir(DISCORD_URL)).pack(side="left", padx=8)
        _botao(self.botoes, t("fechar"), self.j.destroy).pack(side="right")

    def _gerar(self) -> None:
        if not self.v_ok.get():
            self.estado.config(text=t("contrib_falta_consentimento"), fg=AMARELO)
            return
        captura = self.rotulos.get(self.v_run.get())
        relato = {"conteudo": self.e_conteudo.get().strip(), "relato": self.t_relato.get("1.0", "end").strip(),
                  "video": self.e_video.get().strip(), "idioma": idioma.atual()}
        if not captura and not (relato["relato"] or relato["video"]):
            self.estado.config(text=t("contrib_vazio"), fg=AMARELO)
            return
        self.estado.config(text=t("contrib_lendo") if captura else t("aplicando"), fg=AMARELO)
        resultado: dict = {}
        incluir = self.v_bruta.get()

        def trabalho():
            from a2parse.contribuicao import empacotar
            try:
                resultado["caminho"] = empacotar(captura, relato, incluir)
            except Exception as e:
                resultado["erro"] = str(e)[:120]

        threading.Thread(target=trabalho, daemon=True).start()

        def esperar():
            if not self.j.winfo_exists():
                return
            if not resultado:
                self.j.after(200, esperar)
                return
            if "erro" in resultado:
                self.estado.config(text=t("contrib_erro", erro=resultado["erro"]), fg=VERMELHO)
                return
            self.pacote = resultado["caminho"]
            self.estado.config(text=t("contrib_pronto", arquivo=os.path.basename(self.pacote)), fg=VERDE)
            self._botoes()
        esperar()
