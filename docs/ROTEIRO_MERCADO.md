# Mercado e o que mais vale trazer (estudo, 19/10/2026)

Estudo de um app concorrente (medidor + alertas + mercado, gratuito com plano pago) para decidir o que o Nebula
Overlay deve ter. Regras que continuam valendo: só ler o tráfego, nunca enviar nada ao servidor do jogo, sem
servidor próprio, sem tabelas extraídas do jogo no repositório, tudo grátis.

## Como o mercado deles funciona

- **Preços:** não vêm do tráfego. Vêm de um site de preços de terceiros (aion2.exchange), que tem um coletor
  lendo de hora em hora os preços, as estatísticas diárias de venda (publicadas no horário da Coreia) e a
  profundidade do mercado, por servidor. O app baixa esses números de hora em hora e faz as contas no PC.
- **O que você tem:** vem do tráfego (o servidor manda inventário, armazém e moedas ao entrar no jogo).
- **Com isso montam:** patrimônio (mochila, armazém, equipado, kinah), variação em 24 h, "bom momento para
  vender" (itens seus que subiram 20% ou mais em 24 h), valor de cada chefe de campo pelos drops, "fabricar
  compensa?", comparação entre servidores, lista de desejos com aviso, preço justo (mediana do dia) e uma barra
  pequena no jogo que avisa quando cai um item valioso.
- **Pago:** alerta de venda, melhor hora para vender, rota de farm, patrimônio ao longo do tempo.

## O que o Nebula já tem e eles também

Medidor da party, alertas de mecânica antecipados, eventos de campo (Shugo, invasão), energia Odyle, ping,
atualização automática, pt/en/es, overlay só quando o jogo está em foco.

## O que vale trazer, em ordem

### 1. "Tudo funcionando?" (pequeno, ajuda já)

Uma aba na engrenagem que confere e explica, com o botão que resolve: Npcap instalado, loopback quando há
acelerador, Npcap restrito a administrador, jogo em tela cheia exclusiva, captura recebendo mensagens do jogo
(se o painel diz "Conectado" e não chega nada há 1 min, é acelerador por driver ou placa errada), ping e
**relógio do PC errado** (já sabemos a diferença pelo 0x3600; os eventos de campo dependem dela). Inclui
"Copiar diagnóstico" para mandar a quem ajuda. É o caso do amigo cujo app "não funciona".

### 2. Loot e kinah da run (base do mercado, precisa de capturas)

Hoje o `a2parse` não decodifica nenhuma mensagem de item, inventário ou kinah. Nas capturas há várias mensagens
ainda sem nome (famílias 0x56xx, 0x92xx, 0x95xx). Para achar as certas, é preciso gravar com
"Gravar também fora de masmorra" ligado:

1. **Entrar no jogo** (tela de personagem até a cidade): a lista do inventário, do armazém e das moedas.
2. **Pegar um drop** de valor conhecido e **vender algo a um NPC** (kinah sobe um valor conhecido).
3. **Abrir o mercado, buscar dois itens e olhar as listagens** (anote item, quantidade e preço que aparecem).
4. **Matar um chefe e abrir o baú.**

Com isso: o relatório da run ganha "o que caiu" e o kinah ganho, e o painel pode ter uma linha "loot da run".

### 3. Preços (duas fontes, sem servidor próprio)

- **Preços que você mesmo viu:** quando você abre o mercado no jogo, o servidor manda as listagens. O Nebula
  guarda o menor preço de cada item com a hora ("visto há 2 h"), só no seu PC. Funciona sempre, mas só para o
  que você consultou.
- **Feed externo (opcional, desligado por padrão):** baixar os preços do servidor de hora em hora de um site de
  preços público, se os donos permitirem. O aion2.exchange tem uma API (`/api/servers`, `/api/overview`...),
  mas não publica termos de uso e estava fora do ar (503) no dia do estudo; antes de usar, perguntar no Discord
  deles. Só leitura de um site, nunca o servidor do jogo.

Com preços: patrimônio, "bom momento para vender", lista de desejos com aviso, valor do loot da run e o aviso
"caiu item valioso". "Fabricar compensa?" exige a tabela de receitas, que é dado do jogo: só se vier de fonte
pública baixada em tempo de execução ou da pasta `dados_jogo` do usuário (nunca no repositório).

### 4. Para a live (médio)

O overlay como fonte de navegador do OBS: um servidor HTTP só em `127.0.0.1` servindo o painel com fundo
transparente. Não sai nada do PC.

### 5. Pequenos, do mesmo estudo

- Medidor: cura e dano mitigado além do dano; opção "só o chefe final"; masmorra somada ou por luta.
- Overlay em outro monitor e "fixo na tela" (hoje ele some quando o jogo perde o foco).
- Aviso quando o relógio do PC está errado (vem junto com o item 1).

## O que não trazer

Conta de usuário, dados enviados a um servidor nosso (timers de chefe de campo da comunidade, ranking, mapa da
comunidade, radar de mascotes, alertas "que aprendem juntos") e plano pago. Tudo isso exige servidor e coleta de
dados de outros jogadores. O minimapa de guerra do Abismo e os replays exigem decodificar posições (grande);
ficam para depois.

## Próximo passo

Item 1 dá para fazer já. Os itens 2 e 3 começam pelas quatro gravações acima.
