# Guia para mapear um boss (sugestão)

Este guia mostra como um boss novo costuma ser mapeado, para quem quiser entender o processo ou adiantar parte dele.
É uma **sugestão**: a decisão final sobre cada mecânica, os tempos e os textos dos alertas é do mantenedor, que confere
tudo em várias runs antes de publicar. Se você só quer ajudar, mandar material já basta ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## 1. O que juntar

- **Uma ou mais runs gravadas.** Com o Nebula Overlay aberto e "Gravar as masmorras" ligado (engrenagem → Alertas),
  cada masmorra vira um arquivo em `Documentos\Nebula Overlay\capturas`.
- **Vídeo da mesma run**, se puder. Anote o horário em que começou a gravar; ele liga o tempo do vídeo ao tempo da captura.
- **O que você viu:** em que momento o telegraph aparece, o que mata, o que o grupo faz para sobreviver.

## 2. Listar as skills do boss

Do código-fonte (ver [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md)):

```bash
python mapear.py "Documentos/Nebula Overlay/capturas/aovivo_X.pcap" --video-inicio 21:10:05
```

Para cada boss sai uma tabela com:
- cada skill, quantas vezes saiu e em que tempo da captura e do vídeo;
- o **preparo** (0x3809): quanto antes do cast o boss anuncia a skill. Esse é o tempo que o alerta ganha;
- o intervalo entre casts e o HP do boss em cada um;
- o alvo e quantos jogadores tomaram dano;
- as sequências que se repetem (A → B em +X s).

`--linha` mostra a linha do tempo completa; `--json ARQ` grava os casts para outra ferramenta.

## 3. Ligar skill e mecânica

Para cada skill que importa, olhe o vídeo no instante do cast:
- qual telegraph apareceu (círculo, leque, faixa, marca em jogador);
- quanto tempo até o impacto;
- quem precisa reagir (todos, o alvo, o tank, quem está perto).

Uma boa ligação aparece **igual em todos os casts**. Se só bate às vezes, anote como dúvida.

## 4. Como a mecânica fica no `mecanicas.json`

Cada boss tem `ids` (códigos do mob por dificuldade) e uma lista de `mecanicas`. Uma mecânica por skill fica mais ou menos assim:

```json
{
  "id": "judge-urahum-poca-acida",
  "nome": "Poça ácida",
  "gatilho": {"tipo": "skill", "skill_ids": [1605140], "preparo_s": {"1605140": 1.5}},
  "alerta": "SAI DA POÇA",
  "acao": "Saia antes do fim do cast, não depois que a poça se forma",
  "acao_tipo": "sair",
  "wipe": false
}
```

- `preparo_s` diz, por skill, quantos segundos o preparo vem antes do cast (a coluna "preparo" do `mapear.py`).
- `wipe: true` marca o que mata o grupo: vira alarme, com borda vermelha e contagem.
- `id` é estável: é por ele que cada pessoa desliga ou reescreve o alerta no `usuario.json`.
- `acao_tipo` escolhe o ícone, a cor, a voz curta e a dica da classe (`sair`, `empilhar`, `espalhar`, `pular`, `esquivar`, ...).
- `sequencia` (passos com tempo), `status` (faixa abaixo do alerta), `papeis`, `por_papel`, `so_perto` e `burst` estão
  explicados em [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md).
- Todo texto novo precisa de tradução em `mecanicas/traducoes.json`.

## 5. Testar

- Repita a captura com o overlay: `python overlay.py --repetir captura.pcap --a-partir 6:20` e confira se cada aviso sai na hora certa.
- Rode os testes: `python -m unittest discover -s testes`.
- Depois de algumas runs, a engrenagem → Ferramentas → **Aprender roteiros** monta a linha do tempo do boss sozinha.

## 6. Mandar

Abra uma issue ["Mecânica"](../../../issues/new?template=mecanica.yml) com o que você levantou (tabela, prints, links de vídeo),
ou um pull request se já mexeu no `mecanicas.json`. O mantenedor revisa, confere em outras runs e publica.
