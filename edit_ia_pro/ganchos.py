"""Gancho escrito nos primeiros segundos, no alto da tela (y entre 250 e 600)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import ALTURA, FPS, LARGURA
from .corte import normalizar, separar_frases
from .cores import rgb
from .desenho import Peca, caber, desenhar_linhas, escalar, largura, quebrar, retangulo_arredondado
from .fontes import fonte
from .legendas import escrever_concat
from .transcricao import Palavra

ESTILOS = ("manchete", "tarjas", "balao", "marca-texto", "vidro")
NOMES_ESTILOS = {
    "manchete": "manchete", "tarjas": "tarjas", "balao": "balao", "balão": "balao",
    "marca-texto": "marca-texto", "marca texto": "marca-texto", "vidro": "vidro", "vidro escuro": "vidro",
}
TOPO, BASE = 250, 600
CENTRO_Y = (TOPO + BASE) // 2
LARGURA_UTIL = 720  # sobra espaço pra tarja/painel dentro da zona segura (x 140 a 940)
LARGURA_PAINEL = 660
BRANCO = (255, 255, 255, 255)
ESCURO = (20, 20, 24, 255)


def estilo_gancho(nome: str) -> str:
    chave = nome.strip().lower()
    if chave not in NOMES_ESTILOS:
        raise ValueError(f"estilo de gancho desconhecido: {nome}")
    return NOMES_ESTILOS[chave]


def dividir_linhas(texto: str, nome_fonte: str, tamanho: int, peso: int = 800, contorno: int = 0,
                   maximo: int = LARGURA_UTIL) -> tuple[list[str], int]:
    """No máximo 2 linhas; reduz a fonte até caber."""
    palavras = texto.split()
    while tamanho >= 40:
        f = fonte(nome_fonte, tamanho, peso)
        linhas = quebrar(palavras, f, maximo, contorno)
        cabe = all(largura(p, f, contorno) <= maximo for p in palavras)
        if len(linhas) <= 2 and cabe:
            return [" ".join(palavras[i] for i in l) for l in linhas], tamanho
        tamanho -= 6
    meio = (len(palavras) + 1) // 2
    return [" ".join(palavras[:meio]), " ".join(palavras[meio:])], 40


def desenhar(estilo: str, texto: str, cor: str) -> Image.Image:
    """PNG 1080x1920 com o gancho parado (quadro final da entrada)."""
    img = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    destaque = rgb(cor)
    cx = LARGURA // 2
    if estilo == "manchete":
        linhas, tam = dividir_linhas(texto.upper(), "anton", 110, contorno=9)
        f = fonte("anton", tam)
        alt = int(tam * 1.25)
        for i, linha in enumerate(linhas):
            y = CENTRO_Y - alt * (len(linhas) - 1) // 2 + i * alt
            desenhar_linhas(img, [Peca(linha, f, destaque if i == 1 else BRANCO, 9)], cx, y, LARGURA_UTIL + 40)
    elif estilo in ("tarjas", "marca-texto"):
        linhas, tam = dividir_linhas(texto, "montserrat", 76, 900)
        f = fonte("montserrat", tam, 900)
        alt = int(tam * 1.55)
        for i, linha in enumerate(linhas):
            y = CENTRO_Y - alt * (len(linhas) - 1) // 2 + i * alt
            w = largura(linha, f)
            camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(camada)
            if estilo == "tarjas":
                fundo = BRANCO if i % 2 == 0 else destaque
                d.rectangle((cx - w // 2 - 30, y - tam * 0.68, cx + w // 2 + 30, y + tam * 0.68), fill=fundo)
                desenhar_linhas(camada, [Peca(linha, f, ESCURO)], cx, y, LARGURA_UTIL + 60)
                camada = camada.rotate(2 if i % 2 == 0 else -2, resample=Image.BICUBIC, center=(cx, y))
            else:
                cor_marca = destaque[:3] + (215,)
                d.rounded_rectangle((cx - w // 2 - 18, y - tam * 0.18, cx + w // 2 + 18, y + tam * 0.58), 10, fill=cor_marca)
                desenhar_linhas(camada, [Peca(linha, f, ESCURO, 0)], cx, y, LARGURA_UTIL + 60)
            img.alpha_composite(camada)
    elif estilo == "balao":
        linhas, tam = dividir_linhas(texto, "montserrat", 62, 700, maximo=LARGURA_PAINEL)
        f = fonte("montserrat", tam, 700)
        rascunho = Image.new("RGBA", img.size)
        x0, y0, x1, y1 = desenhar_linhas(rascunho, [Peca(l, f, ESCURO) for l in linhas], cx, CENTRO_Y, LARGURA_PAINEL + 20)
        caixa = (x0 - 44, y0 - 30, x1 + 44, y1 + 30)
        retangulo_arredondado(img, caixa, 40, BRANCO, sombra=True)
        ImageDraw.Draw(img).polygon(
            [(caixa[0] + 70, caixa[3] - 2), (caixa[0] + 130, caixa[3] - 2), (caixa[0] + 60, caixa[3] + 46)], fill=BRANCO,
        )
        img.alpha_composite(rascunho)
    elif estilo == "vidro":
        linhas, tam = dividir_linhas(texto, "montserrat", 66, 800, maximo=LARGURA_PAINEL)
        f = fonte("montserrat", tam, 800)
        rascunho = Image.new("RGBA", img.size)
        x0, y0, x1, y1 = desenhar_linhas(rascunho, [Peca(l, f, BRANCO) for l in linhas], cx, CENTRO_Y + 10, LARGURA_PAINEL + 20)
        caixa = (x0 - 48, y0 - 50, x1 + 48, y1 + 34)
        retangulo_arredondado(img, caixa, 30, (12, 12, 16, 175), sombra=True)
        ImageDraw.Draw(img).rounded_rectangle((caixa[0] + 48, caixa[1] + 22, caixa[0] + 148, caixa[1] + 32), 5, fill=destaque)
        img.alpha_composite(rascunho)
    else:
        raise ValueError(f"estilo desconhecido: {estilo}")
    return img


def gerar_camada(texto: str, estilo: str, cor: str, pasta: str | Path, duracao_video: float, duracao: float = 2.8) -> tuple[Path, float]:
    """Gancho com entrada de 4 quadros crescendo de 90% a 100%. Devolve (lista, fim)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    parado = desenhar(estilo, texto, cor)
    conteudo = parado.getchannel("A").getbbox() or (0, 0, LARGURA, ALTURA)
    cx, cy = (conteudo[0] + conteudo[2]) / 2, (conteudo[1] + conteudo[3]) / 2
    recorte = parado.crop(conteudo)
    entradas = []
    quadro = 1 / FPS
    for i, escala in enumerate((0.90, 0.94, 0.97, 1.0)):
        img = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
        pequeno = escalar(recorte, escala)
        img.alpha_composite(pequeno, (int(cx - pequeno.width / 2), int(cy - pequeno.height / 2)))
        arquivo = pasta / f"gancho_{i}.png"
        img.save(arquivo, compress_level=1)
        fim = (i + 1) * quadro if i < 3 else duracao
        entradas.append((arquivo, i * quadro, fim))
    vazio = pasta / "vazio.png"
    Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0)).save(vazio)
    return escrever_concat(entradas, duracao_video, pasta / "gancho.ffconcat", vazio), duracao


def sugerir_ganchos(palavras: list[Palavra], quantos: int = 2) -> list[str]:
    """Opções tiradas da própria fala: até 2 linhas, 6 a 8 palavras, sem promessa de ganho."""
    from .meta import conferir_texto

    frases = separar_frases(palavras)
    candidatas = []
    for frase in frases:
        textos = [palavras[i].texto.strip() for i in frase]
        if len(textos) < 4:
            continue
        corte = textos[:8]
        texto = " ".join(corte).rstrip(",;:")
        if conferir_texto(texto):
            continue
        n = normalizar(texto)
        nota = 0
        nota += 3 if texto.endswith("?") else 0
        nota += 2 if any(w in n.split() for w in ("voce", "seu", "sua", "nunca", "pare", "erro", "segredo", "jeito", "ninguem")) else 0
        nota += 1 if 6 <= len(corte) <= 8 else 0
        nota -= frases.index(frase) * 0.1  # começo da fala pesa mais
        candidatas.append((nota, texto))
    candidatas.sort(key=lambda c: -c[0])
    vistas, saida = set(), []
    for _, texto in candidatas:
        if texto not in vistas:
            vistas.add(texto)
            saida.append(texto)
        if len(saida) == quantos:
            break
    return saida
