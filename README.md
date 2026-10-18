# Nebula Overlay

Overlay de mecânicas para o **Aion 2**: avisa o que o boss vai fazer, um pouco antes de ele fazer.

- **Alertas antecipados.** O aviso sai quando o boss anuncia a skill, antes do cast. Vem com contagem, ícone, voz curta ("Sai!", "Empilha!", "Engaje!") e uma dica para a sua classe.
- **Linha do tempo do boss.** Mostra as próximas mecânicas com o tempo até cada uma: rotação aprendida das runs, fases por HP e barra de atordoamento. As mais confiáveis sobem para o centro da tela 5 s antes.
- **Painel do boss e do grupo.** HP do boss, atordoamento, dano e DPS de cada jogador com o símbolo da classe, o CP e o GS de cada um, e a energia Odyle.
- **Feito para a sua classe e papel.** Tank, healer, suporte e dps veem alertas diferentes; quem bate de longe não recebe "ENGAJE".
- **Eventos de campo.** Avisa antes do Festival Shugo e dos outros eventos ("Festival Shugo · 5 min") e mostra quanto falta para fechar; o horário exato vem do servidor.
- **Ping no painel.** Tempo de resposta do servidor, com ou sem ExitLag, medido só lendo os pacotes (nada é enviado).
- **Três idiomas.** Português, English, Español (interface, alertas e voz).
- **Atualiza sozinho.** Cada melhoria publicada aqui chega no seu app.

> Projeto de fã, gratuito e não oficial, sem vínculo com a NCSOFT. Aion 2 e os símbolos das classes pertencem à NCSOFT.
> O Nebula Overlay **só lê** o tráfego de rede que já chega ao seu PC: não lê nem altera a memória do jogo, não injeta nada,
> não envia nada ao servidor e não aperta teclas por você. Mesmo assim, os termos do jogo proíbem programas de terceiros:
> **use por sua conta e risco.**

## Instalar

1. Baixe o **NebulaOverlay-Setup.exe** na página de [versões](https://github.com/DLL-P/nebula-overlay/releases/latest) e rode.
   Não precisa de administrador. Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo** (o instalador não tem assinatura digital paga).
2. Instale o **[Npcap](https://npcap.com/#download)** (o instalador avisa se faltar). É ele que deixa o app ler a conexão do jogo.
   Se você usa **ExitLag** ou outro acelerador, marque **"Support loopback traffic"** na instalação do Npcap.
3. Abra o **Nebula Overlay** pelo menu Iniciar e depois o jogo. Use o jogo **em janela ou janela sem bordas** (em tela cheia exclusiva o Windows não deixa nada aparecer por cima).

## Usar

- A janela do Nebula Overlay mostra se achou o jogo. Quando conecta, ela vai para a barra de tarefas; é por ela que você fecha o app.
- No jogo, segure **Alt** para soltar o mouse e clicar no **cadeado** (mover as camadas) ou na **engrenagem** (configurações).
- Na engrenagem: idioma, voz, tamanho, aviso no centro, classe e papel, dicas, burst, gravação das masmorras, relatório da última run e o aprendizado dos roteiros.
- Tudo o que é seu fica em **Documentos\Nebula Overlay**: configurações, capturas das masmorras, relatórios e vozes. Desinstalar não apaga essa pasta.

## Masmorras

Os alertas estão mapeados para os bosses de 8 masmorras (Krao Cave, Draupnir, Urugugu Canyon, Vakron Sky Island, Fire Temple,
Ferocious Horn Den, Shattered Arkanis, Deus Research Base). A Urugugu está completa, com alertas por skill, preparo antecipado e
linha do tempo aprendida; as outras ainda dependem de mais runs mapeadas. Quer ajudar? Veja [como contribuir](CONTRIBUTING.md).

## Vozes

As palavras de ordem vêm no instalador, em português, inglês e espanhol, geradas com o Piper (vozes de licença livre;
créditos em [voz_padrao/CREDITOS.md](voz_padrao/CREDITOS.md)). Na engrenagem dá para trocar pelas vozes do Windows.

## Licença

O código é livre sob a [GPL-3.0](LICENSE): pode usar, estudar, modificar e redistribuir, desde que versões modificadas também tenham o código aberto. A arte do jogo (símbolos das classes) pertence à NCSOFT e não está coberta pela licença.

## Documentação

- [Como contribuir](CONTRIBUTING.md)
- [Guia para mapear um boss](docs/MAPEAR_BOSS.md)
- [Desenvolvimento](docs/DESENVOLVIMENTO.md)
- [Protocolo de rede](docs/PROTOCOLO.md)

---

## English

**Nebula Overlay** is a mechanics overlay for **Aion 2**: early boss alerts (with countdown, short voice callouts and a tip for your class),
a boss timeline learned from real runs, and a boss/party panel. Interface, alerts and voice in Portuguese, English and Spanish. It updates itself.

Install: download **NebulaOverlay-Setup.exe** from [releases](https://github.com/DLL-P/nebula-overlay/releases/latest), install
**[Npcap](https://npcap.com/#download)** (check "Support loopback traffic" if you use ExitLag or another booster), then open Nebula Overlay
and the game in windowed/borderless mode. In game, hold **Alt** to click the padlock and the gear.

Free, unofficial fan project, not affiliated with NCSOFT. It only **reads** network traffic that already reaches your PC (no memory reading,
no injection, nothing sent to the server, no input automation). The game's terms still forbid third-party programs: **use at your own risk**.

## Español

**Nebula Overlay** es un overlay de mecánicas para **Aion 2**: alertas anticipadas de los jefes (con cuenta atrás, voz corta y un consejo
para tu clase), una línea de tiempo del jefe aprendida de runs reales y un panel del jefe y del grupo. Interfaz, alertas y voz en portugués,
inglés y español. Se actualiza solo.

Instalación: descarga **NebulaOverlay-Setup.exe** en [versiones](https://github.com/DLL-P/nebula-overlay/releases/latest), instala
**[Npcap](https://npcap.com/#download)** (marca "Support loopback traffic" si usas ExitLag u otro acelerador) y abre Nebula Overlay y el
juego en ventana o ventana sin bordes. En el juego, mantén **Alt** para hacer clic en el candado y el engranaje.

Proyecto de fans, gratuito y no oficial, sin vínculo con NCSOFT. Solo **lee** el tráfico de red que ya llega a tu PC (no lee memoria, no
inyecta nada, no envía nada al servidor, no automatiza teclas). Aun así, los términos del juego prohíben programas de terceros:
**úsalo bajo tu propio riesgo**.

---

## Apoiar · Support · Apoyar

O Nebula Overlay é um projeto sem fins lucrativos: gratuito, sem anúncios e sem nada pago dentro do app, e vai continuar assim.
Se ele te ajuda e você quiser reconhecer o tempo e o trabalho dedicados à comunidade, doações são bem-vindas. São totalmente
opcionais e não liberam nada a mais. Contribuir com runs, prints, vídeos e traduções ajuda tanto quanto.

**Doar:** [livepix.gg/dellabeats](https://livepix.gg/dellabeats), por Pix, sem precisar criar conta. Também pelo botão "Apoiar o
desenvolvedor" na engrenagem.

Nebula Overlay is a non-profit project: free, no ads and nothing paid inside the app, and it will stay that way. If it helps you and
you'd like to recognize the time and work put into it for the community, donations are welcome. They are fully optional and unlock
nothing extra. Contributing runs, screenshots, videos and translations helps just as much.

**Donate:** [livepix.gg/dellabeats](https://livepix.gg/dellabeats) (also from the "Support the developer" button in the gear). For now it
only takes Pix, Brazil's instant payment; card and international payments are coming.

Nebula Overlay es un proyecto sin fines de lucro: gratuito, sin anuncios y sin nada de pago dentro de la app, y seguirá así. Si te
ayuda y quieres reconocer el tiempo y el trabajo dedicados a la comunidad, las donaciones son bienvenidas. Son totalmente opcionales
y no desbloquean nada extra. Contribuir con runs, capturas, videos y traducciones ayuda igual.

**Donar:** [livepix.gg/dellabeats](https://livepix.gg/dellabeats) (también desde el botón "Apoyar al desarrollador" en el engranaje). Por
ahora solo acepta Pix, el pago instantáneo de Brasil; tarjeta y pagos internacionales vendrán después.
