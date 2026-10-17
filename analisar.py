"""Analisa uma captura .pcap/.pcapng do Aion 2.

Uso básico:
  python analisar.py captura.pcapng

Mais opções: python analisar.py --help
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import struct
import sys
from collections import Counter

from a2parse.analise import Analise
from a2parse.protocolo import OPCODES


def carregar_nomes(pasta: str | None) -> tuple[dict[int, str], dict[int, str]]:
    skills, npcs = {}, {}
    if not pasta:
        return skills, npcs
    caminho = os.path.join(pasta, "skills.json")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            skills = {int(k): v for k, v in json.load(f).items()}
    caminho = os.path.join(pasta, "npcs.json")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            npcs = {int(k): v.get("name", "") for k, v in json.load(f).items()}
    return skills, npcs


def fmt(n: float) -> str:
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return f"{n:.0f}"


def pct(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}%" if b else "—"


def nome_op(op: int) -> str:
    return OPCODES.get(op, "CompressedBundle" if op == 0xFFFF else "?")


def tabela(linhas: list[list[str]], cabecalho: list[str]) -> str:
    todas = [cabecalho] + linhas
    larguras = [max(len(str(l[i])) for l in todas) for i in range(len(cabecalho))]
    saida = []
    for j, l in enumerate(todas):
        saida.append("  ".join(str(c).ljust(larguras[i]) if i == 0 else str(c).rjust(larguras[i]) for i, c in enumerate(l)))
        if j == 0:
            saida.append("  ".join("-" * w for w in larguras))
    return "\n".join(saida)


def codificacoes_numero(n: int) -> list[tuple[str, bytes]]:
    cods = []
    for nome, fmt_s, maximo in (("u16", "<H", 0xFFFF), ("u32", "<I", 0xFFFFFFFF), ("u64", "<Q", 2**64 - 1)):
        if 0 <= n <= maximo:
            cods.append((nome, struct.pack(fmt_s, n)))
    v, b = n, bytearray()
    while True:
        if v < 0x80:
            b.append(v)
            break
        b.append((v & 0x7F) | 0x80)
        v >>= 7
    cods.append(("varint", bytes(b)))
    return cods


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Analisa capturas de rede do Aion 2 (layouts em docs/PROTOCOLO.md).")
    ap.add_argument("captura", help="arquivo .pcap ou .pcapng")
    ap.add_argument("--porta", type=int, help="só considera conexões com esta porta TCP")
    ap.add_argument("--dados", help="pasta com skills.json e npcs.json, para mostrar nomes")
    ap.add_argument("--log", metavar="ARQ", help="grava cada mensagem decodificada neste arquivo texto")
    ap.add_argument("--csv", metavar="ARQ", help="grava os eventos de dano neste CSV")
    ap.add_argument("--amostras", metavar="OPCODE", help="mostra payloads em hex deste opcode (ex.: 0x3645)")
    ap.add_argument("--max-amostras", type=int, default=15)
    ap.add_argument("--procurar-numero", type=int, metavar="N", help="procura N nos payloads como u16/u32/u64/varint")
    ap.add_argument("--procurar-texto", metavar="TXT", help="procura TXT nos payloads em UTF-8 e UTF-16")
    ap.add_argument("--casts", action="store_true", help="lista os casts (0x3802) de entidades que não são jogadores")
    args = ap.parse_args()

    skills, _npcs = carregar_nomes(args.dados)
    nome_skill = lambda c: skills.get(c) or skills.get(c // 10000 * 10000) or str(c)

    amostra_op = int(args.amostras, 16) if args.amostras else None
    amostras: list[str] = []
    buscas = []
    if args.procurar_numero is not None:
        buscas += [(f"{args.procurar_numero} como {n}", b) for n, b in codificacoes_numero(args.procurar_numero)]
    if args.procurar_texto:
        buscas += [(f'"{args.procurar_texto}" UTF-8', args.procurar_texto.encode("utf-8")),
                   (f'"{args.procurar_texto}" UTF-16', args.procurar_texto.encode("utf-16-le"))]
    achados: dict[tuple[str, int], list[int]] = {}
    log = open(args.log, "w", encoding="utf-8") if args.log else None

    def observador(ts, fluxo, prof, op, payload, resultado):
        if amostra_op == op and len(amostras) < args.max_amostras:
            amostras.append(f"{ts:.3f}  {len(payload):5d} B  {payload.hex(' ')}")
        for rotulo, agulha in buscas:
            p = payload.find(agulha)
            if p >= 0:
                achados.setdefault((rotulo, op), []).append(p)
        if log:
            pre = "  " * prof
            if resultado is None:
                txt = f"(sem decoder) {len(payload)} B"
            elif resultado[0] == "ok":
                txt = " ".join(f"{k}={v}" for k, v in resultado[1].items())
            else:
                txt = f"{resultado[0]}: {resultado[1]}"
            log.write(f"{ts:.3f} {pre}0x{op:04X} {nome_op(op):<22} {txt}\n")

    a = Analise(porta=args.porta, observador=observador)
    a.processar_arquivo(args.captura)
    if log:
        log.close()

    # ---------- fluxos ----------
    print("== Conexões TCP")
    linhas = []
    for f in sorted(a.fluxos.values(), key=lambda f: -f.bytes)[:12]:
        o, po, d, pd = f.chave
        linhas.append([f"{o}:{po} → {d}:{pd}", fmt(f.bytes), f.mensagens, f.conhecidas,
                       "jogo" if f.parece_jogo else ("ignorado" if f.framer.desistiu else "—"),
                       f.framer.sincronizacoes, f.remontador.buracos])
    print(tabela(linhas, ["fluxo", "bytes", "msgs", "conhecidas", "status", "sincr.", "buracos"]))
    jogo = a.fluxos_do_jogo()
    if not jogo:
        print("\nNenhuma conexão com opcodes do Aion 2 foi encontrada. Confira se a captura foi feita com o jogo aberto e em combate.")
        return 1

    # ---------- opcodes ----------
    print("\n== Mensagens por opcode")
    linhas = []
    for op, n in a.opcodes.most_common(40):
        linhas.append([f"0x{op:04X}", nome_op(op), n, fmt(a.bytes_opcode[op]), a.descartadas.get(op, 0), a.erros.get(op, 0)])
    print(tabela(linhas, ["opcode", "tipo", "qtd", "bytes", "descart.", "erros"]))
    if a.blocos:
        print(f"\nBlocos 0xFFFF: {a.blocos}, {fmt(a.bytes_comprimidos)} comprimidos → {fmt(a.bytes_descomprimidos)} descomprimidos")
    for op, msg in a.exemplo_erro.items():
        print(f"  erro em 0x{op:04X} ({nome_op(op)}): {msg}")

    # ---------- dano ----------
    if a.fontes:
        print("\n== Dano por entidade (0x3804 + 0x3805)")
        jogadores = a.jogadores()
        total = sum(f.dano for f in a.fontes.values())
        linhas = []
        for fid, f in sorted(a.fontes.items(), key=lambda kv: -kv[1].dano):
            dur = max(1.0, f.ultimo - f.primeiro)
            classe = "jogador" if fid in jogadores else "npc/pet"
            linhas.append([fid, classe, fmt(f.dano), fmt(f.dano / dur), pct(f.dano, total), f.hits,
                           pct(f.criticos, f.hits), pct(f.costas, f.hits), pct(f.double, f.hits), fmt(f.dano_dot), fmt(f.multi_hit)])
        print(tabela(linhas[:20], ["entidade", "tipo", "dano", "DPS*", "% dano", "hits", "crít.", "costas", "double", "DoT", "multi-hit"]))
        print("* DPS do primeiro ao último golpe dessa entidade nesta captura.")
        top = sorted(a.fontes.items(), key=lambda kv: -kv[1].dano)[:3]
        for fid, f in top:
            print(f"\n  Skills de {fid}:")
            linhas = [[nome_skill(s), fmt(d), f.hits_por_skill[s], pct(d, f.dano)] for s, d in f.skills.most_common(10)]
            print("  " + tabela(linhas, ["skill", "dano", "hits", "%"]).replace("\n", "\n  "))

    if a.alvos:
        print("\n== Alvos que mais receberam dano")
        linhas = []
        for aid, d in a.alvos.most_common(10):
            hpmax = a.hp_max.get(aid)
            linhas.append([aid, fmt(d), fmt(hpmax) if hpmax else "—", fmt(a.hp_atual[aid]) if aid in a.hp_atual else "—",
                           "sim" if aid in a.mortes else "não"])
        print(tabela(linhas, ["entidade", "dano recebido", "maior HP visto", "último HP", "morreu"]))

    if a.combat_power:
        ts, cp, mx = a.combat_power[-1]
        print(f"\nSeu Combat Power (0x3656): {cp:,} (máximo {mx:,})".replace(",", "."))

    # ---------- casts ----------
    if args.casts:
        jogadores = a.jogadores()
        npc = [c for c in a.casts if c[1] not in jogadores]
        print(f"\n== Casts de NPCs (0x3802): {len(npc)} de {len(a.casts)}")
        if npc:
            t0 = npc[0][0]
            for ts, conj, sk, alvo, cd in npc[:200]:
                print(f"  +{ts - t0:7.2f}s  conjurador {conj:<8} skill {sk:<10} {nome_skill(sk):<30} alvo {alvo:<8} cooldown {cd} ms")

    # ---------- descoberta ----------
    if amostras:
        print(f"\n== Amostras de 0x{amostra_op:04X} ({nome_op(amostra_op)})")
        print("\n".join(amostras))
    elif amostra_op is not None:
        print(f"\nNenhuma mensagem 0x{amostra_op:04X} na captura.")
    if buscas:
        print("\n== Busca nos payloads")
        if not achados:
            print("  nada encontrado")
        for (rotulo, op), offs in sorted(achados.items(), key=lambda kv: -len(kv[1])):
            comuns = ", ".join(f"{o}" for o, _ in Counter(offs).most_common(3))
            print(f"  {rotulo:<28} em 0x{op:04X} {nome_op(op):<22} {len(offs)}×  offsets mais comuns: {comuns}")

    if args.csv and a.eventos_dano:
        campos = sorted({k for e in a.eventos_dano for k in e})
        campos.remove("ts")
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts"] + campos)
            w.writeheader()
            w.writerows(a.eventos_dano)
        print(f"\n{len(a.eventos_dano)} eventos de dano gravados em {args.csv}")
    if args.log:
        print(f"Log de mensagens gravado em {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
