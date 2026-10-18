# EDIT IA PRO · editor de vídeo curto

Implementação em Python do roteiro **EDIT IA PRO · Modo celular**: a IA recebe o
vídeo que a pessoa gravou no celular e devolve o vídeo editado, com 2 aprovações
(corte e amostra) no caminho.

## O que faz

| Passo do roteiro | Módulo |
| --- | --- |
| Receber (duração, formato, som) | `ferramentas.sondar`, `cli receber` |
| Transcrever com tempo por palavra (faster-whisper, `small`, pt, VAD) | `transcricao` |
| Cortar pausas > 0,25 s (confirmadas com `silencedetect`), tomadas repetidas (fica a última completa), "éé"/"hum"/"tipo assim", folga 0,06 s / 0,10 s sem entrar na palavra vizinha, palavras suspeitas > 1,2 s, plano em 3 linhas | `corte` |
| Montar `corte.mp4` (trim/atrim + concat, fade de 10 ms, 1080x1920, 30 fps, CRF 20, AAC 192k) | `montagem` |
| 7 legendas: Impacto, Caixa na palavra, Palavra gigante, Pulso, Fita, Papelaria, Discreta | `legendas` |
| 5 ganchos: Manchete, Tarjas, Balão, Marca-texto, Vidro escuro (entrada 90% → 100%) + sugestão de ganchos tirados da fala | `ganchos` |
| Cor de destaque por nome ("azul bebê") ou código, padrão `#FFC400` | `cores` |
| Rosto a cada 0,5 s (YuNet, ou Haar sem internet); texto nunca nos olhos/boca; zona segura x 140–940, y 230–1530 | `rosto` |
| Animações (palavra de impacto, lista com check, passo a passo, número contando, notificação, carimbo, destaque desenhado, comentário digitado, barra enchendo), ritmo poucas/médias/nenhuma | `motion` |
| Zoom 1,00/1,08 alternado nas emendas, tela dividida, chamada final | `final` |
| Efeitos sonoros gerados no ffmpeg, nunca dois a menos de 0,6 s | `sons` |
| Trilha 22 dB abaixo com `sidechaincompress`, `loudnorm` em 2 passadas a -14 LUFS | `audio` |
| Frases que a Meta reprova (ganho em dinheiro, "em X dias", "garantido", etc.) | `meta` |
| 6 quadros pra conferir, duração do final = duração do corte | `conferir` |
| Memória em `edit-ia-pro/<video>/estado.md` | `estado` |

## Uso

```bash
pip install -e '.[transcricao,teste]'

python -m edit_ia_pro receber video.mp4
python -m edit_ia_pro ouvir video.mp4            # mostra o plano e pergunta se pode cortar
python -m edit_ia_pro cortar video.mp4           # gera corte.mp4
python -m edit_ia_pro cortar video.mp4 --tirar 3-5   # "entre 3 e 5 segundos tira essa parte"
python -m edit_ia_pro sugerir video.mp4          # 2 ganchos + lista de animações
python -m edit_ia_pro amostra video.mp4 --estilo estilo.json
python -m edit_ia_pro final video.mp4 --estilo estilo.json
python -m edit_ia_pro meta video.mp4
```

`estilo.json` (tudo opcional; o padrão é a recomendação do roteiro):

```json
{
  "legenda": "Impacto",
  "gancho": "Manchete",
  "texto_gancho": "O erro que trava seu vídeo",
  "cor": "amarelo",
  "zoom": true,
  "ritmo": "medias",
  "chamada": "Comenta EDIT",
  "trilha": "musica.mp3",
  "telas_divididas": [{"imagem": "print.png", "inicio": 5.0, "fim": 8.0}]
}
```

Os arquivos ficam em `edit-ia-pro/<video>/`. O vídeo original nunca é alterado.

## Testes

```bash
python -m pytest            # tudo (uns 2 minutos: renderiza vídeos)
python -m pytest -m "not lento"   # só a lógica, em segundos
```

Os testes de ponta a ponta geram um vídeo sintético (cada palavra é um bipe),
cortam, montam o vídeo completo com gancho, legenda, animações, tela dividida,
trilha e chamada, e conferem: 1080x1920 a 30 fps, sem silêncio > 0,25 s no corte,
duração final igual à do corte, volume em -14 LUFS e sons espaçados.
