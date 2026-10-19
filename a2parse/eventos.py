"""Eventos de campo (Festival Shugo e outros): o que vem a seguir e o que está aberto agora.

Duas fontes:
- a agenda (mecanicas/eventos.json): regras como "toda hora em :00" ou "às 21:00 de terça e sábado".
  É ela que permite avisar antes, porque o servidor só manda o evento quando ele abre;
- o servidor: 0x6001 avisa cada troca de fase de um evento, com o horário de início, o início da fase e o fim
  da fase; 0x6000 é a lista dos eventos abertos ao entrar numa zona. Isso confirma a agenda e dá o fim exato.

Os horários são do relógio do servidor (0x3600), então valem mesmo com o relógio do PC errado.
"""

from __future__ import annotations

import datetime as dt
import json
import struct
from dataclasses import dataclass, field

from .caminhos import app, usuario


# ---------------- pacotes ----------------

def _varint(b: bytes, i: int) -> tuple[int, int]:
    v = s = 0
    while True:
        if i >= len(b) or s > 35:
            raise ValueError("varint")
        x = b[i]
        i += 1
        v |= (x & 0x7F) << s
        s += 7
        if x < 0x80:
            return v, i


def _registro(b: bytes, i: int) -> tuple[dict, int]:
    """varint evento | u8 fase | i64 início | i64 início da fase | i64 fim da fase (ms desde 1970)."""
    ev, i = _varint(b, i)
    fase = b[i]
    inicio, inicio_fase, fim_fase = struct.unpack_from("<qqq", b, i + 1)
    for ms in (inicio, inicio_fase, fim_fase):
        if not 1_600_000_000_000 < ms < 4_000_000_000_000:
            raise ValueError("horário fora do esperado")
    return {"evento": ev, "fase": fase, "inicio": inicio / 1000, "inicio_fase": inicio_fase / 1000,
            "fim_fase": fim_fase / 1000}, i + 25


def ler_evento(p: bytes) -> dict | None:
    """0x6001 FieldEventChanged: u8 tipo | registro (29 bytes no total)."""
    try:
        r, _ = _registro(p, 1)
        r["tipo"] = p[0]
        return r
    except (ValueError, IndexError, struct.error):
        return None


def ler_lista(p: bytes) -> list[dict]:
    """0x6000 FieldEventInfo: varint quantidade | registros (só vista vazia; o resto é tentativa, com checagem)."""
    try:
        n, i = _varint(p, 0)
        saida = []
        for _ in range(min(n, 64)):
            r, i = _registro(p, i)
            saida.append(r)
        return saida
    except (ValueError, IndexError, struct.error):
        return []


# ---------------- agenda ----------------

def carregar() -> list[dict]:
    """Eventos do programa e, por cima (mesma "chave"), os seus: Documentos/Nebula Overlay/mecanicas/eventos.json."""
    eventos: dict[str, dict] = {}
    for caminho in (app("mecanicas", "eventos.json"), usuario("mecanicas", "eventos.json")):
        try:
            with open(caminho, encoding="utf-8") as f:
                for e in json.load(f).get("eventos", []):
                    eventos[e["chave"]] = e
        except (OSError, ValueError, KeyError):
            pass
    return list(eventos.values())


def _fuso(texto: str) -> dt.timezone:
    """"-03:00" → UTC−3."""
    sinal = -1 if texto.startswith("-") else 1
    h, m = (int(x) for x in texto.lstrip("+-").split(":"))
    return dt.timezone(sinal * dt.timedelta(hours=h, minutes=m))


def proximo_inicio(evento: dict, agora: float) -> float | None:
    """Próximo início pela agenda, em segundos desde 1970 (relógio do servidor)."""
    regra = evento.get("agenda") or {}
    tipo = regra.get("tipo")
    if tipo == "hora":                        # toda hora no minuto M
        minuto = int(regra.get("minuto", 0))
        base = dt.datetime.fromtimestamp(agora, dt.timezone.utc).replace(minute=minuto, second=0, microsecond=0)
        if base.timestamp() <= agora:
            base += dt.timedelta(hours=1)
        return base.timestamp()
    if tipo == "horarios":                    # horários fixos, em dias da semana (0 = segunda) ou todo dia
        fuso = _fuso(regra.get("utc", "+00:00"))
        dias = set(regra.get("dias", range(7)))
        local = dt.datetime.fromtimestamp(agora, fuso)
        melhores = []
        for d in range(8):
            dia = (local + dt.timedelta(days=d)).date()
            if dia.weekday() not in dias:
                continue
            for hhmm in regra.get("horas", []):
                h, m = (int(x) for x in hhmm.split(":"))
                t = dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=fuso).timestamp()
                if t > agora:
                    melhores.append(t)
        return min(melhores) if melhores else None
    return None


@dataclass
class Eventos:
    """Estado dos eventos: o que o servidor contou + a agenda."""
    definicoes: list[dict] = field(default_factory=carregar)
    abertos: dict[int, dict] = field(default_factory=dict)      # ID do evento -> último registro
    atraso: float = 0.0                                         # relógio do servidor − hora do pacote

    def relogio(self, ts: float, servidor_ms: int) -> None:
        if 1_600_000_000_000 < servidor_ms < 4_000_000_000_000:
            self.atraso = servidor_ms / 1000 - ts

    def mensagem(self, op: int, payload: bytes) -> None:
        registros = [ler_evento(payload)] if op == 0x6001 else ler_lista(payload) if op == 0x6000 else []
        for r in registros:
            if r:
                self.abertos[r["evento"]] = r

    def _definicao(self, ev: int) -> dict | None:
        return next((d for d in self.definicoes if ev in d.get("ids", [])), None)

    def estado(self, agora_pc: float, janela: float = 600.0, desligados=()) -> list[dict]:
        """Eventos abertos e os que começam em até 'janela' s: [{chave, nome, estado, inicio, fim, fase}]."""
        agora = agora_pc + self.atraso
        saida: dict[str, dict] = {}
        for ev, r in self.abertos.items():                      # o que o servidor disse que está aberto
            d = self._definicao(ev) or {"chave": f"evento-{ev}", "nome": {}}
            if d["chave"] in desligados or r["fim_fase"] <= agora:
                continue
            item = saida.get(d["chave"])
            if item is None or r["fim_fase"] > item["fim"]:
                saida[d["chave"]] = {"chave": d["chave"], "nome": d.get("nome", {}), "estado": "aberto",
                                     "inicio": r["inicio"], "fim": r["fim_fase"], "fase": r["fase"], "id": ev}
        for d in self.definicoes:                               # o que a agenda diz que vem aí
            if d["chave"] in desligados or d["chave"] in saida:
                continue
            ini = proximo_inicio(d, agora)
            if ini is None:
                continue
            dur, periodo = float(d.get("duracao_min", 0)) * 60, _periodo(d)
            base = {"chave": d["chave"], "nome": d.get("nome", {}), "fase": 0, "id": None}
            if periodo and agora < ini - periodo + dur:         # o desta hora ainda está aberto
                saida[d["chave"]] = dict(base, estado="aberto", inicio=ini - periodo, fim=ini - periodo + dur)
            elif ini - agora <= janela:
                saida[d["chave"]] = dict(base, estado="em_breve", inicio=ini, fim=ini + dur)
        lista = sorted(saida.values(), key=lambda e: (e["estado"] != "aberto", e["inicio"]))
        for e in lista:                                         # tempos relativos, no relógio do servidor
            e["faltam"] = e["inicio"] - agora
            e["restam"] = e["fim"] - agora
        return lista

    def minijogos(self, agora_pc: float) -> list[dict]:
        """Minijogos abertos agora (ex.: os 9 do Festival Shugo, um ID cada): [{id, nome, fase, restam, regras}].
        Fase 1 é a sala de espera; na fase 2 cada um fecha no tempo dele."""
        agora = agora_pc + self.atraso
        saida = []
        for ev, r in self.abertos.items():
            d = self._definicao(ev) or {}
            info = (d.get("minijogos") or {}).get(str(ev))
            if info is None or r["fim_fase"] <= agora:
                continue
            saida.append({"id": ev, "evento": d.get("chave"), "nome": info.get("nome", {}), "fase": r["fase"],
                          "restam": r["fim_fase"] - agora, "regras": info.get("regras", {})})
        return sorted(saida, key=lambda m: m["restam"])


def _periodo(d: dict) -> float:
    return 3600.0 if (d.get("agenda") or {}).get("tipo") == "hora" else 0.0


def nome(evento: dict, idioma: str) -> str:
    n = evento.get("nome") or {}
    return n.get(idioma) or n.get("pt") or evento.get("chave", "")
