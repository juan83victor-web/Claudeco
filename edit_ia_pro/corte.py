"""Passo 2 · Ouvir e cortar: pausas, tomadas repetidas, vícios e bordas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .transcricao import Palavra

PAUSA_MAXIMA = 0.25      # silêncio maior que isso entre palavras sai
FOLGA_ANTES = 0.06
FOLGA_DEPOIS = 0.10
PALAVRA_LONGA = 1.2      # palavra mais longa que isso pode esconder uma tomada repetida
PAUSA_DE_FRASE = 0.7     # pausa que separa frases mesmo sem pontuação

VICIOS = {"ee", "eee", "eeee", "hum", "hm", "hmm", "humm", "ahn", "ah", "aham", "eh", "uh"}
VICIOS_DUPLOS = {("tipo", "assim")}


@dataclass
class Trecho:
    inicio: float
    fim: float

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


@dataclass
class PlanoDeCorte:
    trechos: list[Trecho]
    palavras_mantidas: list[Palavra]
    duracao_original: float
    pausas_removidas: int = 0
    frases_repetidas: int = 0
    vicios_removidos: int = 0
    tomadas_mantidas: list[str] = field(default_factory=list)
    suspeitas: list[Palavra] = field(default_factory=list)

    @property
    def duracao_final(self) -> float:
        return sum(t.duracao for t in self.trechos)

    def resumo(self) -> str:
        """Plano em até 3 linhas, em palavras do dia a dia."""
        partes = [_contar(self.pausas_removidas, "pausa", "pausas")]
        if self.frases_repetidas:
            partes.append(_contar(self.frases_repetidas, "frase repetida", "frases repetidas"))
        if self.vicios_removidos:
            partes.append(_contar(self.vicios_removidos, "'éé' ou 'hum'", "'éé' e 'hum'"))
        linhas = [
            "tirei " + _juntar(partes),
            f"o vídeo foi de {_relogio(self.duracao_original)} pra {_relogio(self.duracao_final)}",
        ]
        if self.tomadas_mantidas:
            linhas.append("fiquei com " + _juntar(self.tomadas_mantidas))
        if self.suspeitas:
            tempos = ", ".join(_relogio(p.inicio) for p in self.suspeitas[:3])
            linhas.append(f"confere em {tempos}: pode ter frase repetida escondida")
        return "\n".join(linhas[:3] if len(linhas) <= 3 else linhas[:2] + ["; ".join(linhas[2:])])


def _contar(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _juntar(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _relogio(segundos: float) -> str:
    s = int(round(segundos))
    return f"{s // 60}:{s % 60:02d}"


def normalizar(texto: str) -> str:
    """Minúsculo, sem acento e sem pontuação."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", "", texto).strip()


def termina_frase(texto: str) -> bool:
    return texto.rstrip().endswith((".", "!", "?", "…"))


def separar_frases(palavras: list[Palavra]) -> list[list[int]]:
    """Índices das palavras de cada frase (pontuação final ou pausa longa)."""
    frases: list[list[int]] = []
    atual: list[int] = []
    for i, p in enumerate(palavras):
        if atual and p.inicio - palavras[atual[-1]].fim > PAUSA_DE_FRASE:
            frases.append(atual)
            atual = []
        atual.append(i)
        if termina_frase(p.texto):
            frases.append(atual)
            atual = []
    if atual:
        frases.append(atual)
    return frases


def _comeco(palavras: list[Palavra], frase: list[int], n: int) -> list[str]:
    return [w for w in (normalizar(palavras[i].texto) for i in frase[:n]) if w]


def mesma_frase(a: list[str], b: list[str]) -> bool:
    """Duas frases começam igual ou quase igual (3 a 5 primeiras palavras)."""
    n = min(5, len(a), len(b))
    if n == 0:
        return False
    if n < 3:
        # frase abandonada bem no começo ("Hoje eu..." e "Hoje eu vou mostrar")
        return a[:n] == b[:n] and n >= 2
    return SequenceMatcher(None, " ".join(a[:n]), " ".join(b[:n])).ratio() >= 0.8


def tomadas_repetidas(palavras: list[Palavra], frases: list[list[int]]) -> tuple[set[int], list[str]]:
    """Frases a remover: de cada grupo de tomadas fica a ÚLTIMA que foi até o fim.

    Só compara frases vizinhas em sequência (a pessoa regrava logo em seguida).
    """
    remover: set[int] = set()
    notas: list[str] = []
    i = 0
    while i < len(frases):
        grupo = [i]
        j = i + 1
        while j < len(frases) and mesma_frase(_comeco(palavras, frases[grupo[-1]], 5), _comeco(palavras, frases[j], 5)):
            grupo.append(j)
            j += 1
        if len(grupo) > 1:
            completas = [g for g in grupo if termina_frase(palavras[frases[g][-1]].texto)]
            fica = completas[-1] if completas else max(grupo, key=lambda g: (len(frases[g]), g))
            remover.update(g for g in grupo if g != fica)
            ordem = ["primeira", "segunda", "terceira", "quarta", "quinta"]
            pos = grupo.index(fica)
            nome = ordem[pos] if pos < len(ordem) else f"{pos + 1}ª"
            notas.append(f"a {nome} tomada de \"{' '.join(_comeco(palavras, frases[fica], 4))}...\"")
        i = j
    return remover, notas


def vicios(palavras: list[Palavra]) -> set[int]:
    """'Éé', 'hum', 'tipo assim' soltos."""
    fora: set[int] = set()
    for i, p in enumerate(palavras):
        n = normalizar(p.texto)
        if n in VICIOS or re.fullmatch(r"e{2,}|h?m{2,}|a+h+n*", n or "x"):
            fora.add(i)
    for i in range(len(palavras) - 1):
        par = (normalizar(palavras[i].texto), normalizar(palavras[i + 1].texto))
        if par in VICIOS_DUPLOS:
            solto = palavras[i + 1].texto.endswith(",") or (
                i + 2 >= len(palavras) or palavras[i + 2].inicio - palavras[i + 1].fim > 0.2
            ) or (i > 0 and palavras[i - 1].texto.endswith(","))
            if solto:
                fora.update({i, i + 1})
    return fora


def palavras_suspeitas(palavras: list[Palavra]) -> list[Palavra]:
    """Palavras longas demais: costumam esconder a mesma frase dita duas vezes."""
    return [p for p in palavras if p.duracao > PALAVRA_LONGA]


def montar_trechos(
    palavras: list[Palavra],
    manter: list[int],
    duracao: float,
    pausa_maxima: float = PAUSA_MAXIMA,
    silencios: list[tuple[float, float]] | None = None,
) -> tuple[list[Trecho], int]:
    """Agrupa palavras mantidas em trechos e aplica a folga nas bordas.

    A folga nunca entra na palavra vizinha (mantida ou não) e nunca corta palavra.
    Devolve os trechos e quantas pausas saíram.
    """
    if not manter:
        return [], 0
    blocos: list[list[int]] = [[manter[0]]]
    pausas = 0
    for anterior, atual in zip(manter, manter[1:]):
        vizinhas = atual == anterior + 1
        lacuna = palavras[atual].inicio - palavras[anterior].fim
        if vizinhas and lacuna <= pausa_maxima:
            blocos[-1].append(atual)
        else:
            if vizinhas:
                pausas += 1
            blocos.append([atual])
    trechos = []
    for bloco in blocos:
        primeira, ultima = bloco[0], bloco[-1]
        limite_antes = palavras[primeira - 1].fim if primeira > 0 else 0.0
        limite_depois = palavras[ultima + 1].inicio if ultima + 1 < len(palavras) else duracao
        inicio = max(palavras[primeira].inicio - FOLGA_ANTES, limite_antes, 0.0)
        fim = min(palavras[ultima].fim + FOLGA_DEPOIS, limite_depois, duracao)
        inicio = min(inicio, palavras[primeira].inicio)
        fim = max(fim, palavras[ultima].fim)
        trechos.append(Trecho(round(inicio, 3), round(fim, 3)))
    # Junta trechos que se encostam depois da folga.
    unidos = [trechos[0]]
    for t in trechos[1:]:
        if t.inicio <= unidos[-1].fim + 1e-3:
            unidos[-1].fim = max(unidos[-1].fim, t.fim)
        else:
            unidos.append(t)
    unidos, extras = _tirar_silencios(unidos, silencios or [], pausa_maxima)
    return unidos, pausas + extras


def _tirar_silencios(trechos: list[Trecho], silencios, pausa_maxima: float) -> tuple[list[Trecho], int]:
    """silencedetect confirma pausas que o tempo das palavras escondeu (palavra esticada)."""
    tirados = 0
    for s0, s1 in silencios:
        a, b = s0 + FOLGA_DEPOIS, s1 - FOLGA_ANTES
        if s1 - s0 <= pausa_maxima or b <= a:
            continue
        novos = []
        for t in trechos:
            if t.fim <= a or t.inicio >= b:
                novos.append(t)
                continue
            tirados += 1
            if t.inicio < a:
                novos.append(Trecho(t.inicio, round(a, 3)))
            if t.fim > b:
                novos.append(Trecho(round(b, 3), t.fim))
        trechos = [t for t in novos if t.duracao >= 0.05]
    return trechos, tirados


def planejar(
    palavras: list[Palavra],
    duracao: float,
    silencios: list[tuple[float, float]] | None = None,
    pausa_maxima: float = PAUSA_MAXIMA,
) -> PlanoDeCorte:
    frases = separar_frases(palavras)
    frases_fora, notas = tomadas_repetidas(palavras, frases)
    fora = {i for f in frases_fora for i in frases[f]}
    fora_vicios = vicios(palavras) - fora
    fora |= fora_vicios
    manter = [i for i in range(len(palavras)) if i not in fora]
    trechos, pausas = montar_trechos(palavras, manter, duracao, pausa_maxima, silencios)
    # Pausas antes do primeiro e depois do último trecho também saem.
    if trechos and trechos[0].inicio > pausa_maxima:
        pausas += 1
    if trechos and duracao - trechos[-1].fim > pausa_maxima:
        pausas += 1
    return PlanoDeCorte(
        trechos=trechos,
        palavras_mantidas=[palavras[i] for i in manter],
        duracao_original=duracao,
        pausas_removidas=pausas,
        frases_repetidas=len(frases_fora),
        vicios_removidos=len(fora_vicios),
        tomadas_mantidas=notas,
        suspeitas=[p for p in palavras_suspeitas(palavras) if p in [palavras[i] for i in manter]],
    )


def remover_intervalo(trechos: list[Trecho], de: float, ate: float) -> list[Trecho]:
    """Ajuste pedido pela pessoa: 'entre 3 e 5 segundos tira essa parte'.

    `de` e `ate` são tempos do vídeo cortado (o que ela assistiu).
    """
    original = [(mapear_para_original(trechos, de)), (mapear_para_original(trechos, ate))]
    a, b = original
    novos = []
    for t in trechos:
        if t.fim <= a or t.inicio >= b:
            novos.append(Trecho(t.inicio, t.fim))
            continue
        if t.inicio < a:
            novos.append(Trecho(t.inicio, a))
        if t.fim > b:
            novos.append(Trecho(b, t.fim))
    return [t for t in novos if t.duracao > 0.04]


def mapear_para_original(trechos: list[Trecho], t: float) -> float:
    acumulado = 0.0
    for tr in trechos:
        if t <= acumulado + tr.duracao:
            return tr.inicio + (t - acumulado)
        acumulado += tr.duracao
    return trechos[-1].fim if trechos else t


def mapear_para_corte(trechos: list[Trecho], t: float) -> float | None:
    """Tempo do original -> tempo no vídeo cortado (None se o tempo foi cortado)."""
    acumulado = 0.0
    for tr in trechos:
        if tr.inicio - 1e-6 <= t <= tr.fim + 1e-6:
            return acumulado + min(max(t - tr.inicio, 0.0), tr.duracao)
        acumulado += tr.duracao
    return None


def palavras_no_corte(palavras: list[Palavra], trechos: list[Trecho]) -> list[Palavra]:
    """Palavras mantidas com o tempo já no vídeo cortado.

    Uma palavra que perdeu só um pedaço de silêncio fica com a parte que sobrou.
    """
    saida = []
    for p in palavras:
        partes = [(max(p.inicio, t.inicio), min(p.fim, t.fim)) for t in trechos if min(p.fim, t.fim) > max(p.inicio, t.inicio)]
        if not partes:
            continue
        a, b = mapear_para_corte(trechos, partes[0][0]), mapear_para_corte(trechos, partes[-1][1])
        saida.append(Palavra(p.texto, round(a, 3), round(b, 3)))
    return saida


def emendas(trechos: list[Trecho]) -> list[float]:
    """Tempos das emendas no vídeo cortado."""
    tempos, acumulado = [], 0.0
    for t in trechos[:-1]:
        acumulado += t.duracao
        tempos.append(round(acumulado, 3))
    return tempos
