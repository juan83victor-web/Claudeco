"""Monta o corte.mp4: junta os trechos com trim/atrim + concat, fade de 10 ms nas emendas."""

from __future__ import annotations

from pathlib import Path

from . import FPS
from .corte import Trecho
from .ferramentas import ffmpeg, sondar

FADE = 0.01  # 10 ms em cada emenda evita estalo


def tamanho_saida(info: dict) -> tuple[int, int]:
    return (1080, 1920) if info["altura"] >= info["largura"] else (1920, 1080)


def filtro_corte(trechos: list[Trecho], largura: int, altura: int) -> str:
    linhas = []
    for i, t in enumerate(trechos):
        linhas.append(
            f"[0:v]trim=start={t.inicio:.3f}:end={t.fim:.3f},setpts=PTS-STARTPTS,"
            f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
            f"crop={largura}:{altura},setsar=1,fps={FPS}[v{i}];"
        )
        fim_fade = max(t.duracao - FADE, 0)
        linhas.append(
            f"[0:a]atrim=start={t.inicio:.3f}:end={t.fim:.3f},asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates=48000:channel_layouts=stereo,"
            f"afade=t=in:st=0:d={FADE},afade=t=out:st={fim_fade:.3f}:d={FADE}[a{i}];"
        )
    entradas = "".join(f"[v{i}][a{i}]" for i in range(len(trechos)))
    linhas.append(f"{entradas}concat=n={len(trechos)}:v=1:a=1[v][a]")
    return "\n".join(linhas)


def montar_corte(video: str | Path, trechos: list[Trecho], saida: str | Path) -> Path:
    """Vertical: 1080x1920, 30 fps, H.264 CRF 20, AAC 192k. O original não é alterado."""
    if not trechos:
        raise ValueError("nenhum trecho para montar")
    info = sondar(video)
    if not info["tem_audio"]:
        raise ValueError("o vídeo não tem som")
    largura, altura = tamanho_saida(info)
    saida = Path(saida)
    script = saida.with_suffix(".filtro.txt")
    script.write_text(filtro_corte(trechos, largura, altura))
    ffmpeg(
        "-i", str(video), "-filter_complex_script", str(script),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(saida),
    )
    return saida
