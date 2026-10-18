"""Acesso ao ffmpeg/ffprobe e downloads (fontes e detector de rosto)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

PASTA_CACHE = Path(os.environ.get("EDIT_IA_PRO_CACHE", Path.home() / ".cache" / "edit-ia-pro"))


class ErroFerramenta(RuntimeError):
    """Falha ao rodar ffmpeg/ffprobe ou ao baixar algo."""


def garantir_ffmpeg() -> str:
    """Devolve o caminho do ffmpeg, instalando o static-ffmpeg se faltar."""
    caminho = shutil.which("ffmpeg")
    if caminho and shutil.which("ffprobe"):
        return caminho
    try:
        import static_ffmpeg  # type: ignore

        static_ffmpeg.add_paths()
    except ImportError as erro:
        raise ErroFerramenta("ffmpeg não encontrado. Rode: pip install static-ffmpeg") from erro
    caminho = shutil.which("ffmpeg")
    if not caminho:
        raise ErroFerramenta("ffmpeg não encontrado mesmo após static-ffmpeg")
    return caminho


def rodar(args: list[str], capturar: bool = True) -> subprocess.CompletedProcess:
    """Roda um comando e levanta ErroFerramenta com o fim do stderr se falhar."""
    proc = subprocess.run(args, capture_output=capturar, text=True)
    if proc.returncode != 0:
        fim = (proc.stderr or "")[-2000:]
        raise ErroFerramenta(f"falhou: {' '.join(args[:3])} ...\n{fim}")
    return proc


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return rodar(["ffmpeg", "-hide_banner", "-y", "-loglevel", "error", *args])


def sondar(caminho: str | Path) -> dict:
    """Duração, tamanho, fps e se tem áudio."""
    proc = rodar([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(caminho),
    ])
    dados = json.loads(proc.stdout)
    video = next((s for s in dados["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in dados["streams"] if s["codec_type"] == "audio"), None)
    info = {
        "duracao": float(dados["format"].get("duration", 0.0)),
        "tem_audio": audio is not None,
        "largura": 0,
        "altura": 0,
        "fps": 0.0,
    }
    if video:
        largura, altura = int(video["width"]), int(video["height"])
        rotacao = _rotacao(video)
        if rotacao in (90, 270):
            largura, altura = altura, largura
        num, den = video.get("avg_frame_rate", "0/1").split("/")
        info.update(largura=largura, altura=altura, fps=float(num) / float(den) if float(den) else 0.0)
    info["vertical"] = info["altura"] > info["largura"]
    return info


def _rotacao(stream: dict) -> int:
    rot = stream.get("tags", {}).get("rotate")
    if rot is None:
        for lado in stream.get("side_data_list", []):
            if "rotation" in lado:
                rot = lado["rotation"]
    return abs(int(float(rot or 0))) % 360


def detectar_silencios(caminho: str | Path, ruido_db: float = -35, minimo: float = 0.25) -> list[tuple[float, float]]:
    """Trechos de silêncio via silencedetect=noise=-35dB:d=0.25."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(caminho), "-vn",
         "-af", f"silencedetect=noise={ruido_db}dB:d={minimo}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    inicios = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    fins = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    if len(fins) < len(inicios):  # silêncio até o fim do arquivo
        fins.append(sondar(caminho)["duracao"])
    return [(max(0.0, a), b) for a, b in zip(inicios, fins)]


def baixar(urls: list[str], destino: Path, tamanho_minimo: int = 10_000) -> Path | None:
    """Baixa o primeiro link que funcionar. Devolve None se nenhum funcionar.

    O tamanho mínimo descarta respostas de erro e ponteiros do Git LFS.
    """
    if destino.exists() and destino.stat().st_size >= tamanho_minimo:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                dados = resp.read()
        except Exception:
            continue
        if len(dados) >= tamanho_minimo:
            destino.write_bytes(dados)
            return destino
    return None
