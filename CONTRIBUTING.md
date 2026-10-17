# Como contribuir

Toda ajuda é bem-vinda, e você não precisa saber programar. O mapeamento de verdade (ligar cada skill à mecânica, medir
tempos, escrever os alertas) é feito pelo mantenedor; o que mais ajuda é **material das lutas**.

## O que você pode mandar

| Tipo | Como | Onde |
|---|---|---|
| **Prints** do telegraph (círculo, leque, marca no chão) | imagem com o boss e o efeito visíveis | [issue "Mecânica"](../../issues/new?template=mecanica.yml) |
| **Vídeos** de uma luta inteira | link (YouTube não listado, Drive...) com o horário de início da gravação | [issue "Mecânica"](../../issues/new?template=mecanica.yml) |
| **Textos**: o que acontece, o que fazer, o que o alerta deveria dizer | descrição livre | [issue "Mecânica"](../../issues/new?template=mecanica.yml) |
| **Capturas do Nebula Overlay** (`.pcap` da pasta capturas) | **envio privado**, ver abaixo | [issue "Captura de run"](../../issues/new?template=captura.yml) |
| **Dados de outros programas de leitura** (logs de luta, linhas do tempo, tabelas) | arquivo ou link, dizendo de qual programa veio | [issue "Captura de run"](../../issues/new?template=captura.yml) |
| **Traduções** e correções de texto | o texto atual e a sugestão | [issue "Tradução"](../../issues/new?template=traducao.yml) ou PR em `mecanicas/traducoes.json` |
| **Erros** | o que aconteceu e o arquivo `nebula.log` (Documentos\Nebula Overlay) | [issue "Problema"](../../issues/new?template=bug.yml) |
| **Código** | pull request; os testes rodam sozinhos | — |

## Consentimento e privacidade

Ao mandar material, você autoriza o uso dele para melhorar o Nebula Overlay. Antes, saiba o que cada coisa contém:

- **Prints e vídeos** podem mostrar nomes de personagens, guilda e chat. Corte ou borre o que não quiser mostrar; issues são públicas.
- **Capturas (`.pcap`)** contêm tudo o que o jogo recebeu durante a gravação: nomes de personagens (o seu e os do grupo),
  servidor e mensagens de chat que chegaram nesse tempo. Por isso:
  - **não anexe `.pcap` em issue** (issues são públicas);
  - abra a issue "Captura de run" dizendo que tem a captura, e o mantenedor combina um envio privado;
  - do arquivo, só saem para o projeto dados de luta (IDs de skill, tempos, HP do boss). A captura em si **nunca é publicada** e
    é apagada quando não for mais necessária. Você pode pedir a exclusão a qualquer momento na mesma issue.
- Ninguém é obrigado a nada: dá para ajudar só com texto.

## Código

- O app roda do código-fonte com Python 3.12: veja [docs/DESENVOLVIMENTO.md](docs/DESENVOLVIMENTO.md).
- Cada commit no `main` vira uma versão nova, que todos recebem pela atualização automática. Por isso todo PR passa pelos testes
  (`python -m unittest discover -s testes`) e pela revisão do mantenedor.
- Não mande tabelas extraídas dos arquivos do jogo (nomes de NPC e skill em massa): elas não entram no repositório.
- Mecânica nova precisa de tradução em `mecanicas/traducoes.json` (o teste `test_todo_texto_de_alerta_tem_traducao` avisa).

---

**English:** contributions are welcome: screenshots, videos, text descriptions, Nebula Overlay captures and data from other combat-reading
tools. Never attach `.pcap` files to public issues (they contain character names and chat); open a "Captura de run" issue and a private
transfer will be arranged. By sending material you allow its use to improve Nebula Overlay; captures are never published.

**Español:** se aceptan contribuciones: capturas de pantalla, videos, descripciones, capturas del Nebula Overlay y datos de otros programas
de lectura. Nunca adjuntes `.pcap` en issues públicas (contienen nombres de personajes y chat); abre una issue "Captura de run" y se acordará
un envío privado. Al enviar material autorizas su uso para mejorar Nebula Overlay; las capturas nunca se publican.
