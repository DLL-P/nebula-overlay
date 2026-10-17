# Instalador, latência e atualização (plano)

Três pedidos: um arquivo só para levar a outra máquina, a latência com o servidor no rodapé do painel sem
depender do ExitLag, e atualização com um clique. Abaixo, o que já existia, o que foi feito agora e o que fica
para depois.

## 1. Um arquivo só

**O que já existia.** O `empacotar/construir.py` gera o app com o PyInstaller (`dist/NebulaOverlay/`, uma pasta)
e, com o Inno Setup 6, o **`NebulaOverlay-Setup.exe`**, que é um arquivo único com tudo dentro. O GitHub Actions
(`.github/workflows/lancar.yml`) gera e publica esse instalador a cada commit no `main` (a versão
`v2026.10.17.4` já está publicada com ele e o `.sha256`).

**Como levar para outra máquina.** Copie só o `NebulaOverlay-Setup.exe` (da página de versões do GitHub ou do
`dist/`) e rode. Ele instala por usuário, sem pedir administrador, em `%LOCALAPPDATA%\Programs\Nebula Overlay`,
cria o atalho no menu Iniciar e abre o app. As configurações ficam em `Documentos\Nebula Overlay`.

**Por que instalador e não um `.exe` portátil (PyInstaller `--onefile`).** O `--onefile` se descompacta numa
pasta temporária a cada abertura (abre mais devagar e é o formato que mais leva falso positivo de antivírus) e
não consegue se trocar sozinho enquanto roda, o que complica a atualização. O instalador resolve as duas coisas:
a atualização baixa o instalador novo e roda em modo silencioso.

**Gerar na sua máquina.** Falta só o Inno Setup (sem ele sai só a pasta):

```bash
winget install JRSoftware.InnoSetup
```

```bash
python empacotar/construir.py --versao 2026.10.17.5
```

**Npcap.** Continua pré-requisito e **não vai dentro do instalador**: a licença gratuita do Npcap não permite
redistribuir o instalador dele embutido em outro programa (isso exige a licença OEM). O que o Nebula faz:

- o instalador confere se o Npcap está instalado (registro `SOFTWARE\Npcap` ou `System32\Npcap\wpcap.dll`) e,
  se faltar, oferece abrir a página oficial de download, lembrando de marcar "Support loopback traffic" para
  quem usa acelerador;
- o app, se não achar o Npcap, mostra o aviso na janela principal com o botão **Baixar o Npcap** e o
  **Tentar de novo** (não precisa reiniciar).

**Pendente (opcional).** Assinatura digital do instalador (tira o aviso "O Windows protegeu o computador"); há
certificados gratuitos para projetos de código aberto (ex.: SignPath Foundation), que exigem cadastro do projeto.

## 2. Latência sem depender do ExitLag

**Captura com e sem acelerador (já existia, agora mais robusta).**

- Com acelerador (ExitLag, NoPing, GearUP...): o jogo conecta num proxy local; o `gravar.rota_do_jogo()` acha o
  proxy pelo `netstat` e a captura fica no loopback, na porta dele.
- Sem acelerador: a captura fica na placa de rede. **Novo:** a placa agora é escolhida pelo IP local das conexões
  do próprio `AION2.exe` (vale para VPN, cabo + Wi-Fi, placa virtual), e só se não der usa a placa da rota padrão.
  Para casos estranhos, `"placa": "<parte do nome>"` no `overlay.json` força a placa.
- **Novo:** se você liga ou desliga o acelerador com o jogo aberto, o jogo reconecta por outro caminho. O overlay
  percebe (20 s sem mensagem do jogo), olha a rota de novo e troca a captura sozinho.
- O rodapé do painel não mostra mais "via ExitLag"; a rota aparece na janela principal ("Conectado · direto").

**Como a latência é medida, só lendo (nada é enviado ao servidor).**

| Situação | O que aparece | Como |
|---|---|---|
| Conexão direta | `42 ms` (ping) | Tempo entre um segmento TCP que o jogo envia e o ACK do servidor que cobre esse segmento, na própria captura. Vale o menor dos últimos 10 s (o ACK pode sair atrasado, junto com o próximo pacote do servidor, mas nunca adiantado). Retransmissões são ignoradas (algoritmo de Karn). |
| Com acelerador | `±4 ms` (oscilação) | No loopback quem responde o TCP é o proxy local (o RTT dá ~0 ms) e o sentido cliente → servidor é cifrado, então não há eco do protocolo para cronometrar. O que dá para medir é a **oscilação**: o servidor manda o horário dele (0x3600) 20 vezes por segundo; a diferença entre a hora de chegada e esse horário é "atraso de ida + diferença dos relógios". A diferença dos relógios é quase constante, então o quanto o atraso do último segundo (mediana) sobe acima do mínimo dos últimos 30 s é o lag que você sente. Numa captura real com ExitLag deu ±3 a ±9 ms. |
| Servidor parado | número em vermelho | Mais de 1 s sem o horário do servidor (que vem a cada 50 ms): mostra há quanto tempo não chega nada. |

Cores: verde até 80 ms de ping (ou 15 ms de oscilação), amarelo até 150 ms (ou 40 ms), vermelho acima.

**Por que não dá o ping absoluto com acelerador.** O túnel do acelerador vai para um servidor dele, não para o
do jogo, e o que passa no loopback é respondido localmente. O 0x3603 (heartbeat) também não serve: o relógio
dele sobe exatamente 10 000 ms por mensagem, é do servidor, não um eco do cliente. Medir de verdade exigiria
mandar algo (um ping), o que a regra do projeto proíbe.

**Onde está no código.** `a2parse/latencia.py` (medição, com testes em `testes/test_latencia.py`), ligado na
`Sessao` (`a2parse/aovivo.py`); desenho no rodapé do painel, à esquerda da Odyle (`overlay.py`); opção
"Mostrar a latência" na aba Geral da engrenagem.

## 3. Atualização com um clique

**O que já existia.** `a2parse/atualizar.py`: ao abrir, o app consulta `api.github.com/repos/DLL-P/nebula-overlay/releases/latest`;
se houver versão mais nova com `NebulaOverlay-Setup.exe` e `.sha256`, mostra o aviso na janela principal. Fora do
jogo, com "Atualizar sozinho" ligado, baixa e instala sozinho; o download só é aceito se vier de
`https://github.com/DLL-P/nebula-overlay/releases/download/`, e o SHA-256 tem de bater. O instalador roda com
`/SILENT`, fecha o app, troca os arquivos e o abre de novo. Rodando do código-fonte (versão `dev`) a atualização
fica desligada.

**Feito agora.**

- **Botão no overlay:** quando há versão nova, aparece um botão com seta ao lado da engrenagem, no rodapé do painel
  (segure Alt e clique). Um clique baixa, instala e reinicia; o botão mostra o progresso do download.
- **Na engrenagem:** a aba Sobre mostra "Nova versão X disponível" com o botão **Atualizar agora**.
- **Sessões longas:** o app olha de novo a cada 6 horas (antes era só ao abrir).
- **Download mais fechado:** além do prefixo, o endereço é conferido por partes (só `https`, só `github.com`, sem
  `..`), para nenhum caminho "escapar" do repositório.

**Funciona no executável instalado**, que é o único caso em que faz sentido trocar arquivos. Pelo código-fonte,
atualize com `git pull`.

## Fica para depois

- Assinatura digital do instalador (ver item 1).
- Notas da versão no aviso (o texto do commit já vem em `info["notas"]`).
- Se um dia houver um eco no protocolo (uma mensagem do cliente que o servidor responde na hora), dá para ter o
  ping absoluto também com acelerador; hoje o sentido cliente → servidor é cifrado.
