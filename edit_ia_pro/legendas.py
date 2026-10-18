"""Legendas animadas palavra por palavra nos 7 estilos do painel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from . import ALTURA, LARGURA, ZONA_SEGURA
from .cores import rgb
from .desenho import Peca, caber, desenhar_linhas
from .fontes import fonte
from .rosto import LEGENDA_Y, Rosto, posicao_vertical, rostos_entre
from .transcricao import Palavra

ESTILOS = ("impacto", "caixa", "gigante", "pulso", "fita", "papelaria", "discreta")
NOMES_ESTILOS = {
    "impacto": "impacto", "caixa na palavra": "caixa", "caixa": "caixa",
    "palavra gigante": "gigante", "gigante": "gigante", "pulso": "pulso",
    "fita": "fita", "papelaria": "papelaria", "discreta": "discreta",
}
LARGURA_UTIL = ZONA_SEGURA[2] - ZONA_SEGURA[0]  # 800 px
BRANCO = (255, 255, 255, 255)
PRETO = (0, 0, 0, 255)
ESCURO = (20, 20, 24, 255)


def estilo_legenda(nome: str) -> str:
    chave = nome.strip().lower()
    if chave not in NOMES_ESTILOS:
        raise ValueError(f"estilo de legenda desconhecido: {nome}")
    return NOMES_ESTILOS[chave]


@dataclass
class Grupo:
    palavras: list[Palavra]

    @property
    def inicio(self) -> float:
        return self.palavras[0].inicio

    @property
    def fim(self) -> float:
        return self.palavras[-1].fim


def agrupar(palavras: list[Palavra], estilo: str = "impacto", pausa: float = 0.3) -> list[Grupo]:
    """1 a 3 palavras por vez, quebrando em pontuação e pausa."""
    maximo, max_letras = {"gigante": (1, 99), "discreta": (8, 42), "fita": (4, 24), "papelaria": (4, 26)}.get(estilo, (3, 18))
    grupos: list[Grupo] = []
    atual: list[Palavra] = []
    for p in palavras:
        letras = sum(len(x.texto) + 1 for x in atual) + len(p.texto)
        if atual and (len(atual) >= maximo or letras > max_letras or p.inicio - atual[-1].fim > pausa):
            grupos.append(Grupo(atual))
            atual = []
        atual.append(p)
        if p.texto.rstrip()[-1:] in ".,!?;:…":
            grupos.append(Grupo(atual))
            atual = []
    if atual:
        grupos.append(Grupo(atual))
    return grupos


@dataclass
class Estado:
    grupo: int
    falada: int
    inicio: float
    fim: float


def estados(grupos: list[Grupo], segura: float = 0.4) -> list[Estado]:
    """Cada estado = grupo na tela + qual palavra está sendo falada."""
    saida = []
    for g, grupo in enumerate(grupos):
        proximo = grupos[g + 1].inicio if g + 1 < len(grupos) else grupo.fim + segura
        fim_grupo = min(grupo.fim + segura, proximo)
        for k, p in enumerate(grupo.palavras):
            inicio = grupo.inicio if k == 0 else p.inicio
            fim = grupo.palavras[k + 1].inicio if k + 1 < len(grupo.palavras) else fim_grupo
            if fim > inicio:
                saida.append(Estado(g, k, round(inicio, 3), round(fim, 3)))
    return saida


def _texto(p: Palavra, maiusculo: bool) -> str:
    t = p.texto.strip().strip(",;:")
    return t.upper() if maiusculo else t


def desenhar(estilo: str, grupo: Grupo, falada: int, cor: str, y: int = LEGENDA_Y) -> Image.Image:
    """PNG transparente 1080x1920 de um estado da legenda."""
    img = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    destaque = rgb(cor)
    cx = LARGURA // 2
    palavras = grupo.palavras
    if estilo == "impacto":
        f = fonte("anton", 90)
        pecas = [Peca(_texto(p, True), f, destaque if i == falada else BRANCO, 8) for i, p in enumerate(palavras)]
        desenhar_linhas(img, pecas, cx, y, LARGURA_UTIL)
    elif estilo == "caixa":
        f = fonte("montserrat", 68, 800)
        pecas = [
            Peca(_texto(p, False), f, PRETO if i == falada else BRANCO, 0 if i == falada else 3,
                 caixa=destaque if i == falada else None)
            for i, p in enumerate(palavras)
        ]
        desenhar_linhas(img, pecas, cx, y, LARGURA_UTIL - 40)
    elif estilo == "gigante":
        texto = _texto(palavras[falada], True)
        f = caber(texto, "anton", 200, LARGURA_UTIL - 20)
        desenhar_linhas(img, [Peca(texto, f, destaque, 0)], cx + 10, y + 10, LARGURA_UTIL)
        desenhar_linhas(img, [Peca(texto, f, BRANCO, 0)], cx, y, LARGURA_UTIL)
    elif estilo == "pulso":
        normal, grande = fonte("montserrat", 66, 800), fonte("montserrat", 82, 800)
        pecas = [
            Peca(_texto(p, False), grande if i == falada else normal, destaque if i == falada else BRANCO, 4)
            for i, p in enumerate(palavras)
        ]
        desenhar_linhas(img, pecas, cx, y, LARGURA_UTIL)
    elif estilo == "fita":
        _fita(img, palavras, falada, destaque, y)
    elif estilo == "papelaria":
        f = fonte("montserrat", 70, 800)
        pecas = [
            Peca(_texto(p, False), f, destaque if i == falada else BRANCO, 10, ESCURO)
            for i, p in enumerate(palavras[: falada + 1])
        ]
        # mede com a frase inteira pra não pular de linha enquanto escreve
        _alinhado_a_frase(img, pecas, palavras, f, y)
    elif estilo == "discreta":
        f = fonte("montserrat", 48, 600)
        pecas = [Peca(_texto(p, False), f, destaque if i == falada else BRANCO) for i, p in enumerate(palavras)]
        rascunho = Image.new("RGBA", img.size)
        x0, y0, x1, y1 = desenhar_linhas(rascunho, pecas, cx, y, LARGURA_UTIL - 60)
        ImageDraw.Draw(img).rounded_rectangle((x0 - 28, y0 - 14, x1 + 28, y1 + 14), 22, fill=(0, 0, 0, 150))
        img.alpha_composite(rascunho)
    else:
        raise ValueError(f"estilo desconhecido: {estilo}")
    return img


def _fita(img: Image.Image, palavras, falada, destaque, y) -> None:
    f = fonte("montserrat", 60, 800)
    pecas = [Peca(_texto(p, False), f, destaque if i == falada else BRANCO) for i, p in enumerate(palavras)]
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rascunho = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = desenhar_linhas(rascunho, pecas, 0, y, LARGURA_UTIL - 80, alinhar="esquerda", x_esquerda=180)
    ImageDraw.Draw(camada).rectangle((x0 - 40, y0 - 10, x1 + 40, y1 + 10), fill=(0, 0, 0, 235))
    camada.alpha_composite(rascunho)
    # inclina -4 graus (como no CSS: sobe pra direita); no Pillow o ângulo positivo é anti-horário
    girada = camada.rotate(4, resample=Image.BICUBIC, center=((x0 + x1) / 2, (y0 + y1) / 2))
    img.alpha_composite(girada)


def _alinhado_a_frase(img, pecas, palavras, f, y) -> None:
    completa = [Peca(_texto(p, False), f, BRANCO, 10) for p in palavras]
    rascunho = Image.new("RGBA", img.size)
    x0, _, _, _ = desenhar_linhas(rascunho, completa, LARGURA // 2, y, LARGURA_UTIL)
    desenhar_linhas(img, pecas, 0, y, LARGURA_UTIL, alinhar="esquerda", x_esquerda=x0)


def altura_estimada(estilo: str) -> int:
    return {"gigante": 240, "discreta": 160, "fita": 200}.get(estilo, 230)


def gerar_camada(
    palavras: list[Palavra],
    estilo: str,
    cor: str,
    pasta: str | Path,
    duracao: float,
    rostos: list[Rosto] | None = None,
    ocultar: list[tuple[float, float]] | None = None,
) -> Path:
    """Desenha todos os estados e escreve a lista do concat (uma faixa de vídeo só).

    `ocultar`: trechos sem legenda (animação na faixa da legenda, chamada final).
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    grupos = agrupar(palavras, estilo)
    lista = estados(grupos)
    vazio = pasta / "vazio.png"
    Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0)).save(vazio)
    ys: dict[int, int] = {}
    entradas: list[tuple[Path, float, float]] = []
    for n, e in enumerate(lista):
        inicio, fim = e.inicio, e.fim
        for a, b in ocultar or []:
            if a <= inicio and fim <= b:
                inicio = fim
            elif a <= inicio < b:
                inicio = b
            elif a < fim <= b:
                fim = a
        if fim - inicio < 0.02:
            continue
        if e.grupo not in ys:
            g = grupos[e.grupo]
            ys[e.grupo] = posicao_vertical(altura_estimada(estilo), rostos_entre(rostos or [], g.inicio, g.fim))
        arquivo = pasta / f"leg_{n:05d}.png"
        desenhar(estilo, grupos[e.grupo], e.falada, cor, ys[e.grupo]).save(arquivo, compress_level=1)
        entradas.append((arquivo, inicio, fim))
    return escrever_concat(entradas, duracao, pasta / "legenda.ffconcat", vazio)


def escrever_concat(entradas: list[tuple[Path, float, float]], duracao: float, destino: Path, vazio: Path) -> Path:
    """Lista do concat demuxer com imagens e durações; buracos viram PNG vazio."""
    linhas = ["ffconcat version 1.0"]
    agora = 0.0

    def item(arquivo: Path, dur: float) -> None:
        linhas.append(f"file '{arquivo.resolve()}'")
        linhas.append(f"duration {dur:.3f}")

    for arquivo, inicio, fim in sorted(entradas, key=lambda e: e[1]):
        inicio = max(inicio, agora)
        if inicio - agora > 0.001:
            item(vazio, inicio - agora)
        if fim - inicio > 0.001:
            item(arquivo, fim - inicio)
            agora = fim
    item(vazio, max(duracao - agora, 0.04))
    linhas.append(f"file '{vazio.resolve()}'")  # o último arquivo precisa repetir
    destino.write_text("\n".join(linhas) + "\n")
    return destino
