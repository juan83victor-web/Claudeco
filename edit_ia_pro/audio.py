"""Mixagem (voz + efeitos + trilha) e volume final em -14 LUFS (loudnorm em 2 passadas)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .ferramentas import ErroFerramenta, ffmpeg
from .sons import Som, gerar, inicio_do_arquivo

ALVO_LUFS = -14.0
TRILHA_ABAIXO_DB = 22.0
NIVEL_ARQUIVO_SOM = -16.0  # os efeitos são gerados normalizados em -16 LUFS


def filtro_mix(sons: list[Som], duracao: float, primeira_entrada_som: int, trilha: int | None) -> tuple[str, str]:
    """Monta o filtro de áudio. Devolve (filtro, rótulo de saída).

    Todas as entradas recebem apad + atrim pra saída não encurtar.
    """
    partes = [f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{duracao:.3f},asplit=2[voz][voz_sc]"]
    rotulos = ["[voz]"]
    for n, s in enumerate(sons):
        atraso = int(round(inicio_do_arquivo(s) * 1000))
        ganho = s.volume - NIVEL_ARQUIVO_SOM
        partes.append(
            f"[{primeira_entrada_som + n}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume={ganho:.1f}dB,adelay={atraso}|{atraso},apad,atrim=0:{duracao:.3f}[s{n}]"
        )
        rotulos.append(f"[s{n}]")
    if trilha is not None:
        partes.append(
            f"[{trilha}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume=-{TRILHA_ABAIXO_DB:.0f}dB,apad,atrim=0:{duracao:.3f}[trilha_baixa]"
        )
        # abaixa a trilha quando a voz fala
        partes.append("[trilha_baixa][voz_sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[trilha]")
        rotulos.append("[trilha]")
    else:
        partes.append("[voz_sc]anullsink")
    if len(rotulos) == 1:
        partes.append("[voz]anull[mix]")
    else:
        partes.append(f"{''.join(rotulos)}amix=inputs={len(rotulos)}:normalize=0:duration=first[mix]")
    return ";\n".join(partes), "[mix]"


def medir_loudnorm(arquivo: str | Path, alvo: float = ALVO_LUFS) -> dict:
    """1ª passada: mede o volume."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(arquivo), "-vn",
         "-af", f"loudnorm=I={alvo}:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    achado = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not achado:
        raise ErroFerramenta("não consegui medir o volume:\n" + proc.stderr[-1500:])
    return json.loads(achado[-1])


def filtro_loudnorm(medido: dict, alvo: float = ALVO_LUFS) -> str:
    """2ª passada com os valores medidos."""
    return (
        f"loudnorm=I={alvo}:TP=-1.0:LRA=11:measured_I={medido['input_i']}:measured_TP={medido['input_tp']}:"
        f"measured_LRA={medido['input_lra']}:measured_thresh={medido['input_thresh']}:"
        f"offset={medido['target_offset']}:linear=true,aresample=48000"
    )


def normalizar_volume(entrada: str | Path, saida: str | Path, alvo: float = ALVO_LUFS) -> Path:
    medido = medir_loudnorm(entrada, alvo)
    ffmpeg("-i", str(entrada), "-map", "0:v", "-map", "0:a", "-c:v", "copy",
           "-af", filtro_loudnorm(medido, alvo), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", str(saida))
    return Path(saida)


def medir_lufs(arquivo: str | Path) -> float:
    return float(medir_loudnorm(arquivo)["input_i"])


def arquivos_de_som(sons: list[Som], pasta: str | Path) -> list[Path]:
    return [gerar(s.nome, pasta) for s in sons]
