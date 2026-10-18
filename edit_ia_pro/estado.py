"""Memória do vídeo: uma linha no estado.md a cada decisão."""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from pathlib import Path

RAIZ = "edit-ia-pro"


def pasta_do_video(base: str | Path, nome: str) -> Path:
    """edit-ia-pro/<video>/ com nome curto e sem acento."""
    curto = unicodedata.normalize("NFD", Path(nome).stem.lower())
    curto = "".join(c for c in curto if unicodedata.category(c) != "Mn")
    curto = re.sub(r"[^a-z0-9]+", "-", curto).strip("-")[:24] or "video"
    pasta = Path(base) / RAIZ / curto
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def anotar(pasta: str | Path, decisao: str) -> None:
    arquivo = Path(pasta) / "estado.md"
    if not arquivo.exists():
        arquivo.write_text("# Estado da edição\n\n")
    agora = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with arquivo.open("a") as f:
        f.write(f"- {agora} · {decisao.strip()}\n")


def ler(pasta: str | Path) -> list[str]:
    arquivo = Path(pasta) / "estado.md"
    if not arquivo.exists():
        return []
    return [l[2:] for l in arquivo.read_text().splitlines() if l.startswith("- ")]
