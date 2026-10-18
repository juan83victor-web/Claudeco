"""Transcrição com tempo por palavra (faster-whisper)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Palavra:
    texto: str
    inicio: float
    fim: float

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


def transcrever(video: str | Path, modelo: str = "small", nomes_dificeis: list[str] | None = None) -> list[Palavra]:
    """Transcreve em português. Use modelo="base" se o "small" ficar lento demais."""
    from faster_whisper import WhisperModel  # import tardio: pacote pesado

    whisper = WhisperModel(modelo, device="cpu", compute_type="int8")
    dica = ", ".join(nomes_dificeis) if nomes_dificeis else None
    segmentos, _ = whisper.transcribe(
        str(video), language="pt", word_timestamps=True, vad_filter=True, initial_prompt=dica,
    )
    palavras = []
    for seg in segmentos:
        for p in seg.words or []:
            texto = p.word.strip()
            if texto:
                palavras.append(Palavra(texto, round(p.start, 3), round(p.end, 3)))
    return palavras


def salvar(palavras: list[Palavra], caminho: str | Path) -> None:
    Path(caminho).write_text(json.dumps([asdict(p) for p in palavras], ensure_ascii=False, indent=1))


def carregar(caminho: str | Path) -> list[Palavra]:
    return [Palavra(**d) for d in json.loads(Path(caminho).read_text())]
