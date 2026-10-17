"""Motor de alertas de mecânica: roda sobre a curva de HP de um vídeo ou sobre uma captura.

  python alertas.py video [--masmorra "Urugugu Canyon"] [--ensaio --a-partir 6:20]
  python alertas.py pcap captura.pcapng --masmorra "Urugugu Canyon" [--bosses "A,B,C"]

No modo ensaio os alertas saem em tempo real, com som: dê play no vídeo no
mesmo instante de --a-partir e confira se o alerta chega na hora certa.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict

from a2parse.alertas import Alerta, DetectorBoss, MotorAlertas, boss, carregar_mecanicas, masmorra
from a2parse.sons import tocar
from a2parse.fontes import eventos_pcap, eventos_video, ler_tempo, mmss

RAIZ = os.path.dirname(os.path.abspath(__file__))
COR = {"azul": 94, "ambar": 33, "vermelho": 91, "roxo": 95, "verde": 92, "cinza": 37}


def colorir(texto: str, cor: str, ativo: bool) -> str:
    return f"\x1b[{COR.get(cor, 37)}m{texto}\x1b[0m" if ativo else texto


COR_NIVEL = {"info": "verde", "alerta": "ambar", "alarme": "vermelho"}   # mesma convenção do cactbot


def linha(a: Alerta, cats: dict, cor: bool) -> str:
    fase = "em breve" if a.fase == "breve" else a.nivel.upper()
    cont = f"  ⏱ {a.contagem:.1f}s" if a.contagem else ""
    return (f"{mmss(a.t):>7}  {a.boss:<24} " + colorir(f"{fase:<8}", COR_NIVEL.get(a.nivel, "cinza"), cor) + "  "
            + colorir(a.texto, cats.get(a.tipo, cats["atencao"])["cor"], cor) + f"  — {a.sub}{cont}")


class Voz:
    """Fala em português pelo sintetizador do Windows (System.Speech), num processo só, sem atraso de inicialização."""

    def __init__(self) -> None:
        import subprocess
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'pt*' } | Select-Object -First 1; "
                  "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; $s.Rate = 2; "
                  "while ($true) { $l = [Console]::In.ReadLine(); if ($l -eq $null) { break }; $s.SpeakAsyncCancelAll(); $s.SpeakAsync($l) | Out-Null }")
        try:
            self.p = subprocess.Popen(["powershell", "-NoProfile", "-Command", script], stdin=subprocess.PIPE, text=True, encoding="utf-8")
        except OSError:
            self.p = None

    def falar(self, texto: str) -> None:
        if self.p and self.p.stdin:
            self.p.stdin.write(texto.replace("\n", " ") + "\n")
            self.p.stdin.flush()

    def contagem(self, ate: float) -> None:
        """Fala 3, 2, 1 terminando em 'ate' (monotonic), como a contagem por voz do BigWigs/DBM."""
        def _c():
            for n in (3, 2, 1):
                espera = ate - n - time.monotonic()
                if espera > 0:
                    time.sleep(espera)
                self.falar(str(n))
        threading.Thread(target=_c, daemon=True).start()


# ---------------- execução ----------------

def rodar_video(dados: dict, args) -> list[Alerta]:
    mz = masmorra(dados, args.masmorra)
    if "video" not in mz:
        sys.exit(f"{mz['nome']} não tem curva de vídeo registrada no mecanicas.json.")
    curva = args.curva or os.path.join(RAIZ, "mecanicas", "historico", "urugugu_2026-10-16_hp.txt")
    motores: dict[str, MotorAlertas] = {}
    saida: list[Alerta] = []
    for ev in eventos_video(curva, mz["video"]["lutas"]):
        m = motores.get(ev.boss)
        if m is None:
            m = motores[ev.boss] = MotorAlertas(boss(dados, ev.boss), pre_aviso=not args.sem_pre_aviso,
                                                usar_observado=not args.pct_guia, tolerancia=1.0)
        if ev.tipo == "sumico":
            m.sync(ev.t, "sumico")
            saida += m.avancar(ev.t)
        else:
            saida += m.hp(ev.t, ev.valor)
    for m in motores.values():
        saida += m.avancar(float("inf"))
    if getattr(args, "mostrar_ajustes", True):
        for m in motores.values():
            for t, mec, d in m.ajustes:
                print(f"sync {mmss(t):>7}  {m.nome}: '{mec}' reancorada em {d:+.1f}s")
    return sorted(saida)


def rodar_pcap(dados: dict, args) -> tuple[list[Alerta], dict]:
    nomes = [n.strip() for n in args.bosses.split(",")] if args.bosses else [b["nome"] for b in masmorra(dados, args.masmorra)["bosses"]]
    det = DetectorBoss(nomes, hp_minimo=args.hp_minimo)
    motores: dict[str, MotorAlertas] = {}
    entidade_boss: dict[int, str] = {}
    saida: list[Alerta] = []
    diag = {"skills": defaultdict(list), "hp": defaultdict(list), "inicio": None, "sumicos": []}
    evs = eventos_pcap(args.captura, args.porta)
    if not evs:
        sys.exit("Nenhum evento de combate decodificado na captura.")
    t0 = evs[0].t
    diag["inicio"] = t0
    ultimo_hp: dict[str, float] = {}
    sumido: set[str] = set()
    for ev in evs:
        t = ev.t - t0
        for nome, th in ultimo_hp.items():
            if nome not in sumido and t - th > 1.5:
                sumido.add(nome)
                motores[nome].sync(th, "sumico")
                diag["sumicos"].append((nome, th))
        if ev.tipo == "dano":
            det.dano_recebido(ev.entidade, int(ev.valor))
        elif ev.tipo == "hp":
            det.hp(ev.entidade, int(ev.valor))
            nome = det.nome_de(ev.entidade)
            if nome:
                entidade_boss[ev.entidade] = nome
                m = motores.get(nome)
                if m is None:
                    m = motores[nome] = MotorAlertas(boss(dados, nome), pre_aviso=not args.sem_pre_aviso, usar_observado=not args.pct_guia,
                                                     modo_skills=True, eu=args.eu)
                pct = det.pct(ev.entidade, int(ev.valor))
                ultimo_hp[nome] = t
                sumido.discard(nome)
                diag["hp"][nome].append((t, pct))
                saida += m.hp(t, pct)
        elif ev.tipo == "skill" and ev.entidade in entidade_boss:
            nome = entidade_boss[ev.entidade]
            diag["skills"][nome].append((t, int(ev.valor)))
            saida += motores[nome].skill(t, int(ev.valor), ev.origem)
        for m in motores.values():
            saida += m.avancar(t)
    for m in motores.values():
        saida += m.avancar(float("inf"))
    diag["entidades"] = {n: e for e, n in entidade_boss.items()}
    diag["max_hp"] = {n: det.max_hp[e] for e, n in entidade_boss.items()}
    return sorted(saida), diag


def imprimir_diagnostico(alertas: list[Alerta], diag: dict) -> None:
    print("\n== Diagnóstico (para mapear skills e o sumiço do boss)")
    for nome, ent in diag["entidades"].items():
        hp = diag["hp"][nome]
        print(f"\n{nome}: entidade {ent}, maior HP visto {diag['max_hp'][nome]:,}".replace(",", "."))
        if hp:
            print(f"  luta de {mmss(hp[0][0])} a {mmss(hp[-1][0])}, {len(hp)} pacotes de HP")
            buracos = [(a[0], b[0]) for a, b in zip(hp, hp[1:]) if b[0] - a[0] > 3]
            for a, b in buracos:
                print(f"  sem HP por {b - a:.1f}s ({mmss(a)} → {mmss(b)}): candidato a boss fora da tela")
        sk = diag["skills"][nome]
        cont = Counter(s for _, s in sk)
        if cont:
            print("  skills usadas: " + ", ".join(f"{s}×{n}" for s, n in cont.most_common(12)))
        for a in alertas:
            if a.boss == nome and a.fase == "ativo" and a.passo == 0:
                perto = [f"{s}@{t - a.t:+.1f}s" for t, s in sk if -5 <= t - a.t <= 25]
                if perto:
                    print(f"  perto de '{a.texto}' ({mmss(a.t)}): " + ", ".join(perto))


def ensaio(alertas: list[Alerta], cats: dict, a_partir: float, cor: bool, voz: Voz | None) -> None:
    print(f"\nEnsaio: dê play no vídeo em {mmss(a_partir)} e aperte Enter no mesmo instante.")
    input()
    inicio = time.monotonic() - a_partir
    for a in alertas:
        if a.t < a_partir:
            continue
        espera = a.t - (time.monotonic() - inicio)
        if espera > 0:
            time.sleep(espera)
        print(linha(a, cats, cor))
        if a.fase != "ativo":
            continue
        if voz and a.nivel != "info":
            voz.falar(a.voz or a.texto.capitalize())
            if a.contagem_voz and a.contagem:
                voz.contagem(time.monotonic() + a.contagem)
        else:
            tocar(cats.get(a.tipo, cats["atencao"])["som"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.system("")  # liga as cores ANSI no console do Windows
    ap = argparse.ArgumentParser(description="Motor de alertas de mecânica do Aion 2.")
    sub = ap.add_subparsers(dest="modo", required=True)
    for nome in ("video", "pcap"):
        p = sub.add_parser(nome)
        if nome == "pcap":
            p.add_argument("captura")
            p.add_argument("--porta", type=int)
            p.add_argument("--bosses", help="nomes na ordem em que aparecem, separados por vírgula")
            p.add_argument("--hp-minimo", type=int, default=1_000_000, help="HP mínimo para uma entidade contar como boss")
            p.add_argument("--eu", type=int, help="ID da sua entidade (liga os alertas pessoais); o analisar.py mostra quem é quem")
        else:
            p.add_argument("--curva", help="arquivo da curva de HP medida no vídeo")
        p.add_argument("--masmorra", default="Urugugu Canyon")
        p.add_argument("--mecanicas", help="caminho alternativo do mecanicas.json")
        p.add_argument("--sem-pre-aviso", action="store_true")
        p.add_argument("--pct-guia", action="store_true", help="usa o % dos guias mesmo quando há % observado em vídeo")
        p.add_argument("--ensaio", action="store_true", help="solta os alertas em tempo real, com som")
        p.add_argument("--voz", action="store_true", help="no ensaio, fala a ação em português e conta 3-2-1")
        p.add_argument("--a-partir", default="0:00", help="tempo inicial do ensaio (m:s)")
        p.add_argument("--jsonl", help="grava os alertas neste arquivo, um JSON por linha")
        p.add_argument("--sem-cor", action="store_true")
    args = ap.parse_args()

    dados = carregar_mecanicas(args.mecanicas)
    cats = dados["categorias_alerta"]
    cor = not args.sem_cor
    if args.modo == "video":
        alertas, diag = rodar_video(dados, args), None
    else:
        alertas, diag = rodar_pcap(dados, args)

    if args.jsonl:
        with open(args.jsonl, "w", encoding="utf-8") as f:
            for a in alertas:
                f.write(json.dumps(a.__dict__, ensure_ascii=False) + "\n")

    if args.ensaio:
        ensaio(alertas, cats, ler_tempo(args.a_partir), cor, Voz() if args.voz else None)
    else:
        print(f"== {len(alertas)} alertas")
        for a in alertas:
            print(linha(a, cats, cor))
        if diag:
            imprimir_diagnostico(alertas, diag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
