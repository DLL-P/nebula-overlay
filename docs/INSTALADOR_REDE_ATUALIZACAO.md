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
| Com e sem acelerador | `70 ms` | **Eco do próprio jogo.** A cada 10,000 s o cliente manda um pacote de 12 bytes (cifrado, mas o tamanho é sempre o mesmo) e o servidor responde com o heartbeat 0x3603. O tempo entre os dois é o tempo de resposta do servidor, passando pelo acelerador quando há um. Em 5 capturas com ExitLag: mediana de 69 a 73 ms, mínimo 62 ms. Vale a mediana dos últimos 3 ecos. |
| Lag entre um eco e outro | o número sobe | O servidor manda o horário dele (0x3600) 20 vezes por segundo; chegada − horário = atraso de ida + diferença dos relógios, que é quase constante. Se o atraso do último segundo passa 25 ms acima do melhor dos últimos 30 s, esse excesso soma no número. |
| Primeiros 10 s, conexão direta | ping do TCP | Antes do primeiro eco: tempo entre um segmento TCP do jogo e o ACK do servidor que o cobre (o menor dos últimos 10 s; retransmissões não contam). No loopback do acelerador isso não vale, porque quem confirma é o proxy local. |
| Servidor parado | número em vermelho | Mais de 1 s sem o horário do servidor (que vem a cada 50 ms): mostra há quanto tempo não chega nada. |

Cores: verde até 80 ms, amarelo até 150 ms, vermelho acima.

**Por que o eco é confiável.** O pacote de 12 bytes sai a cada 10,000 s exatos e o 0x3603 chega sempre logo
depois (em 324 heartbeats de 5 capturas, só 1 ficou sem o pacote de 12 bytes antes). O "relógio" dentro do 0x3603
sobe exatamente 10 000 ms por mensagem: é o horário de envio do eco, devolvido pelo servidor.

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
- Se um patch mudar o tamanho do pacote de eco (hoje 12 bytes, `TAM_PING` em `a2parse/latencia.py`), o ping some do
  rodapé até ajustar o número; o teste com captura real avisa.
