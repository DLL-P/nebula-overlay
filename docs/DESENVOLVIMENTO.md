# Desenvolvimento

## Rodar do código-fonte

Windows, Python 3.12 e o [Npcap](https://npcap.com/#download). Não há dependências de terceiros para rodar.

```bash
python overlay.py                                   # o app, igual ao instalado
python overlay.py --repetir captura.pcap --a-partir 6:20 --sempre-visivel   # repete uma run, sem o jogo
python overlay.py --demo                            # alertas de exemplo
python -m unittest discover -s testes               # testes
```

Rodando do código-fonte, configurações, capturas e vozes ficam na pasta do projeto (no app instalado, em
Documentos\Nebula Overlay). A variável `NEBULA_OVERLAY_PASTA` troca esse lugar (útil para testes).

## Estrutura

| Arquivo | O que faz |
|---|---|
| `overlay.py` | o app: camadas por cima do jogo (alertas, painel, borda), conexão com o jogo, atualização |
| `painel.py` | janelas normais: principal, engrenagem (configurações) e saída das ferramentas |
| `app.py` | ponto de entrada do executável (app e ferramentas) |
| `voz.py` | voz curta pré-gravada com as vozes do Windows (pt-BR, en-US, es) |
| `gravar.py` | Npcap: placas, rota do jogo (detecta acelerador), gravação de linha de comando |
| `roteiros.py` | aprende a linha do tempo dos bosses com as capturas |
| `relatorio.py` | relatório pós-run: seu dano por skill, pausas, janelas de burst |
| `mapear.py` | tabela de skills de um boss numa captura (ver [MAPEAR_BOSS.md](MAPEAR_BOSS.md)) |
| `analisar.py` | estatísticas de uma captura (opcodes, erros de decodificação) |
| `alertas.py` | ensaio do motor de alertas sobre um vídeo ou uma captura |
| `a2parse/captura.py`, `protocolo.py`, `decoders.py` | remontagem TCP, framer, LZ4 e layouts ([PROTOCOLO.md](PROTOCOLO.md)) |
| `a2parse/aovivo.py` | sessão ao vivo: bosses, você, grupo, alertas, linha do tempo |
| `a2parse/alertas.py` | motor de alertas (lê `mecanicas/mecanicas.json`) |
| `a2parse/roteiro.py` | roteiro aprendido e previsão (cadeia de skills, fases por HP, atordoamento, ciclos) |
| `a2parse/meter.py` | painel de dano |
| `a2parse/classes.py` | classe e papel |
| `a2parse/idioma.py` | textos da interface em pt/en/es e tradução dos alertas |
| `a2parse/caminhos.py` | pasta do programa e pasta do usuário |
| `a2parse/atualizar.py`, `versao.py` | atualização automática pelas versões do GitHub |
| `mecanicas/mecanicas.json` | mecânicas de cada boss (o conhecimento do app) |
| `mecanicas/roteiros.json` | linha do tempo aprendida que vai junto com o app |
| `mecanicas/traducoes.json` | textos dos alertas em inglês e espanhol |
| `dados/dicas_classes.json` | dica de cada classe por tipo de ação |

### Dados do jogo

O repositório não tem tabelas extraídas do jogo. Os bosses são reconhecidos pelos `ids` no `mecanicas.json`. Quem tiver
tabelas próprias de nomes (`npcs.json`, `skills_pt.json`, no formato `{"id": ...}`) pode pô-las em `dados/` (no
código-fonte) ou em `Documentos\Nebula Overlay\dados_jogo`; o relatório e o reconhecimento de bosses de campo passam a usá-las.
Elas estão no `.gitignore`.

## Mecânicas (`mecanicas/mecanicas.json`)

Cada masmorra tem bosses; cada boss tem `ids` (código do mob por dificuldade) e `mecanicas`. Campos de uma mecânica:

| Campo | O que é |
|---|---|
| `id` | identificador estável (preferências do usuário usam ele) |
| `gatilho` | `{"tipo": "skill", "skill_ids": [...], "preparo_s": {"<skill>": 1.5}}` ou `{"tipo": "hp", "pct": 75}`; `"pessoal": true` só alerta quando o alvo é você |
| `alerta`, `acao`, `acao_tipo` | texto grande, texto menor e tipo da ação (ícone, cor, voz e dica) |
| `wipe` | `true` vira alarme (cartão vermelho, borda e contagem); o nível também depende do `acao_tipo` |
| `sequencia` | passos `{"t", "texto", "sub", "tipo", "contagem", "sync"}`; o `sync` reancora a sequência num evento real dentro de uma janela |
| `status` | `{"texto", "tipo", "em": "boss" ou "alvo", "de", "ate"}`: a faixa abaixo do alerta |
| `papeis`, `por_papel` | quem vê o alerta e texto trocado por papel (tank, healer, dps, suporte) |
| `so_perto` | só para classes corpo a corpo (ex.: ENGAJE) |
| `dica_tipo`, `dicas` | outra chave da tabela de dicas, ou dica fixa por classe |
| `burst` | janelas `segurar` / `soltar` |
| `voz`, `voz_curta` | fala trocada / chave da palavra de ordem |

### Preferências do usuário (`mecanicas/usuario.json`, na pasta do usuário)

```json
{
  "desligadas": ["divine-auldor-leque-frontal-4-tornados"],
  "textos": {"divine-auldor-marca-mergulho-dividir-dano": "STACK"},
  "voz": {"guardian-captain-raur-fase-de-reflexo": "Para tudo"}
}
```

Também dá para corrigir traduções sem mexer no app: `mecanicas/traducoes.json` na pasta do usuário, no mesmo formato
do arquivo do programa, vale por cima dele.

## Como o motor decide

- **Três níveis:** `info` (texto), `alerta` (cartão amarelo com som) e `alarme` (cartão vermelho, voz e contagem).
- **Preparo:** com `preparo_s`, o alerta sai no 0x3809, antes do cast, `antecipar` segundos antes do previsto (padrão 0,8 s).
- **Sync por janela:** um passo pode esperar um evento real (`"sync": {"evento": "sumico", "janela": [antes, depois]}`);
  se o evento cai na janela, a sequência se reancora ali.
- **Linha do tempo:** junta os passos já agendados (exatos) com a previsão do roteiro. Só previsões com confiança ≥ 0,75 e
  boss com precisão medida ≥ 75% sobem para o centro.

## Gerar o app e o instalador

```bash
python -m pip install pyinstaller==6.22.2
python empacotar/construir.py --versao 2026.10.17.1
```

Gera `dist/NebulaOverlay/`, e com o [Inno Setup 6](https://jrsoftware.org/isinfo.php) instalado, também
`dist/NebulaOverlay-Setup.exe` e o `.sha256`. Tabelas do jogo e capturas nunca entram no pacote.

## Versões e atualização automática

- Cada commit no `main` dispara `.github/workflows/lancar.yml`: testes, app, instalador e uma versão `vAAAA.MM.DD.N` no GitHub.
- Pull requests rodam só os testes (`.github/workflows/testes.yml`).
- O app instalado consulta a versão mais nova ao abrir. Fora do jogo, atualiza sozinho (se "Atualizar sozinho" estiver ligado);
  durante o jogo, mostra o botão. Ele baixa só do próprio repositório, confere o SHA-256 e roda o instalador em modo silencioso,
  que reabre o app.
