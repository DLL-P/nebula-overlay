"""Grava o tráfego TCP do Aion 2 num arquivo .pcap, usando o Npcap já instalado.

  python gravar.py                       grava até você apertar Ctrl+C
  python gravar.py --segundos 30         grava 30 s e para sozinho
  python gravar.py --listar              mostra as placas de rede

Só lê o tráfego que já chega ao seu PC: não envia nada, não toca no jogo.
Durante a gravação mostra se encontrou a conexão do jogo e quantas mensagens
de dano já viu, para você saber que está funcionando.
"""

from __future__ import annotations

import argparse
import ctypes as C
import datetime as dt
import json
import os
import struct
import socket
import sys
import time

from a2parse.captura import SYN, Remontador, _decodificar
from a2parse.protocolo import BLOCO, OPCODES, FramerFluxo, mensagens_do_bloco

from a2parse.caminhos import usuario

PASTA = usuario("capturas")
FILTRO_PADRAO = "tcp and not port 443 and not port 80"   # tráfego web fica de fora; o jogo não usa essas portas


# ---------------- Npcap (wpcap.dll) ----------------

class sockaddr(C.Structure):
    _fields_ = [("sa_family", C.c_ushort), ("sa_data", C.c_ubyte * 14)]


class pcap_addr(C.Structure):
    pass


pcap_addr._fields_ = [("next", C.POINTER(pcap_addr)), ("addr", C.POINTER(sockaddr)), ("netmask", C.POINTER(sockaddr)),
                      ("broadaddr", C.POINTER(sockaddr)), ("dstaddr", C.POINTER(sockaddr))]


class pcap_if(C.Structure):
    pass


pcap_if._fields_ = [("next", C.POINTER(pcap_if)), ("name", C.c_char_p), ("description", C.c_char_p),
                    ("addresses", C.POINTER(pcap_addr)), ("flags", C.c_uint)]


class timeval(C.Structure):
    _fields_ = [("tv_sec", C.c_long), ("tv_usec", C.c_long)]


class pcap_pkthdr(C.Structure):
    _fields_ = [("ts", timeval), ("caplen", C.c_uint32), ("len", C.c_uint32)]


class pcap_stat(C.Structure):
    _fields_ = [("ps_recv", C.c_uint), ("ps_drop", C.c_uint), ("ps_ifdrop", C.c_uint)]


class bpf_program(C.Structure):
    _fields_ = [("bf_len", C.c_uint), ("bf_insns", C.c_void_p)]


class ErroCaptura(Exception):
    """Problema para abrir a captura. 'chave' é o texto da interface (a2parse/idioma.py)."""

    def __init__(self, chave: str, mensagem: str, **valores) -> None:
        super().__init__(mensagem)
        self.chave, self.valores = chave, valores


def sou_admin() -> bool:
    try:
        return bool(C.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


class CapturaWindows:
    """Sem Npcap: o socket bruto do próprio Windows (SIO_RCVALL), que precisa de administrador.

    Fica no IP da placa que o jogo usa ou, com acelerador, no 127.0.0.1 (o mesmo lugar onde o Npcap olharia).
    RCVALL_IPLEVEL recebe só o tráfego deste PC, sem modo promíscuo. Entrega pacotes IPv4 inteiros (IP cru).
    """
    LINKTYPE = 101                       # IP cru, como no pcap
    RCVALL_IPLEVEL = 3
    PORTAS_WEB = (80, 443)

    def __init__(self, ip: str, porta: int | None = None) -> None:
        import socket
        self.porta = porta
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
            s.bind((ip, 0))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            try:
                s.ioctl(socket.SIO_RCVALL, self.RCVALL_IPLEVEL)
            except OSError:
                s.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
            s.settimeout(0.1)
        except OSError as e:
            raise ErroCaptura("erro_windows", f"Não consegui capturar pelo Windows: {e}", erro=str(e))
        self.s = s

    def aceita(self, d: bytes) -> bool:
        """TCP sobre IPv4: com acelerador, só a porta do proxy; direto, tudo menos a web (mesmo filtro do Npcap)."""
        if len(d) < 24 or d[0] >> 4 != 4 or d[9] != 6:
            return False
        ihl = (d[0] & 0x0F) * 4
        if len(d) < ihl + 4:
            return False
        origem, destino = struct.unpack_from(">HH", d, ihl)
        if self.porta is not None:
            return self.porta in (origem, destino)
        return origem not in self.PORTAS_WEB and destino not in self.PORTAS_WEB

    def ler(self) -> bytes | None:
        """O próximo pacote do jogo, ou None (nada em 0,1 s ou pacote de outro programa). OSError: a captura caiu."""
        import socket
        try:
            d = self.s.recv(65535)
        except socket.timeout:
            return None
        return d if self.aceita(d) else None

    def fechar(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass


def carregar_wpcap():
    pasta = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "Npcap")
    if hasattr(os, "add_dll_directory") and os.path.isdir(pasta):
        os.add_dll_directory(pasta)
    try:
        w = C.CDLL(os.path.join(pasta, "wpcap.dll"))
    except OSError:
        raise ErroCaptura("erro_npcap", "Não achei o Npcap (wpcap.dll). Instale o Npcap em npcap.com.")
    vp, cp = C.c_void_p, C.c_char_p
    w.pcap_findalldevs.argtypes = [C.POINTER(C.POINTER(pcap_if)), cp]
    w.pcap_freealldevs.argtypes = [C.POINTER(pcap_if)]
    w.pcap_open_live.argtypes = [cp, C.c_int, C.c_int, C.c_int, cp]
    w.pcap_open_live.restype = vp
    w.pcap_datalink.argtypes = [vp]
    w.pcap_compile.argtypes = [vp, C.POINTER(bpf_program), cp, C.c_int, C.c_uint32]
    w.pcap_setfilter.argtypes = [vp, C.POINTER(bpf_program)]
    w.pcap_freecode.argtypes = [C.POINTER(bpf_program)]
    w.pcap_geterr.argtypes = [vp]
    w.pcap_geterr.restype = cp
    w.pcap_next_ex.argtypes = [vp, C.POINTER(C.POINTER(pcap_pkthdr)), C.POINTER(C.POINTER(C.c_ubyte))]
    w.pcap_dump_open.argtypes = [vp, cp]
    w.pcap_dump_open.restype = vp
    w.pcap_dump.argtypes = [vp, C.POINTER(pcap_pkthdr), C.POINTER(C.c_ubyte)]
    w.pcap_dump_flush.argtypes = [vp]
    w.pcap_dump_close.argtypes = [vp]
    w.pcap_close.argtypes = [vp]
    w.pcap_lib_version.restype = cp
    w.pcap_setbuff.argtypes = [vp, C.c_int]
    w.pcap_stats.argtypes = [vp, C.POINTER(pcap_stat)]
    return w


BUFFER = 16 * 1024 * 1024   # buffer do driver: o padrão (1 MB) perde pacotes nos picos de tráfego do jogo


def buffer_grande(w, h) -> None:
    try:
        w.pcap_setbuff(h, BUFFER)
    except Exception:
        pass


def descartados(w, h) -> int | None:
    """Pacotes que o Npcap jogou fora por buffer cheio (cada um vira um buraco no fluxo)."""
    st = pcap_stat()
    try:
        return st.ps_drop if w.pcap_stats(h, C.byref(st)) == 0 else None
    except Exception:
        return None


def placas(w) -> list[dict]:
    lst = C.POINTER(pcap_if)()
    erro = C.create_string_buffer(256)
    if w.pcap_findalldevs(C.byref(lst), erro) != 0:
        texto = erro.value.decode(errors="replace")
        raise ErroCaptura("erro_abrir", "Erro ao listar placas de rede: " + texto, erro=texto)
    saida, p = [], lst
    while p:
        d = p.contents
        ips, a = [], d.addresses
        while a:
            if a.contents.addr and a.contents.addr.contents.sa_family == 2:  # AF_INET
                ips.append(".".join(str(b) for b in a.contents.addr.contents.sa_data[2:6]))
            a = a.contents.next
        saida.append({"nome": d.name.decode(), "descricao": (d.description or b"").decode(errors="replace"), "ips": ips})
        p = d.next
    w.pcap_freealldevs(lst)
    return saida


def ip_local() -> str | None:
    """IP da placa que sai para a internet. Um socket UDP 'conectado' não envia nenhum pacote."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


# ---------------- rota do jogo (direto ou por acelerador) ----------------

def _cmd(args: list[str]) -> str:
    import subprocess
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding="mbcs", errors="replace", timeout=15,
                              creationflags=0x08000000).stdout       # sem janela de console (app instalado)
    except (OSError, subprocess.SubprocessError):
        return ""


class _Processo(C.Structure):
    import ctypes.wintypes as _W
    _fields_ = [("dwSize", _W.DWORD), ("cntUsage", _W.DWORD), ("th32ProcessID", _W.DWORD),
                ("th32DefaultHeapID", C.c_void_p), ("th32ModuleID", _W.DWORD), ("cntThreads", _W.DWORD),
                ("th32ParentProcessID", _W.DWORD), ("pcPriClassBase", C.c_long), ("dwFlags", _W.DWORD),
                ("szExeFile", C.c_wchar * 260)]


def pids_de(nome_exe: str) -> dict[int, str]:
    """PIDs de um executável (ou de todos, com nome_exe=''). Lista de processos do Windows, sem abrir programa."""
    k = C.windll.kernel32
    k.CreateToolhelp32Snapshot.restype = C.c_void_p
    snap = k.CreateToolhelp32Snapshot(0x2, 0)                  # TH32CS_SNAPPROCESS
    out: dict[int, str] = {}
    if not snap or snap == C.c_void_p(-1).value:
        return out
    try:
        pe = _Processo()
        pe.dwSize = C.sizeof(_Processo)
        ok = k.Process32FirstW(C.c_void_p(snap), C.byref(pe))
        while ok:
            if not nome_exe or pe.szExeFile.lower() == nome_exe.lower():
                out[pe.th32ProcessID] = pe.szExeFile
            ok = k.Process32NextW(C.c_void_p(snap), C.byref(pe))
    finally:
        k.CloseHandle(C.c_void_p(snap))
    return out


def rota_do_jogo() -> dict | None:
    """Descobre se o Aion 2 fala com um proxy local (ExitLag, NoPing, GearUP...).

    Com acelerador, o tráfego que sai pela placa de rede vem embrulhado no túnel
    do acelerador. O tráfego limpo do jogo passa antes pelo loopback, entre o
    AION2.exe e o proxy, e é ali que a gravação tem de acontecer.
    """
    jogo = pids_de("AION2.exe")
    if not jogo:
        return None
    escutando, ligacoes = {}, []
    for linha in _cmd(["netstat", "-ano", "-p", "TCP"]).splitlines():
        p = linha.split()
        if len(p) != 5 or p[0] != "TCP" or not p[4].isdigit():
            continue
        local, remoto, estado, pid = p[1], p[2], p[3], int(p[4])
        if estado == "LISTENING":
            escutando[int(local.rsplit(":", 1)[1])] = pid
        elif estado == "ESTABLISHED" and pid in jogo:
            ligacoes.append((local, remoto))
    for local, remoto in ligacoes:
        ip, porta = remoto.rsplit(":", 1)
        dono = escutando.get(int(porta))
        if ip == "127.0.0.1" and dono is not None and dono not in jogo:
            nome = pids_de("").get(dono, f"PID {dono}")
            return {"proxy": nome, "porta": int(porta), "conexoes": len(ligacoes)}
    # sem acelerador: os IPs locais das conexões do jogo dizem qual placa ele usa (VPN, cabo + Wi-Fi...)
    ips = sorted({local.rsplit(":", 1)[0] for local, remoto in ligacoes if not remoto.startswith(("127.", "["))})
    return {"proxy": None, "conexoes": len(ligacoes), "ips_locais": ips}   # conexoes 0: ainda não conectou


def escolher_placa(lista: list[dict], rota: dict | None, forcada: str | None = None) -> dict | None:
    """Placa a gravar: a forçada (parte do nome ou da descrição, "placa" no overlay.json), o loopback quando o
    jogo passa por um proxy local, a placa com o IP local das conexões do jogo ou, por último, a da rota padrão."""
    if forcada:
        alvo = forcada.lower()
        return next((p for p in lista if alvo in (p["descricao"] + " " + p["nome"]).lower()), None)
    if rota and rota.get("proxy"):
        return next((p for p in lista if "loopback" in (p["descricao"] + p["nome"]).lower()), None)
    for ip in (rota or {}).get("ips_locais", []) + [ip_local()]:
        placa = next((p for p in lista if ip and ip in p["ips"]), None)
        if placa:
            return placa
    return None


# ---------------- detecção do jogo ao vivo ----------------

class Detector:
    def __init__(self) -> None:
        self.fluxos: dict[tuple, list] = {}
        self.danos = 0

    def pacote(self, linktype: int, dados: bytes, ts: float) -> None:
        seg = _decodificar(linktype, dados, ts)
        if seg is None:
            return
        f = self.fluxos.get(seg.fluxo)
        if f is None:
            f = self.fluxos[seg.fluxo] = [Remontador(), FramerFluxo(), 0]
        rem, fr, _ = f
        for bloco, buraco in rem.push(seg.seq, seg.dados, bool(seg.flags & SYN)):
            for op, payload in fr.alimentar(bloco, buraco):
                if op == BLOCO:
                    try:
                        filhas = mensagens_do_bloco(payload)
                    except ValueError:
                        continue
                    f[2] += 1 + len(filhas)
                    self.danos += sum(1 for o, _ in filhas if o in (0x3804, 0x3805))
                elif op in OPCODES:
                    f[2] += 1
                    self.danos += op in (0x3804, 0x3805)

    def jogo(self):
        if not self.fluxos:
            return None
        chave, f = max(self.fluxos.items(), key=lambda kv: kv[1][2])
        return (chave, f[2]) if f[2] >= 5 else None


# ---------------- main ----------------

def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Grava o tráfego TCP do Aion 2 com o Npcap.")
    ap.add_argument("--saida", help="arquivo .pcap (padrão: capturas/captura_DATA_HORA.pcap)")
    ap.add_argument("--placa", type=int, help="número da placa (veja --listar); padrão: a que sai para a internet")
    ap.add_argument("--listar", action="store_true", help="lista as placas de rede e sai")
    ap.add_argument("--segundos", type=float, help="para sozinho depois desse tempo")
    ap.add_argument("--filtro", default=FILTRO_PADRAO, help=f'filtro BPF (padrão: "{FILTRO_PADRAO}")')
    ap.add_argument("--tudo", action="store_true", help='grava todo o TCP (filtro "tcp")')
    ap.add_argument("--sem-auto", action="store_true", help="não procura acelerador (ExitLag etc.); usa a placa de internet")
    args = ap.parse_args()

    try:
        w = carregar_wpcap()
        lista = placas(w)
    except ErroCaptura as e:
        sys.exit(str(e))
    if args.listar:
        for i, p in enumerate(lista):
            print(f"{i:2d}  {p['descricao'] or p['nome']}  {', '.join(p['ips']) or '(sem IPv4)'}")
        return 0

    filtro = "tcp" if args.tudo else args.filtro
    rota = None if (args.placa is not None or args.sem_auto) else rota_do_jogo()
    if rota is None and args.placa is None and not args.sem_auto:
        print("Aviso: o AION2.exe não está aberto. Abra o jogo antes, ou a gravação pode não pegar a conexão certa.")
    if args.placa is not None:
        placa = lista[args.placa]
    elif rota and rota.get("proxy"):
        placa = escolher_placa(lista, rota)
        if placa is None:
            sys.exit("O jogo passa por um proxy local, mas o Npcap não tem a placa de loopback. Reinstale o Npcap com "
                     "a opção 'Support loopback traffic' marcada.")
        filtro = f"tcp port {rota['porta']}"
        print(f"O jogo passa pelo {rota['proxy']} (proxy local na porta {rota['porta']}).")
        print("Gravando o loopback, antes do túnel do acelerador, onde o tráfego do jogo vem limpo.\n")
    else:
        placa = escolher_placa(lista, rota)
        if placa is None:
            print("Não consegui escolher a placa sozinho. Rode com --listar e depois --placa N.")
            return 1

    erro = C.create_string_buffer(256)
    h = w.pcap_open_live(placa["nome"].encode(), 65535, 0, 100, erro)
    if h:
        buffer_grande(w, h)
    if not h:
        sys.exit("Não consegui abrir a placa: " + erro.value.decode(errors="replace")
                 + "\nSe o Npcap estiver configurado só para administrador, abra o terminal como administrador.")
    prog = bpf_program()
    if w.pcap_compile(h, C.byref(prog), filtro.encode(), 1, 0xFFFFFFFF) != 0 or w.pcap_setfilter(h, C.byref(prog)) != 0:
        sys.exit("Filtro inválido: " + (w.pcap_geterr(h) or b"").decode(errors="replace"))
    w.pcap_freecode(C.byref(prog))
    linktype = w.pcap_datalink(h)

    inicio = dt.datetime.now()
    os.makedirs(PASTA, exist_ok=True)
    saida = args.saida or os.path.join(PASTA, f"captura_{inicio:%Y-%m-%d_%H-%M-%S}.pcap")
    dumper = w.pcap_dump_open(h, os.path.abspath(saida).encode("mbcs"))
    if not dumper:
        sys.exit("Não consegui criar o arquivo: " + (w.pcap_geterr(h) or b"").decode(errors="replace"))
    info = {"arquivo": os.path.basename(saida), "inicio_local": inicio.isoformat(timespec="milliseconds"),
            "inicio_epoch": inicio.timestamp(), "placa": placa["descricao"] or placa["nome"], "ips": placa["ips"],
            "filtro": filtro, "npcap": w.pcap_lib_version().decode(errors="replace")}

    print(f"Gravando em {saida}")
    print(f"Placa: {info['placa']} ({', '.join(placa['ips'])}) · filtro: {filtro}")
    print(f"Início: {inicio:%H:%M:%S}  ← se for gravar vídeo, anote essa hora (ou comece o vídeo agora)")
    print("Ctrl+C para parar.\n")

    det = Detector()
    hdr, dados = C.POINTER(pcap_pkthdr)(), C.POINTER(C.c_ubyte)()
    n = bytes_ = 0
    t0 = ultimo_status = time.monotonic()
    try:
        while True:
            r = w.pcap_next_ex(h, C.byref(hdr), C.byref(dados))
            agora = time.monotonic()
            if r == 1:
                w.pcap_dump(dumper, hdr, dados)
                cap = hdr.contents.caplen
                n += 1
                bytes_ += cap
                ts = hdr.contents.ts.tv_sec + hdr.contents.ts.tv_usec / 1e6
                try:
                    det.pacote(linktype, C.string_at(dados, cap), ts)
                except Exception:
                    pass  # um pacote estranho não pode parar a gravação
            elif r < 0:
                print("\nA captura foi interrompida: " + (w.pcap_geterr(h) or b"").decode(errors="replace"))
                break
            if agora - ultimo_status >= 2:
                ultimo_status = agora
                w.pcap_dump_flush(dumper)
                jogo = det.jogo()
                status = (f"jogo: {jogo[0][0]}:{jogo[0][1]} · {jogo[1]} mensagens · {det.danos} de dano"
                          if jogo else "procurando o jogo… (entre/troque de zona ou bata em algo)")
                print(f"\r{int(agora - t0) // 60:02d}:{int(agora - t0) % 60:02d}  {n} pacotes  {bytes_ / 1e6:5.1f} MB  {status}      ",
                      end="", flush=True)
            if args.segundos and agora - t0 >= args.segundos:
                break
    except KeyboardInterrupt:
        pass
    finally:
        perdidos = descartados(w, h)
        w.pcap_dump_close(dumper)
        w.pcap_close(h)
        if perdidos:
            print(f"\nAtenção: o Npcap descartou {perdidos} pacotes (buffer cheio).")

    fim = dt.datetime.now()
    jogo = det.jogo()
    info.update(fim_local=fim.isoformat(timespec="milliseconds"), pacotes=n, bytes=bytes_,
                jogo=f"{jogo[0][0]}:{jogo[0][1]}" if jogo else None, mensagens_jogo=jogo[1] if jogo else 0,
                mensagens_dano=det.danos)
    with open(os.path.splitext(saida)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"\n\nSalvo: {saida} ({bytes_ / 1e6:.1f} MB, {n} pacotes, {fim - inicio})")
    if jogo:
        print(f"Conexão do jogo: {info['jogo']} · {jogo[1]} mensagens reconhecidas · {det.danos} de dano")
        print("\nPróximo passo:")
        print(f'  python analisar.py "{saida}" --dados dados --casts')
        print(f'  python alertas.py pcap "{saida}"')
    else:
        print("Não reconheci tráfego do Aion 2 nesta gravação. O jogo estava aberto e você entrou/trocou de zona?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
