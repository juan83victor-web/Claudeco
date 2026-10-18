"""Olhar antes de mandar: quadros espalhados e duração batendo com o corte."""

from __future__ import annotations

from pathlib import Path

from .ferramentas import ffmpeg, sondar

TOLERANCIA = 0.1  # s


def extrair_quadros(video: str | Path, pasta: str | Path, quantos: int = 6) -> list[Path]:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    duracao = sondar(video)["duracao"]
    quadros = []
    for i in range(quantos):
        t = duracao * (i + 0.5) / quantos
        destino = pasta / f"quadro_{i + 1}.jpg"
        ffmpeg("-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(destino))
        quadros.append(destino)
    return quadros


def quadro_em(video: str | Path, t: float, destino: str | Path, largura: int = 540) -> Path:
    """Um quadro reduzido, pra mandar como imagem quando for pedir uma escolha."""
    ffmpeg("-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={largura}:-2", "-q:v", "4", str(destino))
    return Path(destino)


def duracao_bate(final: str | Path, corte: str | Path) -> tuple[bool, float, float]:
    """A voz não pode escorregar: final e corte com a mesma duração."""
    a, b = sondar(final)["duracao"], sondar(corte)["duracao"]
    return abs(a - b) <= TOLERANCIA, a, b
