"""Cor de destaque: a pessoa diz o nome ("amarelo", "azul bebê") ou o código."""

from __future__ import annotations

import re
import unicodedata

PADRAO = "#FFC400"

NOMES = {
    "amarelo": "#FFC400",
    "amarelo ouro": "#FFB300",
    "dourado": "#FFB300",
    "laranja": "#FF7A00",
    "vermelho": "#FF2D2D",
    "rosa": "#FF4FA3",
    "rosa choque": "#FF1F8E",
    "pink": "#FF1F8E",
    "roxo": "#8B5CF6",
    "lilas": "#C084FC",
    "azul": "#2F80FF",
    "azul bebe": "#8EC9FF",
    "azul claro": "#5AB8FF",
    "azul marinho": "#1E3A8A",
    "ciano": "#00D1FF",
    "turquesa": "#1DD3C0",
    "verde": "#22C55E",
    "verde limao": "#B6FF3B",
    "verde agua": "#5EEAD4",
    "branco": "#FFFFFF",
    "preto": "#111111",
    "cinza": "#9CA3AF",
}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def resolver_cor(entrada: str | None) -> str:
    """Converte nome ou código (#abc, #aabbcc, aabbcc) em '#RRGGBB'."""
    if not entrada:
        return PADRAO
    texto = _sem_acento(entrada.strip().lower())
    codigo = texto.lstrip("#")
    if re.fullmatch(r"[0-9a-f]{6}", codigo):
        return "#" + codigo.upper()
    if re.fullmatch(r"[0-9a-f]{3}", codigo):
        return "#" + "".join(c * 2 for c in codigo).upper()
    texto = re.sub(r"\s+", " ", texto)
    if texto in NOMES:
        return NOMES[texto]
    # "amarelo forte", "um rosa": usa o nome conhecido mais longo contido no texto
    for nome in sorted(NOMES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(nome)}\b", texto):
            return NOMES[nome]
    raise ValueError(f"cor desconhecida: {entrada!r}")


def rgb(cor: str, alfa: int = 255) -> tuple[int, int, int, int]:
    cor = resolver_cor(cor)
    return int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16), alfa
