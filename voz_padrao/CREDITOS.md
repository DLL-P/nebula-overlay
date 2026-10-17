# Vozes do Nebula Overlay

As palavras de ordem que vêm com o app foram geradas com o [Piper](https://github.com/rhasspy/piper) (licença MIT)
por `empacotar/gerar_vozes.py`, com estes modelos de [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices):

| Voz | Modelo | Dados de treino | Licença dos dados |
|---|---|---|---|
| pt-BR | `pt_BR-faber-medium` | [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets) | CC0 |
| en-US | `en_US-joe-medium` | [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets) | CC0 |
| es | `es_MX-claude-high` | [HirCoir/Piper-TTS-Spanish](https://huggingface.co/spaces/HirCoir/Piper-TTS-Spanish) | Apache-2.0 |

Os modelos pt-BR e en-US foram ajustados a partir da voz-base inglesa `lessac` do Piper, cujo conjunto de dados
original é de uso em pesquisa; o Nebula Overlay é gratuito e não comercial. Quem preferir pode usar as vozes do
Windows (engrenagem → Geral → Vozes do Windows) ou pôr os próprios áudios na pasta `voz` do usuário.
