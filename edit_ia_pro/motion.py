"""Passo 5b · Animações 2D nos momentos fortes da fala (motion).

1. `sugerir_momentos` lê a transcrição do corte e marca onde a fala pede animação.
2. `renderizar` desenha cada animação como sequência de PNGs (só a caixa do
   elemento) e junta num .mov com transparência pra sobrepor no vídeo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import FPS, ZONA_SEGURA
from .cores import rgb
from .corte import normalizar
from .desenho import (
    Peca, caber, com_alfa, desenhar_linhas, ease_out_cubico, escalar, largura, retangulo_arredondado,
)
from .ferramentas import ffmpeg
from .fontes import fonte
from .rosto import Rosto, posicao_vertical, rostos_entre
from .transcricao import Palavra

ENTRADA = 0.3
SAIDA = 0.2
ANTECIPA = 0.1  # a entrada começa até 0,1 s antes da palavra que chama

DENSIDADE = {"nenhuma": None, "poucas": 10.0, "medias": 5.0, "médias": 5.0, "muitas": 3.0}
PRIORIDADE = ["comentario", "lista", "passo", "numero", "carimbo", "notificacao", "impacto", "destaque", "barra"]
NOMES = {
    "impacto": "palavra de impacto", "lista": "lista com check", "passo": "passo a passo",
    "numero": "número contando", "notificacao": "notificação", "carimbo": "carimbo",
    "destaque": "destaque desenhado", "comentario": "comentário sendo digitado", "barra": "barra enchendo",
}

NUMEROS_ESCRITOS = {
    "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
    "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
    "quarenta": 40, "cinquenta": 50, "sessenta": 60, "cem": 100, "cento": 100, "mil": 1000,
}
ORDINAIS = {"primeiro": 1, "primeira": 1, "segundo": 2, "segunda": 2, "terceiro": 3, "terceira": 3,
            "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5}
IMPACTO = ["acabou", "sem editor", "de graca", "simples assim", "nunca mais", "chega", "facil assim",
           "sem complicacao", "so isso", "e so isso", "olha o resultado", "muda tudo"]
CARIMBO = {"pronto": "PRONTO", "aprovado": "APROVADO", "aprovada": "APROVADO", "feito": "FEITO",
           "decidido": "DECIDIDO", "confirmado": "CONFIRMADO", "resolvido": "RESOLVIDO"}
NOTIFICACAO = {"chegou": "Chegou!", "mensagem": "Nova mensagem", "notificacao": "Nova notificação",
               "venda": "Nova venda", "vendas": "Nova venda", "pedido": "Novo pedido", "aviso": "Aviso"}
DESTAQUE = ["olha isso", "olha aqui", "olha so", "esse aqui", "essa aqui", "repara aqui"]
BARRA = ["o dobro", "metade", "o triplo", "mais rapido", "progresso", "cada vez mais"]
DINHEIRO = {"reais", "real", "r", "dinheiro", "lucro", "faturamento", "renda"}


@dataclass
class Momento:
    tipo: str
    inicio: float          # tempo no vídeo cortado em que a entrada começa
    fim: float             # fim da saída
    dados: dict = field(default_factory=dict)

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio

    def descricao(self) -> str:
        s = int(self.inicio)
        extra = ""
        if self.tipo == "lista":
            extra = f" com {len(self.dados['itens'])} itens"
        elif self.tipo == "numero":
            extra = f" {self.dados['texto']} contando"
        elif self.tipo in ("carimbo", "impacto", "comentario"):
            extra = f" {self.dados['texto']}"
        return f"{s // 60}:{s % 60:02d} {NOMES[self.tipo]}{extra}"


def _fim_da_frase(palavras: list[Palavra], i: int, limite: int = 8) -> int:
    j = i
    while j < len(palavras) - 1 and j - i < limite and palavras[j].texto.rstrip()[-1:] not in ".,!?;:":
        j += 1
    return j


def _limpo(texto: str) -> str:
    return texto.strip().strip(".,!?;:").strip()


def _duracao(palavras, i, j, minimo=1.2, maximo=2.6) -> tuple[float, float]:
    inicio = max(palavras[i].inicio - ANTECIPA, 0.0)
    fala = palavras[j].fim + 0.5 - inicio
    return inicio, inicio + min(max(fala, minimo), maximo) + SAIDA


def _valor_numero(n: str) -> int | float | None:
    if re.fullmatch(r"\d+([.,]\d+)?%?", n):
        return float(n.rstrip("%").replace(",", ".")) if re.search(r"[.,]", n) else int(n.rstrip("%"))
    return NUMEROS_ESCRITOS.get(n)


def _rotulo_do_numero(palavras: list[Palavra], norm: list[str], i: int) -> str:
    """A coisa contada: "5 minutos" -> MINUTOS, "3 vídeos por dia" -> VÍDEOS POR DIA."""
    if i + 1 >= len(palavras) or palavras[i].texto.rstrip()[-1:] in ".,!?;:":
        return ""
    partes = [_limpo(palavras[i + 1].texto)]
    fecha_frase = palavras[i + 1].texto.rstrip()[-1:] in ".,!?;:"
    if not fecha_frase and i + 3 < len(norm) and norm[i + 2] in ("por", "de", "ao", "a", "no", "na"):
        partes += [_limpo(palavras[i + 2].texto), _limpo(palavras[i + 3].texto)]
    return " ".join(partes)


def detectar_candidatos(palavras: list[Palavra]) -> list[Momento]:
    """Todos os momentos possíveis, antes de aplicar ritmo e regras."""
    norm = [normalizar(p.texto) for p in palavras]
    texto_de = lambda i, j: " ".join(norm[i:j + 1])  # noqa: E731
    momentos: list[Momento] = []
    usados: set[int] = set()

    # Enumeração: "primeiro ... segundo ..." ou "passo 1 ... passo 2"
    ordinais = [i for i, n in enumerate(norm) if n in ORDINAIS
                and not (i > 0 and _valor_numero(norm[i - 1]) is not None)]
    if ordinais and ORDINAIS[norm[ordinais[0]]] == 1:
        seq = [ordinais[0]]
        for i in ordinais[1:]:
            if ORDINAIS[norm[i]] == ORDINAIS[norm[seq[-1]]] + 1 and palavras[i].inicio - palavras[seq[-1]].inicio < 20:
                seq.append(i)
        if len(seq) >= 2:
            itens = []
            for i in seq:
                j = _fim_da_frase(palavras, i + 1, 5) if i + 1 < len(palavras) else i
                corpo = [_limpo(palavras[k].texto) for k in range(i + 1, j + 1) if norm[k] not in ("e", "eh", "passo")]
                itens.append({"texto": " ".join(corpo[:4]).capitalize() or f"Item {ORDINAIS[norm[i]]}",
                              "t": palavras[i].inicio})
                usados.update(range(i, j + 1))
            inicio = max(palavras[seq[0]].inicio - ANTECIPA, 0)
            fim_item = palavras[min(_fim_da_frase(palavras, seq[-1] + 1), len(palavras) - 1)].fim
            fim = max(fim_item + 0.4, palavras[seq[-1]].fim + 1.2)
            momentos.append(Momento("lista", inicio, fim + SAIDA, {"itens": itens[:4]}))
    passos = [i for i in range(len(norm) - 1) if norm[i] in ("passo", "etapa") and _valor_numero(norm[i + 1]) is not None
              or norm[i] in ("passo", "etapa") and norm[i + 1] in ("um", "1")]
    if len(passos) >= 2:
        etapas = []
        for i in passos:
            j = _fim_da_frase(palavras, i + 2, 4) if i + 2 < len(palavras) else i + 1
            nome = " ".join(_limpo(palavras[k].texto) for k in range(i + 2, j + 1))
            n = 1 if norm[i + 1] == "um" else _valor_numero(norm[i + 1])
            etapas.append({"numero": int(n), "nome": nome.upper()[:22], "t": palavras[i].inicio})
            usados.update(range(i, j + 1))
        inicio = max(palavras[passos[0]].inicio - ANTECIPA, 0)
        momentos.append(Momento("passo", inicio, palavras[passos[-1]].fim + 2.2 + SAIDA, {"etapas": etapas}))

    for i, n in enumerate(norm):
        if i in usados:
            continue
        # Chamada final: "comenta X"
        if n in ("comenta", "comente", "comentem") and i + 1 < len(norm):
            k = i + 1
            while k < len(norm) - 1 and norm[k] in ("a", "aqui", "palavra", "ai", "o", "embaixo"):
                k += 1
            palavra = _limpo(palavras[k].texto).upper()
            if palavra:
                inicio = max(palavras[i].inicio - ANTECIPA, 0)
                digitar = 0.05 * len(palavra)
                momentos.append(Momento("comentario", inicio, inicio + ENTRADA + digitar + 1.4 + SAIDA, {"texto": palavra}))
                usados.update({i, k})
            continue
        valor = _valor_numero(n)
        if valor is not None and n not in ("um", "uma"):
            antes = norm[i - 1] if i > 0 else ""
            depois = norm[i + 1] if i + 1 < len(norm) else ""
            if antes in DINHEIRO or depois in DINHEIRO or palavras[i].texto.startswith("R$") or n == "mil" and antes:
                continue
            if depois in ("coisas", "dicas", "erros", "passos", "motivos", "formas", "jeitos", "regras", "segredos") and any(m.tipo == "lista" for m in momentos):
                continue
            j = _fim_da_frase(palavras, i, 3)
            rotulo = _rotulo_do_numero(palavras, norm, i)
            texto = _limpo(palavras[i].texto) if re.search(r"\d", palavras[i].texto) else str(valor)
            ini, fim = _duracao(palavras, i, j, minimo=1.6)
            momentos.append(Momento("numero", ini, fim, {"texto": texto, "rotulo": rotulo.upper()}))
            continue
        if n in CARIMBO:
            ini, fim = _duracao(palavras, i, i, minimo=1.2, maximo=1.6)
            momentos.append(Momento("carimbo", ini, fim, {"texto": CARIMBO[n]}))
            continue
        if n in NOTIFICACAO:
            j = _fim_da_frase(palavras, i, 6)
            k0 = max(i - 2, 0)
            linha = " ".join(_limpo(palavras[k].texto) for k in range(k0, j + 1) if _valor_numero(norm[k]) is None)
            ini, fim = _duracao(palavras, i, j, minimo=2.0, maximo=2.2)
            momentos.append(Momento("notificacao", ini, fim, {"titulo": NOTIFICACAO[n], "texto": linha.capitalize()}))
            continue
        for lista, tipo in ((IMPACTO, "impacto"), (DESTAQUE, "destaque"), (BARRA, "barra")):
            for frase in lista:
                tamanho = len(frase.split())
                if texto_de(i, i + tamanho - 1) == frase:
                    j = i + tamanho - 1
                    texto = " ".join(_limpo(palavras[k].texto) for k in range(i, j + 1)).upper()
                    ini, fim = _duracao(palavras, i, j)
                    momentos.append(Momento(tipo, ini, fim, {"texto": texto}))
                    break
            else:
                continue
            break
    # Frase curta forte com exclamação ("Acabou!", "Sem editor!")
    inicio_frase = 0
    for i, p in enumerate(palavras):
        if p.texto.rstrip()[-1:] in ".!?":
            if p.texto.rstrip().endswith("!") and 1 <= i - inicio_frase + 1 <= 3 \
                    and not any(m.inicio <= p.inicio <= m.fim for m in momentos):
                texto = " ".join(_limpo(palavras[k].texto) for k in range(inicio_frase, i + 1)).upper()
                ini, fim = _duracao(palavras, inicio_frase, i)
                momentos.append(Momento("impacto", ini, fim, {"texto": texto}))
            inicio_frase = i + 1
    return sorted(momentos, key=lambda m: m.inicio)


def escolher(
    candidatos: list[Momento], ritmo: str = "medias", fim_gancho: float = 0.5, duracao: float | None = None,
    bloqueios: list[tuple[float, float]] | None = None,
) -> list[Momento]:
    """Aplica as regras: uma por vez, nada durante o gancho, no ritmo escolhido.

    `bloqueios`: trechos com outra coisa na tela (tela dividida), sem animação.
    """
    intervalo = DENSIDADE.get(ritmo, 5.0)
    if intervalo is None:
        return []
    ordem = sorted(candidatos, key=lambda m: (PRIORIDADE.index(m.tipo), m.inicio))
    escolhidos: list[Momento] = []
    for m in ordem:
        if m.inicio < fim_gancho:
            continue
        if duracao is not None and m.inicio > duracao - 0.6:
            continue
        if duracao is not None and m.fim > duracao:
            m = Momento(m.tipo, m.inicio, duracao, m.dados)
        livre = all(m.fim + 0.2 <= o.inicio or o.fim + 0.2 <= m.inicio for o in escolhidos) and \
            all(m.fim <= a or m.inicio >= b for a, b in bloqueios or [])
        # comentário (chamada final) não depende do ritmo
        espacado = m.tipo == "comentario" or all(abs(m.inicio - o.inicio) >= intervalo for o in escolhidos if o.tipo != "comentario")
        if livre and espacado:
            escolhidos.append(m)
    return sorted(escolhidos, key=lambda m: m.inicio)


def sugerir_momentos(
    palavras: list[Palavra], ritmo: str = "medias", fim_gancho: float = 0.5, duracao: float | None = None,
    bloqueios: list[tuple[float, float]] | None = None,
) -> list[Momento]:
    return escolher(detectar_candidatos(palavras), ritmo, fim_gancho, duracao, bloqueios)


def sons_do_momento(m: Momento) -> list[tuple[float, str, bool]]:
    """(tempo do pico, som, forte) — o pico cai no quadro do movimento."""
    pico = m.inicio + ENTRADA * 0.6
    if m.tipo == "impacto":
        return [(m.inicio + 0.2, "impacto", True)]
    if m.tipo == "lista":
        return [(max(item["t"], m.inicio) + 0.15, "pop", False) for item in m.dados["itens"]]
    if m.tipo == "passo":
        return [(max(e["t"], m.inicio) + 0.1, "swish", False) for e in m.dados["etapas"]]
    if m.tipo == "numero":
        return [(m.inicio + ENTRADA + 0.8, "pop", False)]
    if m.tipo == "notificacao":
        return [(m.inicio + 0.35, "ding", False)]
    if m.tipo == "carimbo":
        return [(m.inicio + 0.14, "impacto_seco", True)]
    if m.tipo == "destaque":
        return [(m.inicio + 0.1, "swish", False)]
    if m.tipo == "comentario":
        digitar = 0.05 * len(m.dados["texto"])
        return [(m.inicio + ENTRADA + 0.05, "teclado", False), (m.inicio + ENTRADA + digitar + 0.25, "clique", False)]
    if m.tipo == "barra":
        return [(pico, "whoosh_subindo", False)]
    return []


# ---------------------------------------------------------------- desenho

BRANCO = (255, 255, 255, 255)
ESCURO = (20, 20, 24, 255)
CARTAO_ESCURO = (22, 22, 28, 235)
TAMANHOS = {
    "impacto": (800, 340), "lista": (760, None), "passo": (800, 170), "numero": (800, 360),
    "notificacao": (800, 230), "carimbo": (720, 380), "destaque": (380, 380), "comentario": (800, 230),
    "barra": (800, 210),
}


def tamanho_caixa(m: Momento) -> tuple[int, int]:
    w, h = TAMANHOS[m.tipo]
    if m.tipo == "lista":
        h = 70 + 112 * len(m.dados["itens"])
    return w, h


def _envelope(m: Momento, t: float) -> tuple[float, float]:
    """(progresso da entrada 0..1 com ease-out, alfa da saída)."""
    entrada = ease_out_cubico(t / ENTRADA)
    resto = m.duracao - t
    alfa = min(1.0, max(resto / SAIDA, 0.0))
    return entrada, alfa


def quadro(m: Momento, t: float, cor: str) -> Image.Image:
    """Um quadro da animação, do tamanho da caixa do elemento, em t (s) desde o início."""
    w, h = tamanho_caixa(m)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    destaque = rgb(cor)
    entrada, alfa = _envelope(m, t)
    desenhar = globals()[f"_q_{m.tipo}"]
    desenhar(img, m, t, entrada, destaque)
    if m.tipo != "notificacao":
        img = com_alfa(img, alfa)
    return img


def _escala_impacto(t: float) -> float:
    if t < 0.2:
        return 0.6 + (1.08 - 0.6) * ease_out_cubico(t / 0.2)
    if t < 0.3:
        return 1.08 - 0.08 * ease_out_cubico((t - 0.2) / 0.1)
    return 1.0


def _q_impacto(img, m, t, entrada, destaque):
    texto = m.dados["texto"]
    f = caber(texto, "anton", 190, img.width - 60)
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    desenhar_linhas(camada, [Peca(texto, f, destaque, 8)], img.width // 2 + 8, img.height // 2 + 8, img.width)
    desenhar_linhas(camada, [Peca(texto, f, BRANCO, 8)], img.width // 2, img.height // 2, img.width)
    escala = _escala_impacto(t)
    tremor = 0
    if 0.3 <= t < 0.3 + 3 / FPS:
        tremor = (3, -2, 2)[int((t - 0.3) * FPS) % 3]
    peca = escalar(camada, escala)
    img.alpha_composite(_recorte_central(peca, img.size), (tremor, 0))


def _recorte_central(peca: Image.Image, tamanho) -> Image.Image:
    w, h = tamanho
    saida = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    saida.alpha_composite(peca, ((w - peca.width) // 2, (h - peca.height) // 2)) if peca.width <= w else \
        saida.alpha_composite(peca.crop(((peca.width - w) // 2, (peca.height - h) // 2, (peca.width + w) // 2, (peca.height + h) // 2)))
    return saida


def _q_lista(img, m, t, entrada, destaque):
    if entrada <= 0:
        return
    w, h = img.size
    fundo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    retangulo_arredondado(fundo, (10, 10, w - 10, h - 20), 28, CARTAO_ESCURO, sombra=True)
    img.alpha_composite(com_alfa(fundo, entrada))
    f = fonte("montserrat", 50, 800)
    for n, item in enumerate(m.dados["itens"]):
        t_item = max(item["t"] - m.inicio, 0) if n else 0.0
        local = t - t_item
        if local < 0:
            continue
        p = ease_out_cubico(local / 0.2)
        cy = 45 + 112 * n + 56
        linha = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(linha)
        circulo = (40, cy - 32, 104, cy + 32)
        arco = 360 * min(max((local - 0.2) / 0.2, 0), 1)
        d.ellipse(circulo, outline=(255, 255, 255, 70), width=6)
        if arco > 0:
            d.arc(circulo, -90, -90 + arco, fill=destaque, width=7)
        if local >= 0.4:
            d.line([(56, cy + 2), (68, cy + 15), (90, cy - 12)], fill=destaque, width=8, joint="curve")
        texto = item["texto"]
        fi = caber(texto, "montserrat", 50, w - 190, 800) if largura(texto, f) > w - 190 else f
        d.text((132, cy), texto, font=fi, fill=BRANCO, anchor="lm")
        deslocada = Image.new("RGBA", img.size, (0, 0, 0, 0))
        deslocada.alpha_composite(com_alfa(linha, p), (int(-40 * (1 - p)), 0)) if p < 1 else deslocada.alpha_composite(linha)
        img.alpha_composite(deslocada)


def _q_passo(img, m, t, entrada, destaque):
    etapas = m.dados["etapas"]
    atual = 0
    for n, e in enumerate(etapas):
        if t >= max(e["t"] - m.inicio, 0) - 0.05:
            atual = n
    t_etapa = max(etapas[atual]["t"] - m.inicio, 0) if atual else 0
    p = ease_out_cubico((t - t_etapa) / 0.25)
    e = etapas[atual]
    texto = f"PASSO {e['numero']}" + (f" · {e['nome']}" if e["nome"] else "")
    f = caber(texto, "montserrat", 54, img.width - 120, 900)
    w = largura(texto, f) + 90
    pilula = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x0 = (img.width - w) // 2
    retangulo_arredondado(pilula, (x0, 30, x0 + w, 130), 50, destaque, sombra=True)
    ImageDraw.Draw(pilula).text((img.width // 2, 80), texto, font=f, fill=ESCURO, anchor="mm")
    img.alpha_composite(com_alfa(pilula, p), (0, int(-60 * (1 - p))))


def formatar_contagem(texto: str, progresso: float) -> str:
    """Conta de 0 até o valor mantendo o formato ("05" continua com 2 dígitos, "50%")."""
    sufixo = "%" if texto.endswith("%") else ""
    corpo = texto.rstrip("%")
    if re.fullmatch(r"\d+", corpo):
        valor = round(int(corpo) * progresso)
        return f"{valor:0{len(corpo)}d}{sufixo}"
    if re.fullmatch(r"\d+[.,]\d+", corpo):
        sep = "," if "," in corpo else "."
        casas = len(re.split(r"[.,]", corpo)[1])
        valor = float(corpo.replace(",", ".")) * progresso
        return f"{valor:.{casas}f}".replace(".", sep) + sufixo
    return texto


def _q_numero(img, m, t, entrada, destaque):
    p = ease_out_cubico((t - ENTRADA * 0.5) / 0.8)
    texto = formatar_contagem(m.dados["texto"], p)
    final = m.dados["texto"]
    f = caber(final, "anton", 210, img.width - 80)
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    desenhar_linhas(camada, [Peca(texto, f, destaque, 8)], img.width // 2, 140, img.width)
    if m.dados.get("rotulo"):
        fr = caber(m.dados["rotulo"], "montserrat", 56, img.width - 60, 800)
        desenhar_linhas(camada, [Peca(m.dados["rotulo"], fr, BRANCO, 5)], img.width // 2, 300, img.width)
    img.alpha_composite(_recorte_central(escalar(camada, 0.8 + 0.2 * entrada), img.size))
    if entrada < 1:
        img.putalpha(img.getchannel("A").point(lambda v: int(v * entrada)))


def _q_notificacao(img, m, t, entrada, destaque):
    """Desce do topo em 0,35 s, fica e sobe na saída. A caixa vai do topo da tela até a posição final."""
    w, h = img.size
    alto = 200
    descida = ease_out_cubico(t / 0.35)
    subida = ease_out_cubico((t - (m.duracao - 0.3)) / 0.3) if t > m.duracao - 0.3 else 0
    final = 250  # topo da zona segura do Reels
    y = int(-alto + (final + alto) * (descida - subida))
    cartao = Image.new("RGBA", (w, alto + 30), (0, 0, 0, 0))
    retangulo_arredondado(cartao, (10, 5, w - 10, alto), 32, (246, 246, 248, 245), sombra=True)
    d = ImageDraw.Draw(cartao)
    d.ellipse((40, 50, 140, 150), fill=destaque)
    d.text((90, 100), "!", font=fonte("anton", 64), fill=ESCURO, anchor="mm")
    ft = fonte("montserrat", 46, 800)
    fl = fonte("montserrat", 38, 500)
    d.text((170, 72), m.dados["titulo"], font=ft, fill=ESCURO, anchor="lm")
    linha = m.dados.get("texto", "")
    while linha and largura(linha, fl) > w - 210:
        linha = linha[:-2].rstrip() + "…" if not linha.endswith("…") else linha[:-2] + "…"
    d.text((170, 130), linha, font=fl, fill=(60, 60, 68, 255), anchor="lm")
    img.alpha_composite(cartao, (0, y)) if y > -cartao.height else None


def _q_carimbo(img, m, t, entrada, destaque):
    if t < 0.14:
        escala = 1.6 - (1.6 - 1.05) * ease_out_cubico(t / 0.14)
    elif t < 0.18:
        escala = 1.05 - 0.05 * ((t - 0.14) / 0.04)
    else:
        escala = 1.0
    texto = m.dados["texto"]
    cor = destaque if m.dados.get("cor") != "vermelho" else (230, 40, 40, 255)
    f = caber(texto, "anton", 120, 480)
    tw = largura(texto, f)
    selo = Image.new("RGBA", (tw + 120, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(selo)
    d.rounded_rectangle((8, 8, selo.width - 8, selo.height - 8), 18, outline=cor, width=14)
    d.text((selo.width // 2, selo.height // 2), texto, font=f, fill=cor, anchor="mm")
    selo = selo.rotate(8, resample=Image.BICUBIC, expand=True)  # -8 graus como no CSS
    selo = escalar(selo, escala)
    if t < 0.06:
        selo = com_alfa(selo, t / 0.06)
    img.alpha_composite(_recorte_central(selo, img.size))


def _q_destaque(img, m, t, entrada, destaque):
    p = min(max(t / 0.4, 0), 1)
    if p <= 0:
        return
    w, h = img.size
    d = ImageDraw.Draw(img)
    caixa = (20, 40, w - 20, h - 40)
    inicio = -110
    d.arc(caixa, inicio, inicio + 380 * ease_out_cubico(p), fill=destaque, width=10)


def _q_comentario(img, m, t, entrada, destaque):
    w, h = img.size
    p = entrada
    cartao = Image.new("RGBA", img.size, (0, 0, 0, 0))
    retangulo_arredondado(cartao, (10, 20, w - 10, h - 30), 30, (250, 250, 252, 245), sombra=True)
    d = ImageDraw.Draw(cartao)
    d.ellipse((40, 60, 130, 150), fill=(205, 208, 216, 255))
    d.ellipse((70, 76, 100, 106), fill=(240, 241, 245, 255))
    d.rounded_rectangle((60, 112, 110, 150), 18, fill=(240, 241, 245, 255))
    d.rounded_rectangle((155, 62, w - 150, 148), 40, outline=(210, 212, 220, 255), width=3, fill=BRANCO)
    texto = m.dados["texto"]
    letras = int(max(t - ENTRADA, 0) / 0.05)
    digitado = texto[: min(letras, len(texto))]
    f = caber(texto, "montserrat", 46, w - 380, 800)
    d.text((185, 105), digitado, font=f, fill=ESCURO, anchor="lm")
    if letras < len(texto) and int(t * 4) % 2 == 0:
        x = 185 + largura(digitado, f) + 4 if digitado else 185
        d.line([(x, 80), (x, 130)], fill=ESCURO, width=3)
    pronto = letras >= len(texto)
    piscando = pronto and int((t - ENTRADA - 0.05 * len(texto)) / 0.15) % 2 == 0
    cor_botao = destaque if not pronto or piscando else (255, 255, 255, 255)
    d.ellipse((w - 130, 62, w - 44, 148), fill=cor_botao, outline=destaque, width=4)
    d.polygon([(w - 106, 82), (w - 62, 105), (w - 106, 128), (w - 98, 105)], fill=ESCURO)
    img.alpha_composite(com_alfa(cartao, p), (0, int(30 * (1 - p))))


def _q_barra(img, m, t, entrada, destaque):
    w, h = img.size
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    rotulo = m.dados.get("texto", "")
    f = caber(rotulo, "montserrat", 52, w - 40, 800)
    d.text((w // 2, 50), rotulo, font=f, fill=BRANCO, anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0, 255))
    d.rounded_rectangle((20, 110, w - 20, 170), 30, fill=(255, 255, 255, 90))
    p = ease_out_cubico((t - 0.1) / 0.6)
    if p > 0:
        d.rounded_rectangle((20, 110, 20 + max(60, (w - 40) * p), 170), 30, fill=destaque)
    img.alpha_composite(com_alfa(camada, entrada))


# ---------------------------------------------------------------- posição e render

def posicionar(m: Momento, rostos: list[Rosto], alvo: tuple[int, int] | None = None) -> tuple[int, int]:
    """(x, y) do canto da caixa: centro da parte de cima, dentro da zona segura e fora do rosto."""
    w, h = tamanho_caixa(m)
    x0, y0, x1, y1 = ZONA_SEGURA
    if m.tipo == "destaque":
        cx, cy = alvo or (540, 640)
        x = min(max(cx - w // 2, x0 - 40), x1 + 40 - w)
        y = min(max(cy - h // 2, y0), y1 - h)
        return x, y
    if m.tipo == "notificacao":
        return (1080 - w) // 2, 0  # a caixa vai do topo até a posição final (y = 250)
    cy = posicao_vertical(h, rostos_entre(rostos, m.inicio, m.fim), preferido=y0 + 40 + h // 2)
    return (1080 - w) // 2, cy - h // 2


def caixa_na_tela(m: Momento, pos: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = tamanho_caixa(m)
    if m.tipo == "notificacao":
        return pos[0], 250, pos[0] + w, 250 + 200
    return pos[0], pos[1], pos[0] + w, pos[1] + h


def tamanho_render(m: Momento) -> tuple[int, int]:
    w, h = tamanho_caixa(m)
    return (w, 250 + h) if m.tipo == "notificacao" else (w, h)


def renderizar(m: Momento, cor: str, pasta: str | Path) -> Path:
    """Sequência de PNGs a 30 fps -> .mov com transparência (qtrle)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    total = max(1, int(math.ceil(m.duracao * FPS)))
    tamanho = tamanho_render(m)
    for n in range(total):
        t = n / FPS
        img = quadro(m, t, cor) if m.tipo != "notificacao" else _quadro_notificacao(m, t, cor, tamanho)
        img.save(pasta / f"anim_{n:04d}.png", compress_level=1)
    saida = pasta / "anim.mov"
    ffmpeg("-framerate", str(FPS), "-i", str(pasta / "anim_%04d.png"), "-c:v", "qtrle", "-pix_fmt", "argb", str(saida))
    return saida


def _quadro_notificacao(m: Momento, t: float, cor: str, tamanho) -> Image.Image:
    img = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    _q_notificacao(img, m, t, ease_out_cubico(t / ENTRADA), rgb(cor))
    return img
