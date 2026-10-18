"""Ajudantes de desenho com o Pillow: medir texto, quebrar linhas, sombra, curvas."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def ease_out_cubico(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_in_cubico(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p ** 3


def medir(texto: str, f: ImageFont.FreeTypeFont, contorno: int = 0) -> tuple[int, int, int, int]:
    """Caixa (x0, y0, x1, y1) do texto desenhado em (0, 0)."""
    return f.getbbox(texto, stroke_width=contorno)


def largura(texto: str, f: ImageFont.FreeTypeFont, contorno: int = 0) -> int:
    x0, _, x1, _ = medir(texto, f, contorno)
    return x1 - x0


def altura_linha(f: ImageFont.FreeTypeFont, contorno: int = 0) -> int:
    subida, descida = f.getmetrics()
    return subida + descida + 2 * contorno


def quebrar(palavras: list[str], f: ImageFont.FreeTypeFont, maximo: int, contorno: int = 0) -> list[list[int]]:
    """Quebra em linhas que cabem em `maximo` px. Devolve índices por linha."""
    espaco = largura(" ", f) or f.size // 4
    linhas: list[list[int]] = [[]]
    atual = 0
    for i, p in enumerate(palavras):
        w = largura(p, f, contorno)
        if linhas[-1] and atual + espaco + w > maximo:
            linhas.append([])
            atual = 0
        atual += (espaco if linhas[-1] else 0) + w
        linhas[-1].append(i)
    return linhas


def caber(texto: str, nome_fonte: str, tamanho: int, maximo: int, peso: int = 800, contorno: int = 0, minimo: int = 40):
    """Reduz o tamanho da fonte até o texto caber em uma linha de `maximo` px."""
    from .fontes import fonte

    while tamanho > minimo:
        f = fonte(nome_fonte, tamanho, peso)
        if largura(texto, f, contorno) <= maximo:
            return f
        tamanho -= 4
    return fonte(nome_fonte, minimo, peso)


def retangulo_arredondado(img: Image.Image, caixa, raio: int, cor, sombra: bool = False) -> None:
    if sombra:
        camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
        x0, y0, x1, y1 = caixa
        ImageDraw.Draw(camada).rounded_rectangle((x0 + 4, y0 + 10, x1 + 4, y1 + 10), raio, fill=(0, 0, 0, 110))
        img.alpha_composite(camada.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(img).rounded_rectangle(caixa, raio, fill=cor)


def colar_centralizado(fundo: Image.Image, img: Image.Image, cx: float, cy: float) -> None:
    fundo.alpha_composite(img, (int(round(cx - img.width / 2)), int(round(cy - img.height / 2))))


def escalar(img: Image.Image, fator: float) -> Image.Image:
    if abs(fator - 1) < 1e-3:
        return img
    w, h = max(1, int(img.width * fator)), max(1, int(img.height * fator))
    return img.resize((w, h), Image.LANCZOS)


def com_alfa(img: Image.Image, alfa: float) -> Image.Image:
    if alfa >= 0.999:
        return img
    canal = img.getchannel("A").point(lambda v: int(v * max(alfa, 0.0)))
    saida = img.copy()
    saida.putalpha(canal)
    return saida


def recortar_conteudo(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Caixa do que não é transparente (pra conferir zona segura)."""
    return img.getchannel("A").getbbox()


@dataclass
class Peca:
    """Um pedaço de texto com estilo próprio, pra montar linhas mistas."""

    texto: str
    fonte: ImageFont.FreeTypeFont
    cor: tuple
    contorno: int = 0
    cor_contorno: tuple = (0, 0, 0, 255)
    caixa: tuple | None = None  # cor da caixa atrás da palavra


def desenhar_linhas(
    img: Image.Image, pecas: list[Peca], cx: int, cy: int, maximo: int,
    alinhar: str = "centro", x_esquerda: int = 140, entre_linhas: float = 1.05,
) -> tuple[int, int, int, int]:
    """Desenha peças quebrando linhas, centradas em (cx, cy). Devolve a caixa usada."""
    draw = ImageDraw.Draw(img)
    linhas: list[list[Peca]] = [[]]
    larguras = [0]
    for p in pecas:
        w = largura(p.texto, p.fonte, p.contorno)
        espaco = int(p.fonte.size * 0.28)
        if linhas[-1] and larguras[-1] + espaco + w > maximo:
            linhas.append([])
            larguras.append(0)
        larguras[-1] += (espaco if linhas[-1] else 0) + w
        linhas[-1].append(p)
    alturas = [int(max(altura_linha(p.fonte, p.contorno) for p in linha) * entre_linhas) for linha in linhas]
    y = cy - sum(alturas) // 2
    caixa_total = [10**6, y, -1, y + sum(alturas)]
    for linha, w_linha, h_linha in zip(linhas, larguras, alturas):
        x = cx - w_linha // 2 if alinhar == "centro" else x_esquerda
        caixa_total[0] = min(caixa_total[0], x)
        caixa_total[2] = max(caixa_total[2], x + w_linha)
        base = y + h_linha // 2
        for p in linha:
            w = largura(p.texto, p.fonte, p.contorno)
            x0, y0, x1, y1 = medir(p.texto, p.fonte, p.contorno)
            topo = base - (y0 + y1) // 2
            if p.caixa:
                folga = int(p.fonte.size * 0.18)
                draw.rounded_rectangle(
                    (x - folga, base - (y1 - y0) // 2 - folga, x + w + folga, base + (y1 - y0) // 2 + folga),
                    int(p.fonte.size * 0.2), fill=p.caixa,
                )
            draw.text((x - x0, topo), p.texto, font=p.fonte, fill=p.cor,
                      stroke_width=p.contorno, stroke_fill=p.cor_contorno)
            x += w + int(p.fonte.size * 0.28)
        y += h_linha
    return tuple(caixa_total)
