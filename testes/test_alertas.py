"""Testes do motor de alertas. Rode da pasta aion2-meter:

    python -m unittest discover -s testes -v
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)

import alertas as cli  # noqa: E402
import gerador as g  # noqa: E402
from a2parse.alertas import MotorAlertas, boss, carregar_mecanicas  # noqa: E402
from a2parse.fontes import ler_tempo  # noqa: E402

DADOS = carregar_mecanicas()


def args_video(**kw):
    base = dict(masmorra="Urugugu Canyon", curva=None, sem_pre_aviso=False, pct_guia=False)
    base.update(kw)
    return argparse.Namespace(**base)


def primeiro(alertas, texto, depois=0.0):
    return next(a.t for a in alertas if a.texto == texto and a.t >= depois)


class TestVideoUrugugu(unittest.TestCase):
    """Os alertas gerados pela curva do vídeo caem perto do que se vê no vídeo."""

    @classmethod
    def setUpClass(cls):
        cls.al = cli.rodar_video(DADOS, args_video())

    def perto(self, t, esperado, tol=1.5):
        self.assertLessEqual(abs(t - ler_tempo(esperado)), tol, f"{t:.1f}s longe de {esperado}")

    def test_auldor_75(self):
        # com o sync no sumiço do boss, a sequência cai em cima do que o vídeo mostra
        self.perto(primeiro(self.al, "EMPILHA NO CÍRCULO"), "7:21.5", tol=0.6)
        self.perto(primeiro(self.al, "MERGULHO"), "7:27.5", tol=0.6)

    def test_auldor_30(self):
        self.perto(primeiro(self.al, "30%: FASE EM BREVE"), "8:48", tol=2)
        self.perto(primeiro(self.al, "EMPILHA NO CÍRCULO", depois=ler_tempo("8:00")), "9:11.5", tol=0.6)
        self.perto(primeiro(self.al, "MERGULHO", depois=ler_tempo("8:00")), "9:17", tol=0.6)

    def test_niveis(self):
        self.assertEqual({a.nivel for a in self.al if a.texto == "EMPILHA NO CÍRCULO"}, {"alarme"})
        self.assertEqual({a.nivel for a in self.al if a.texto == "FASE DO CÉU"}, {"info"})

    def test_raur_usa_percentual_observado(self):
        self.perto(primeiro(self.al, "PARA E VAI PRA BORDA"), "1:03", tol=3)

    def test_pre_aviso_vem_antes(self):
        breve = [a for a in self.al if a.fase == "breve" and a.boss == "Divine Auldor"]
        self.assertEqual(len(breve), 2)
        self.assertLess(breve[0].t, primeiro(self.al, "FASE DO CÉU"))


class TestMotor(unittest.TestCase):
    def test_dispara_uma_vez_e_reseta_no_wipe(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), pre_aviso=False)
        saida = []
        for t, hp in enumerate([100, 90, 80, 74, 70, 60]):
            saida += m.hp(float(t), hp)
        saida += m.avancar(100)
        self.assertEqual(sum(a.texto == "FASE DO CÉU" for a in saida), 1)
        # wipe: o boss volta cheio e a luta recomeça
        saida2 = m.hp(200, 100) + m.hp(201, 74) + m.avancar(300)
        self.assertEqual(sum(a.texto == "FASE DO CÉU" for a in saida2), 1)

    def test_enrage_agendado(self):
        m = MotorAlertas(boss(DADOS, "Ferocious Horn Nuakum"), pre_aviso=False)
        saida = m.hp(10.0, 100) + m.avancar(1000)
        textos = {(a.texto, a.t) for a in saida}
        self.assertIn(("ENRAGE EM 60s", 250.0), textos)
        self.assertIn(("ENRAGE", 310.0), textos)

    def test_sync_reancora_dentro_da_janela(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), pre_aviso=False)
        m.hp(0.0, 100)
        m.hp(10.0, 74)                     # dispara a 75%: SAI previsto em 13, EMPILHA em 17,5
        m.sync(16.0, "sumico")             # boss some 3 s depois do previsto
        saida = m.avancar(100)
        t = {a.texto: a.t for a in saida}
        self.assertAlmostEqual(t["EMPILHA NO CÍRCULO"], 20.5)
        self.assertAlmostEqual(t["MERGULHO"], 26.5)
        self.assertEqual(len(m.ajustes), 1)

    def test_sync_fora_da_janela_e_ignorado(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), pre_aviso=False)
        m.hp(0.0, 100)
        m.hp(10.0, 74)
        m.sync(60.0, "sumico")             # bem depois da janela [13-3, 13+20]
        t = {a.texto: a.t for a in m.avancar(100)}
        self.assertAlmostEqual(t["EMPILHA NO CÍRCULO"], 17.5)
        self.assertEqual(m.ajustes, [])

    def test_proximos(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), pre_aviso=False)
        m.hp(0.0, 80)
        prox = m.proximos(0.0)
        self.assertEqual([p["hp"] for p in prox if "hp" in p], [75.0, 30.0])
        m.hp(5.0, 74)
        com_eta = [p for p in m.proximos(5.0) if "eta" in p]
        self.assertEqual(com_eta[0]["texto"], "SAI DAS FAIXAS")
        self.assertAlmostEqual(com_eta[0]["eta"], 3.0)

    def test_skill_real_do_auldor_com_sync_no_mergulho(self):
        # tempos medidos na captura de 2026-10-16: 1601010 → mergulho 1601030 em +11,6 s
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, eu=16160)
        saida = m.skill(100.0, 1601010, 27268) + m.avancar(108.5)
        saida += m.skill(112.0, 1601030, 16160) + m.avancar(200)
        t = {a.texto: a.t for a in saida}
        self.assertAlmostEqual(t["EMPILHA NO CÍRCULO"], 108.0)
        self.assertAlmostEqual(t["MERGULHO"], 112.0)            # reancorado no cast real (+0,4 s)
        self.assertIn("O MERGULHO É EM VOCÊ", t)                 # pessoal: o alvo era você

    def test_status_do_boss_e_do_alvo(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, eu=16160)
        m.skill(100.0, 1601010, 27268)
        textos = lambda t: {(s["texto"], s["alvo"]) for s in m.status_ativos(t)}
        self.assertEqual(textos(101.0), set())                                  # some só em +3 s
        self.assertEqual(textos(104.0), {("NO CÉU", None)})
        self.assertEqual(textos(109.0), {("NO CÉU", None), ("CÍRCULO VERMELHO", None)})
        m.avancar(111.0)
        m.skill(112.4, 1601030, 15935)                                         # mergulho real 0,8 s depois do previsto
        self.assertIn(("CÍRCULO VERMELHO", None), textos(112.3))               # reancorado junto com a sequência
        self.assertIn(("MERGULHO", 15935), textos(112.5))
        self.assertEqual(textos(114.0), set())

    def test_status_renova_em_vez_de_duplicar(self):
        m = MotorAlertas(boss(DADOS, "Judge Urahum"), modo_skills=True)
        m.skill(10.0, 1605142, 500)
        m.skill(12.0, 1605142, 500)
        m.skill(12.0, 1605142, 600)
        poças = [s for s in m.status_ativos(12.1) if s["texto"] == "POÇA"]
        self.assertEqual(sorted(s["alvo"] for s in poças), [500, 600])
        self.assertAlmostEqual(next(s["restante"] for s in poças if s["alvo"] == 500), 4.9)

    def test_burst_anda_com_o_sync(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True)
        saida = m.skill(100.0, 1601090, 27268) + m.skill(103.0, 1601010, 27268) + m.avancar(114.0)
        saida += m.skill(115.4, 1601030, 1) + m.avancar(200)       # mergulho 0,8 s depois do previsto
        t = {a.texto: a.t for a in saida}
        self.assertAlmostEqual(t["SEGURA O BURST"], 100.0)
        self.assertAlmostEqual(t["BURST AGORA"], 115.4 + 1.3)
        self.assertEqual({a.nivel for a in saida if a.tipo in ("burst", "segurar_burst")}, {"info"})
        sem = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, burst=False)
        self.assertNotIn("SEGURA O BURST", [a.texto for a in sem.skill(1.0, 1601090) + sem.avancar(5)])

    def test_papel_filtra_e_reescreve(self):
        b = boss(DADOS, "Judge Urahum")
        dps = MotorAlertas(b, modo_skills=True, papel="dps")
        cura = MotorAlertas(b, modo_skills=True, papel="healer")
        self.assertNotIn("ÁCIDO EM ALGUÉM", [a.texto for a in dps.skill(1.0, 1605142, 5) + dps.avancar(2)])
        self.assertIn("ÁCIDO EM ALGUÉM", [a.texto for a in cura.skill(1.0, 1605142, 5) + cura.avancar(2)])
        leque = dict(next(m for m in boss(DADOS, "Divine Auldor")["mecanicas"] if m["id"] == "divine-auldor-leque-frontal-4-tornados"))
        leque["gatilho"] = {"tipo": "skill", "skill_ids": [42]}
        tank = MotorAlertas({"nome": "X", "mecanicas": [leque]}, papel="tank")
        self.assertEqual([a.texto for a in tank.skill(1.0, 42)], ["VIRA ELE PRA FORA"])

    def test_dica_da_classe(self):
        from a2parse.alertas import carregar_dicas
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, eu=7, classe="GLADIATOR", dicas=carregar_dicas())
        dicas = {a.texto: a.dica for a in m.skill(1.0, 1601030, 7) + m.avancar(3)}
        self.assertIn("Bloqueio Concentrado", dicas["O MERGULHO É EM VOCÊ"])     # empilhar_pessoal
        u = MotorAlertas(boss(DADOS, "Judge Urahum"), modo_skills=True, eu=7, classe="CLERIC", dicas=carregar_dicas())
        self.assertIn("Luz da Cura", {a.texto: a.dica for a in u.skill(1.0, 1605142, 7)}["POÇA EM VOCÊ: SAI"])

    def test_segunda_leva_de_skills(self):
        u = MotorAlertas(boss(DADOS, "Judge Urahum"), modo_skills=True, papel="dps")
        self.assertEqual([(a.texto, a.contagem) for a in u.skill(1.0, 1605090, 40493)], [("ESTRELA → DEFESA", 2.0)])
        self.assertEqual([a.texto for a in u.skill(5.0, 1605110, 1)], ["SAI DO CÍRCULO"])
        r = MotorAlertas(boss(DADOS, "Guardian Captain Raur"), modo_skills=True)
        self.assertEqual([a.texto for a in r.skill(1.0, 1504440, 1) + r.skill(2.0, 1504440, 1)], ["SAI DE PERTO"])  # supressão de 3 s

    def test_leque_so_para_tank(self):
        b = boss(DADOS, "Divine Auldor")
        dps = MotorAlertas(b, modo_skills=True, papel="dps")
        tank = MotorAlertas(b, modo_skills=True, papel="tank")
        self.assertEqual(dps.skill(1.0, 1600925, 27268), [])
        self.assertEqual([a.texto for a in tank.skill(1.0, 1600925, 27268)], ["VIRA ELE PRA FORA"])

    def test_agarrao_mostra_quem_foi_pego(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True)
        m.skill(1.0, 1601040, 15935)
        self.assertIn(("AGARRADO", 15935), {(s["texto"], s["alvo"]) for s in m.status_ativos(1.5)})

    def test_engaje_so_para_corpo_a_corpo(self):
        b = boss(DADOS, "Divine Auldor")
        textos = lambda classe: [a.texto for a in MotorAlertas(b, modo_skills=True, classe=classe).skill(1.0, 1600970, 1)
                                 + MotorAlertas(b, modo_skills=True, classe=classe).avancar(5)]
        gla = MotorAlertas(b, modo_skills=True, classe="GLADIATOR")
        sor = MotorAlertas(b, modo_skills=True, classe="SORCERER")
        self.assertIn("ENGAJE", [a.texto for a in gla.skill(1.0, 1600970, 1) + gla.avancar(5)])
        self.assertNotIn("ENGAJE", [a.texto for a in sor.skill(1.0, 1600970, 1) + sor.avancar(5)])

    def test_cor_do_thamon_por_tipo_de_dano(self):
        b = boss(DADOS, "Thamon")
        texto = lambda classe: [a.texto for a in MotorAlertas(b, modo_skills=True, classe=classe).hp(0, 94)]
        self.assertEqual(texto("RANGER"), ["VERMELHO: PARA DE BATER"])          # físico, mesmo de longe
        self.assertEqual(texto("GLADIATOR"), ["VERMELHO: PARA DE BATER"])
        self.assertEqual(texto("SORCERER"), ["ROXO: PARA DE BATER"])
        self.assertEqual(texto(None), ["VERMELHO: FÍSICO PARA / ROXO: MÁGICO PARA"])
        verm = dict(next(m for m in b["mecanicas"] if m["id"] == "thamon-fase-vermelha"))
        verm["gatilho"] = {"tipo": "skill", "skill_ids": [42]}
        so = lambda classe: [a.texto for a in MotorAlertas({"nome": "X", "mecanicas": [verm]}, classe=classe).skill(1.0, 42)]
        self.assertEqual(so("RANGER"), ["VERMELHO: PARA DE BATER"])
        self.assertEqual(so("ELEMENTALIST"), [])

    def test_prisao_de_pedra_do_vakron_com_dica_do_arqueiro(self):
        from a2parse.alertas import carregar_dicas
        m = MotorAlertas(boss(DADOS, "Vakron"), modo_skills=True, classe="RANGER", dicas=carregar_dicas())
        a = m.skill(1.0, 1604425, 1)
        self.assertEqual([x.texto for x in a], ["QUEBRA A PEDRA VERMELHA"])
        self.assertIn("Flecha Certeira", a[0].dica)
        for classe in ("GLADIATOR", "TEMPLAR", "ASSASSIN", "RANGER", "SORCERER", "ELEMENTALIST", "CLERIC",
                       "CHANTER", "FIGHTER"):
            self.assertIn(classe, carregar_dicas())

    def test_poca_eletrica_pelo_dano_em_voce(self):
        """A poça do Gelcos é um NPC à parte que mira a si mesmo: o aviso vem do dano que você toma."""
        m = MotorAlertas(boss(DADOS, "Gelcos"), modo_skills=True, eu=7)
        self.assertEqual([a.texto for a in m.dano_em_voce(10.0, 1603310)], ["SAI DA POÇA"])
        self.assertEqual(m.dano_em_voce(11.0, 1603310), [])                  # supressão de 3 s
        self.assertEqual([a.texto for a in m.dano_em_voce(14.0, 1603310)], ["SAI DA POÇA"])
        self.assertEqual(m.dano_em_voce(20.0, 1603250), [])                  # outra skill: nada

    def test_engaje_depois_da_poca(self):
        u = boss(DADOS, "Judge Urahum")
        gla = MotorAlertas(u, modo_skills=True, eu=7, classe="GLADIATOR")
        cle = MotorAlertas(u, modo_skills=True, eu=7, classe="CLERIC")
        g = {a.texto: a.t for a in gla.skill(1.0, 1605142, 7) + gla.avancar(10)}
        self.assertEqual(g.get("ENGAJE"), 4.0)
        self.assertNotIn("ENGAJE", [a.texto for a in cle.skill(1.0, 1605142, 7) + cle.avancar(10)])

    def test_atordoamento_em_todos_os_bosses(self):
        for mz in DADOS["masmorras"]:
            for b in mz["bosses"]:
                a = MotorAlertas(b, modo_skills=True).skill(1.0, 1000009, b.get("nome"))
                self.assertIn(("ATORDOADO: BURST!", 5.0), [(x.texto, x.contagem) for x in a], b["nome"])
                self.assertNotIn("NOVA FASE", [x.texto for x in a])

    def test_pessoal_nao_dispara_para_outro(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), modo_skills=True, eu=16160)
        textos = [a.texto for a in m.skill(5.0, 1601030, 15935) + m.avancar(10)]
        self.assertNotIn("O MERGULHO É EM VOCÊ", textos)

    def test_reserva_de_hp_fica_de_fora_no_modo_skills(self):
        m = MotorAlertas(boss(DADOS, "Divine Auldor"), pre_aviso=False, modo_skills=True)
        textos = [a.texto for a in m.hp(0, 100) + m.hp(5, 74) + m.avancar(100)]
        self.assertEqual(textos, [])
        m2 = MotorAlertas(boss(DADOS, "Divine Auldor"), pre_aviso=False)   # modo vídeo: a reserva vale
        self.assertIn("FASE DO CÉU", [a.texto for a in m2.hp(0, 100) + m2.hp(5, 74) + m2.avancar(100)])

    def test_supressao_de_rajada(self):
        m = MotorAlertas(boss(DADOS, "Guardian Captain Raur"), modo_skills=True, eu=16160)
        saida = []
        for k in range(10):                                     # 10 pulsos em 2 s
            saida += m.skill(50 + k * 0.2, 1504451, 16160)
        saida += m.avancar(100)
        self.assertEqual(sum(a.texto == "VOCÊ ESTÁ NA ZONA" for a in saida), 1)

    def test_preferencias_do_usuario(self):
        from a2parse.alertas import aplicar_usuario
        d = carregar_mecanicas(usuario=None)
        aplicar_usuario(d, {"desligadas": ["divine-auldor-repeticao-da-marca"],
                            "textos": {"divine-auldor-marca-mergulho-dividir-dano": "STACK"}})
        b = boss(d, "Divine Auldor")
        ids = [x["id"] for x in b["mecanicas"]]
        self.assertNotIn("divine-auldor-repeticao-da-marca", ids)
        self.assertEqual(b["mecanicas"][0]["sequencia"][0]["texto"], "STACK")

    def test_skill_mapeada(self):
        b = boss(DADOS, "Divine Auldor")
        b = dict(b, mecanicas=[dict(x) for x in b["mecanicas"]])
        faixa = next(x for x in b["mecanicas"] if x["nome"].startswith("Faixas laranja"))
        faixa["gatilho"] = {"tipo": "skill", "skill_ids": [23021801]}
        m = MotorAlertas(b, pre_aviso=False)
        self.assertEqual([a.texto for a in m.skill(5.0, 23021801)], ["SAI DA FAIXA"])
        self.assertEqual([a.texto for a in m.skill(9.0, 23021801)], ["SAI DA FAIXA"])  # repete a cada cast
        self.assertEqual(m.skill(9.5, 999), [])


class TestCapturaSintetica(unittest.TestCase):
    """Uma luta gerada em .pcapng: detector de boss + motor + diagnóstico de skills."""

    def test_luta_auldor(self):
        rng = random.Random(4)
        BOSS, MAX = 900777, 8_000_000
        msgs, hp = [g.horario(1)], MAX
        w = g.EscritorPcapng()
        ts, seq = 100.0, 1001
        w.pacote(ts, "203.0.113.5", "192.168.1.10", 2106, 51000, seq, 0x02)
        seq += 1
        for passo in range(600):  # 0,5 s por passo = 300 s
            hp = max(0, hp - rng.randint(9000, 18000))
            corpo = g.dano(1002, BOSS, 15060000, 12000) + g.hp(BOSS, hp)
            # roteiro real da fase do céu (captura de 2026-10-16): 1601090 → 1601010 → mergulho 1601030
            if passo == 140:
                corpo += g.inicio_skill(BOSS, 1601090, BOSS, 0)
            if passo == 147:
                corpo += g.inicio_skill(BOSS, 1601010, BOSS, 0)
            if passo == 170:
                corpo += g.inicio_skill(BOSS, 1601030, 1002, 0)
            if passo == 0:
                corpo = g.horario(1) + corpo
            ts += 0.5
            w.pacote(ts, "203.0.113.5", "192.168.1.10", 2106, 51000, seq, 0x18, corpo)
            seq += len(corpo)
        with tempfile.TemporaryDirectory() as tmp:
            cam = os.path.join(tmp, "luta.pcapng")
            w.salvar(cam)
            ns = argparse.Namespace(captura=cam, porta=None, bosses="Divine Auldor", hp_minimo=1_000_000,
                                    masmorra="Urugugu Canyon", sem_pre_aviso=False, pct_guia=False, eu=1002)
            alertas, diag = cli.rodar_pcap(DADOS, ns)
        self.assertEqual(diag["entidades"], {"Divine Auldor": BOSS})
        t_sumico = 147 * 0.5      # tempo desde o 1º evento
        self.assertAlmostEqual(primeiro(alertas, "FASE DO CÉU EM BREVE"), 140 * 0.5, delta=0.6)
        self.assertAlmostEqual(primeiro(alertas, "EMPILHA NO CÍRCULO"), t_sumico + 8, delta=0.6)
        self.assertAlmostEqual(primeiro(alertas, "MERGULHO"), 170 * 0.5, delta=0.6)   # reancorado no cast
        self.assertTrue(any(a.texto == "O MERGULHO É EM VOCÊ" for a in alertas))
        self.assertFalse(any(a.texto == "EM BREVE: FASE DO CÉU" for a in alertas))   # reserva de HP desligada
        self.assertEqual(len(diag["skills"]["Divine Auldor"]), 3)


if __name__ == "__main__":
    unittest.main()
