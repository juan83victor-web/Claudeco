"""Fontes livres do Google Fonts (Anton, Montserrat, Caveat) com reserva no sistema."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .ferramentas import PASTA_CACHE, baixar

_BASES = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/",
    "https://github.com/google/fonts/raw/main/ofl/",
]

ARQUIVOS = {
    "anton": ("anton/Anton-Regular.ttf", "Anton-Regular.ttf"),
    "montserrat": ("montserrat/Montserrat%5Bwght%5D.ttf", "Montserrat[wght].ttf"),
    "caveat": ("caveat/Caveat%5Bwght%5D.ttf", "Caveat[wght].ttf"),
}

# Usadas quando não há internet: fontes grossas comuns em Linux.
RESERVAS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def baixar_fontes() -> dict[str, Path | None]:
    pasta = PASTA_CACHE / "fontes"
    return {
        nome: baixar([b + caminho for b in _BASES], pasta / arquivo)
        for nome, (caminho, arquivo) in ARQUIVOS.items()
    }


@lru_cache(maxsize=1)
def _caminhos() -> dict[str, Path | None]:
    return baixar_fontes()


def _reserva() -> str:
    for caminho in RESERVAS:
        if Path(caminho).exists():
            return caminho
    raise FileNotFoundError("nenhuma fonte disponível (sem internet e sem fontes do sistema)")


@lru_cache(maxsize=256)
def fonte(nome: str, tamanho: int, peso: int = 800) -> ImageFont.FreeTypeFont:
    """Carrega a fonte; Montserrat e Caveat são variáveis e recebem o peso."""
    caminho = _caminhos().get(nome)
    if caminho is None:
        return ImageFont.truetype(_reserva(), tamanho)
    f = ImageFont.truetype(str(caminho), tamanho)
    if nome in ("montserrat", "caveat"):
        try:
            f.set_variation_by_axes([peso])
        except Exception:
            pass
    return f
