"""Posição do rosto, pra nunca pôr texto em cima dos olhos e da boca."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import ZONA_SEGURA
from .ferramentas import PASTA_CACHE, baixar

URLS_YUNET = [
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
]

LEGENDA_Y = 1180  # centro padrão da legenda


@dataclass
class Rosto:
    t: float
    x: int
    y: int
    w: int
    h: int

    @property
    def centro(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def zona_proibida(self) -> tuple[int, int]:
        """Faixa vertical dos olhos até a boca (com margem)."""
        return int(self.y + 0.15 * self.h), int(self.y + 0.95 * self.h)


def _detector(largura: int, altura: int):
    import cv2

    modelo = baixar(URLS_YUNET, PASTA_CACHE / "modelos" / "yunet.onnx", tamanho_minimo=100_000)
    if modelo is not None and hasattr(cv2, "FaceDetectorYN"):
        yunet = cv2.FaceDetectorYN.create(str(modelo), "", (largura, altura), 0.7)

        def detectar(quadro):
            _, faces = yunet.detect(quadro)
            return [tuple(int(v) for v in f[:4]) for f in (faces if faces is not None else [])]

        return detectar
    haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def detectar(quadro):
        cinza = cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
        return [tuple(int(v) for v in f) for f in haar.detectMultiScale(cinza, 1.1, 5, minSize=(80, 80))]

    return detectar


def detectar_rostos(video: str | Path, passo: float = 0.5) -> list[Rosto]:
    """Detecta o maior rosto a cada `passo` segundos."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    detectar = _detector(largura, altura)
    rostos = []
    pulo = max(1, int(round(fps * passo)))
    for indice in range(0, max(total, 1), pulo):
        cap.set(cv2.CAP_PROP_POS_FRAMES, indice)
        ok, quadro = cap.read()
        if not ok:
            break
        caixas = detectar(quadro)
        if caixas:
            x, y, w, h = max(caixas, key=lambda c: c[2] * c[3])
            rostos.append(Rosto(round(indice / fps, 3), x, y, w, h))
    cap.release()
    return rostos


def rostos_entre(rostos: list[Rosto], a: float, b: float) -> list[Rosto]:
    dentro = [r for r in rostos if a - 0.25 <= r.t <= b + 0.25]
    if dentro or not rostos:
        return dentro
    return [min(rostos, key=lambda r: min(abs(r.t - a), abs(r.t - b)))]


def colide(faixa: tuple[int, int], rostos: list[Rosto]) -> bool:
    a, b = faixa
    return any(min(b, r.zona_proibida()[1]) > max(a, r.zona_proibida()[0]) for r in rostos)


def posicao_vertical(altura_caixa: int, rostos: list[Rosto], preferido: int = LEGENDA_Y) -> int:
    """Centro y do texto: o preferido; se cair no rosto, sobe pra cima do rosto.

    Sem espaço em cima, vai pra baixo. Sempre dentro da zona segura.
    """
    _, topo, _, base = ZONA_SEGURA
    meio = altura_caixa // 2

    def limitar(y: int) -> int:
        return min(max(y, topo + meio), base - meio)

    y = limitar(preferido)
    if not colide((y - meio, y + meio), rostos):
        return y
    proibida_topo = min(r.zona_proibida()[0] for r in rostos)
    proibida_base = max(r.zona_proibida()[1] for r in rostos)
    acima = proibida_topo - 20 - meio
    if acima - meio >= topo:
        return acima
    abaixo = proibida_base + 20 + meio
    if abaixo + meio <= base:
        return abaixo
    return y  # rosto ocupa a tela inteira: fica no preferido


def centro_do_rosto(rostos: list[Rosto], largura: int = 1080, altura: int = 1920) -> tuple[int, int]:
    if not rostos:
        return largura // 2, altura // 2
    xs = sorted(r.centro[0] for r in rostos)
    ys = sorted(r.centro[1] for r in rostos)
    return xs[len(xs) // 2], ys[len(ys) // 2]
