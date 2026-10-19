# Protocolo de rede do Aion 2 (o que o Nebula Overlay lê)

Formato das mensagens que o servidor manda ao cliente, do jeito que o `a2parse` decodifica. Tudo foi
conferido em capturas reais de masmorra. Os layouts mudam com os patches do jogo: se algo parar de bater,
grave uma run e compare (`python analisar.py captura.pcap`).

Todos os inteiros de tamanho fixo são little-endian. `varint` é LEB128 (7 bits por byte, até 5 bytes).

## 1. Captura

- O Npcap entrega os segmentos TCP; o `a2parse/captura.py` remonta cada fluxo.
- **Âncora de sincronização:** a mensagem `0x3600` (horário do servidor) tem 8 bytes de payload. No fio
  ela aparece como `0E 00 36` seguido de um `i64` com o horário em ms, que precisa estar perto da hora
  atual. É assim que o framer acha o começo de uma mensagem no meio do fluxo.
- **Com acelerador (ExitLag e parecidos):** o jogo conecta num proxy local (`127.0.0.1:<porta>`) e o
  acelerador reenvia tudo num túnel próprio. O tráfego limpo só existe no **loopback**, entre o jogo e o
  proxy. Por isso o Npcap precisa de "Support loopback traffic"; o `gravar.py` acha o proxy pelo netstat.

## 2. Mensagem

```
varint   length     tamanho do payload + 6
u16      opcode
bytes    payload    length − 6 bytes
```

### 0xFFFF: bloco comprimido

```
u32      tamanho descomprimido   (1 .. 1.048.576)
bytes    bloco LZ4 cru           (formato "block", sem cabeçalho de "frame")
```

O resultado é mais uma sequência de mensagens no mesmo formato, até 3 níveis de profundidade.

## 3. Mensagens usadas

| Opcode | O que é | Para que o overlay usa |
|---|---|---|
| 0x3600 | horário do servidor | âncora do framer |
| 0x3633 | seu personagem | seu nome, servidor e classe |
| 0x3645 / 0x8A33 | nome de outro personagem | nomes no painel do grupo |
| 0x3641 | entidade aparecendo (NPC, invocação) | reconhecer o boss; dono das invocações |
| 0x3802 | início de skill | mecânicas do boss, classe dos jogadores |
| 0x3809 | preparo de skill | aviso antecipado (seção 5) |
| 0x3804 | dano | painel de dano |
| 0x3805 | dano periódico | painel de dano |
| 0x8D00 | HP de entidade | HP do boss, fases por HP |
| 0x3642 | morte | fim da luta |
| 0xE005 | medidor de atordoamento | barra roxa e ATORDOADO (seção 6) |
| 0x610B / 0x610C | tickets de conteúdo | energia Odyle (seção 7) |
| 0x382A | buff/debuff aplicado | status em jogadores; controle em você |
| 0x382C | buff/debuff removido | fim do controle em você |
| 0x3816 | movimento forçado | derrubada/empurrão em você |
| 0x6000 / 0x6001 | eventos de campo | cartão de eventos (seção 10) |
| 0x9702 / 0x970B | lista do grupo / alguém entrou na sala | classe, nível, GS e CP de cada jogador (seção 11) |
| 0x3656 | seu poder de combate | seu CP (atual e o maior) |

A lista completa de nomes fica em `opcodes.json`.

## 4. Layouts

### 0x3804 dano

```
varint    alvo
u16       flags            sem o bit 0x04 não é dano (proc, buff, efeito): fica de fora
varint    origem
u32       skill
u8        id da ação
[flags & 0x01]  u32
u8        tipo do acerto   3 = crítico; 9 = dano refletido (fica de fora)
[flags & 0x02]  detalhes:
    u8 de bits (do menos para o mais significativo): bit 1 aparo, bit 2 perfeito, bit 3 duplo, bit 5 tem cura
    [tem cura] varint64 cura
    u8        direção      1 = costas, 2 = frente
u32
u32
varint
varint64  dano             já inclui o multi-hit
[flags & 0x08]  u32
[flags & 0x10]  1 bit
[flags & 0x20]  varint n + n × varint64   golpes do multi-hit (não some de novo ao dano)
```

O leitor de bits guarda o byte atual: o bit 6 sai do mesmo byte dos bits 0 a 5.
Dano com alvo igual à origem é efeito no próprio personagem e fica de fora.

### 0x3805 dano periódico

```
varint    alvo
u8        máscara          0x0A = dano; outro valor = cura, escudo ou buff
varint    origem
varint
u32       skill
varint64  dano
```

### 0x8D00 HP

```
varint    entidade
varint    tipo             2 = HP
varint
varint
u64       HP atual
```

### 0x3642 morte

`varint entidade | varint | varint motivo`

### 0x3802 início de skill

```
varint    conjurador
u8        flagsA
u32       skill
u8        id da ação
[flagsA & 0x01]  u8
u8        flagsB
varint    alvo
[flagsB & 0x01]  u32
u32
[flagsB & 0x02]  12 bytes  (posição do alvo)
varint
u8
[flagsA & 0x02]  varint
varint    recarga em ms
[flagsA & 0x04]  u8        cargas
[flagsA & 0x08]  varint    tempo de recarga das cargas
[flagsA & 0x10]  1 bit
[flagsA & 0x20]  varint n + n × (varint alvo + 12 bytes)
```

### 0x3641 entidade aparecendo

`varint entidade | u16 | u8 flag | [flag 1: u8 tamanho + nome do dono] | u32 código do mob`

O código do mob leva ao boss no `mecanicas.json` (campo `ids`). Com nome do dono, é invocação de jogador:
o dano dela entra no dono. Invocação sem nome é atribuída pelo prefixo da skill de classe.

### 0x3633 seu personagem

`varint entidade | u32 | u8 | u8 tamanho | nome | u16 servidor | u8 classe`

O ID de classe vem em faixas de 4: 5–8 Gladiador, 9–12 Templário, 13–16 Arqueiro, 17–20 Assassino,
21–24 Espiritualista, 25–28 Mago, 29–32 Clérigo, 33–36 Encantador, 45–48 Lutador.
Os casts confirmam: `skill // 1.000.000` dá 11 Gladiador, 12 Templário, 13 Assassino, 14 Arqueiro,
15 Mago, 16 Espiritualista, 17 Clérigo, 18 Encantador, 19 Lutador.

### 0x382A buff/debuff

A skill que aplicou o efeito fica no offset 30 do payload (ex.: `1601020`, o debuff dos tornados do Auldor)
quando o alvo e a origem têm varints de 2 e 3 bytes. O layout completo (todas as 2.816 mensagens da run de
2026-10-17 00:29 batem):

```
varint    alvo
u8        1
u8        flags            0x13 = com skill; 0x11 = sem (efeitos do próprio personagem ao entrar na zona)
varint    instância        sobe a cada efeito; é o que o 0x382C remove
u32       efeito           skill de classe: skill × 10 + n (11780007 → 117800071); comuns: 1000002x1 a 1000008x1
i64       duração em ms    −1 = sem fim
u64       início           ms do relógio do servidor
varint    origem           quem aplicou
u8        nível            1 nos bosses; nível da skill nos jogadores
[flags & 0x02]  u32 skill
u8
3×f32     posição
```

Efeitos de controle já vistos estão em `dados/controles.json` (ex.: `100000321` derrubada, `100000311`
atordoamento, `100000201` enraizamento; `12211011` derrubada do Pinopi, `16010502` agarrão do Auldor).

### 0x382C buff/debuff removido

`varint alvo | u8 n | n × (u8 0 | varint instância | u8 motivo)`. Motivo 1 = acabou o tempo; 19 = saiu
antes (quebrado, morte); 7, 16 e 5 também aparecem, sem significado confirmado. Em ~2% das mensagens o item vem com outro prefixo e mais
dados: o leitor para ali.

### 0x3816 movimento forçado

`varint alvo | varint origem | u32 efeito × 10 + k | 3×f32 posição | u8 4 | u8 1 | u8 1`. Chega ~0,05 s depois
do 0x382A do mesmo efeito em toda derrubada, empurrão e puxão (93 nas capturas de 2026-10-16/17), então serve
para reconhecer controle mesmo sem o efeito na tabela.

## 5. 0x3809 preparo de skill

O boss anuncia a skill antes de executá-la, e o atraso até o 0x3802 é fixo por skill (desvio de
0,00–0,01 s nas runs de 2026-10-16). É o que permite o aviso sair antes do cast.

```
varint conjurador | u8 flag (2 na maioria; 0 em algumas) | u32 skill | u8 1 | u8 2 | varint alvo | 3×f32 posição | ...
```

| Skill | Preparo → cast |
|---|---|
| Raur 1504440 (círculo) / 1504430 (puxão) / 1504450 (zona) | 1,0 / 0,6 / 3,0 s |
| Urahum 1605110 / 1605090 / 1605130 / 1605140 / 1605100 / 1605080 | 1,5 / 1,0 / 1,5 / 1,5 / 1,0 / 1,0 s |
| Auldor 1600930 / 1600925 / 1600920 / 1600970 / 1601000 / 1601090 | 1,0 / 1,1 / 1,1 / 1,3 / 1,15 / 0,8 s |

Sem preparo: 1504470, 1605142, 1601040, 1601010, 1601030.

## 6. 0xE005 medidor de atordoamento

14 bytes, só para bosses: `varint boss | u8 3 | u8 1 | u32 máximo | u32 atual | u8`. O máximo é 1200.
O valor desce com o dano do grupo; perto de 0, o boss usa a skill **1000009** (junto com 1001450) e fica
atordoado por 5,0 s, sem usar skill nenhuma, e o grupo causa 1,3–1,9× mais dano nesses segundos. Depois o
medidor volta a 1200.

## 7. 0x610B / 0x610C tickets (energia Odyle)

- **0x610B:** `varint quantidade | quantidade × ticket`
- **0x610C:** `u8 flags | ticket | u8 motivo | [flags & 1: u32]`
- **ticket:** `u8 flags | u32 id | [1: 8 bytes] | [2: 8 bytes] | [4: varint restante] | [8: varint recarga]`

A energia Odyle é o ticket **60000001**. O rodapé mostra "restante (+recarga)", por exemplo "0 (+40)".

## 8. Skills de boss identificadas

| Boss | Skill | O que é |
|---|---|---|
| todos | `1000009` + `1001450` | atordoamento (seção 6) |
| Raur | `1504450` → `1504451/52` (pulsos) → `1504460` | zona do escudo; explosão ~4,9 s depois |
| Urahum | `1605130` + 6× `1605131` | anéis em sequência |
| Urahum | `1605142` (alvo jogador) | poça roxa de ácido |
| Auldor | `1601090` | início da fase do céu (≈78% e ≈33%) |
| Auldor | `1601060` | vórtice da borda (só na 2ª fase) |
| Auldor | `1601010` | começa a sumir; círculo vermelho em +8 s |
| Auldor | `1601030` (alvo = marcado) | mergulho, ~1,3 s antes do impacto |

## 9. 0x3603 heartbeat

É a resposta ao eco do cliente, a cada 10 s, com 18 bytes: `u16 | i64 relógio em ms (+10 000 por heartbeat) | i64
horário do servidor (ms desde 1970)`. O cliente manda antes um pacote de 12 bytes (cifrado; o tamanho não muda) e o
0x3603 chega logo depois: o tempo entre os dois é o ping até o servidor, com ou sem acelerador (~70 ms com ExitLag
nas capturas de 2026-10-16). O `a2parse/latencia.py` mede assim, sem enviar nada.

## 10. 0x6000 / 0x6001 eventos de campo

- **0x6001** (a cada troca de fase de um evento): `u8 tipo (3) | varint evento | u8 fase | i64 início | i64 início da fase | i64 fim da fase` (ms desde 1970, relógio do servidor; 29 bytes).
- **0x6000** (ao entrar numa zona): `varint quantidade | registros`. Nas capturas veio vazio (`00`); o formato dos registros é suposto igual ao do 0x6001, sem o `tipo`, e só é aceito se os horários fizerem sentido.

Nas capturas de 2026-10-16, às 02:00 e às 23:00, os IDs 110101, 110201 … 110901 (os 9 minijogos do Festival Shugo, abertos juntos; ver `minijogos` em `mecanicas/eventos.json`)
abriram às HH:00:01 na fase 1 (até HH:03:01), passaram à fase 2 às HH:03:02 e fecharam entre HH:05:57 e HH:08:14: cada ID fecha no tempo do seu minijogo (2026-10-19: 110101 = Jump Jump, 175 s; 110901 = Not This Tile?, 195 s; 110601 = Tesouro de Goldrin, 230 s).
Na captura de 2026-10-19 às 14:30, o ID 120101 (Invasão Dimensional) abriu às HH:30:01 na fase 1 (preparação, até HH:33:01)
e passou à fase 2 até HH:43:01 (10 min). Ainda não se sabe se a variante sorteada (Beritra Air Raid, Accursed Sword,
Incursion of the Spirits) muda o ID.
O servidor só manda o evento quando ele abre; o aviso antecipado vem da agenda em `mecanicas/eventos.json`.

## 11. 0x9702 / 0x970B grupo: GS e CP

A lista do grupo chega a cada mudança no grupo ou na sala. Depois de um cabeçalho (mensagem da sala), cada jogador:

```
u8 0x1E | u8 posição | u32 ID | u16 0 | u16 servidor | u8 tamanho + nome (UTF-8) | u32 classe (faixas do 0x3633) |
u32 nível | u32 GS | [u8 opcional] | u16 servidor (de novo) | u16 | u8 | u64 CP | u64 | u8 | u8
```

O byte opcional depois do GS só aparece em alguns jogadores; o servidor repetido serve de âncora. O CP é o que o
perfil do jogo mostra (para você, o "maior" do 0x3656: `u64 CP atual | u64 CP maior`).
