import subprocess
from pathlib import Path

import pytest

from edit_ia_pro.transcricao import Palavra


def falas(frases: list[tuple[str, float]], inicio: float = 0.6) -> list[Palavra]:
    """Gera palavras com tempo: cada frase vem com a pausa que vem DEPOIS dela."""
    palavras, t = [], inicio
    for frase, pausa in frases:
        for w in frase.split():
            dur = 0.22 + 0.035 * len(w)
            palavras.append(Palavra(w, round(t, 3), round(t + dur, 3)))
            t += dur + 0.08
        t += pausa - 0.08
    return palavras


ROTEIRO = [
    ("Hoje eu vou te mostrar", 1.0),             # tomada abandonada
    ("Hoje eu vou te mostrar três erros.", 0.8),
    ("Éé", 0.6),                                  # vício
    ("Primeiro, não cortar pausas.", 0.5),
    ("Segundo, legenda pequena.", 0.5),
    ("Terceiro, sem gancho.", 0.9),
    ("Em 5 minutos fica pronto!", 0.6),
    ("Acabou!", 0.7),
    ("Comenta EDIT aqui embaixo.", 0.8),
]


@pytest.fixture(scope="session")
def roteiro() -> list[Palavra]:
    return falas(ROTEIRO)


def gerar_video(destino: Path, palavras: list[Palavra], largura=540, altura=960) -> Path:
    """Vídeo sintético: cada palavra é um bipe; o resto é silêncio."""
    duracao = palavras[-1].fim + 0.8
    termos = "+".join(
        f"between(t,{p.inicio},{p.fim})*sin(2*PI*{300 + 40 * (i % 7)}*t)" for i, p in enumerate(palavras)
    )
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=s={largura}x{altura}:r=30:d={duracao}",
        "-f", "lavfi", "-i", f"aevalsrc='0.5*({termos})':s=48000:d={duracao}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(destino),
    ], check=True)
    return destino


@pytest.fixture(scope="session")
def video_sintetico(tmp_path_factory, roteiro) -> Path:
    return gerar_video(tmp_path_factory.mktemp("video") / "bruto.mp4", roteiro)
