"""Conferir a fala: frases que a Meta costuma reprovar em anúncios."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .corte import normalizar, separar_frases
from .transcricao import Palavra

# (padrão no texto normalizado, motivo, sugestão)
REGRAS = [
    (r"\b(reais|mil reais|\d+ ?(mil|k)\b).{0,40}\b(por (dia|semana|mes)|ganh\w*|lucr\w*|fatur\w*|renda)"
     r"|\b(ganh\w*|lucr\w*|fatur\w*|renda)\b.{0,40}(reais|\d+ ?(mil|k)\b)",
     "valor em dinheiro ligado a ganho", "fale do resultado sem número, tipo 'pra vender mais'"),
    (r"\bem \d+ dias\b|\bem (um|uma|dois|duas|tres|quatro|cinco|sete|dez|quinze|trinta) (dias?|semanas?)\b",
     "promessa com prazo ('em X dias')", "tire o prazo ou fale 'com o tempo'"),
    (r"\bgarantid\w*\b|\bgarantia de (resultado|ganho|lucro)\b", "palavra 'garantido'", "troque por 'feito pra ajudar'"),
    (r"\brenda extra de\b", "'renda extra de' com valor", "fale 'uma renda a mais' sem valor"),
    (r"\bfique rico\b|\bficar rico\b|\benriquec\w*", "promessa de ficar rico", "tire a frase"),
    (r"\bsem esforco\b|\bsem fazer nada\b|\bdinheiro facil\b", "'sem esforço'", "troque por 'de um jeito simples'"),
    (r"\bantes e depois\b.{0,40}(dinheiro|reais|conta|saldo)|(dinheiro|reais|conta|saldo).{0,40}\bantes e depois\b",
     "antes e depois de dinheiro", "mostre o processo, não o saldo"),
    (r"\bvoce que (ganha pouco|esta (endividad|desempregad|acima do peso|gord|sozinh|deprimid)|e (pobre|gord|careca|endividad))\w*"
     r"|\bvoce (esta|e) (endividad|desempregad|gord|pobre|careca|deprimid)\w*",
     "frase que aponta característica da pessoa", "fale do assunto, não de quem assiste ('pra quem quer...')"),
]


@dataclass
class Alerta:
    tempo: float
    trecho: str
    motivo: str
    sugestao: str

    def __str__(self) -> str:
        s = int(self.tempo)
        return f"{s // 60}:{s % 60:02d} \"{self.trecho}\": {self.motivo}. Sugestão: {self.sugestao}"


def conferir_texto(texto: str) -> list[tuple[str, str]]:
    """Motivos e sugestões encontrados num texto solto (gancho, chamada, animação)."""
    n = normalizar(re.sub(r"r\$", " reais ", texto, flags=re.I)) + " "
    return [(motivo, sugestao) for padrao, motivo, sugestao in REGRAS if re.search(padrao, n)]


def conferir_fala(palavras: list[Palavra], textos_tela: dict[str, str] | None = None) -> list[Alerta]:
    """Procura na transcrição (frase a frase) e nos textos da tela."""
    alertas = []
    for frase in separar_frases(palavras):
        texto = " ".join(palavras[i].texto for i in frase)
        for motivo, sugestao in conferir_texto(texto):
            alertas.append(Alerta(palavras[frase[0]].inicio, texto, motivo, sugestao))
    for onde, texto in (textos_tela or {}).items():
        for motivo, sugestao in conferir_texto(texto):
            alertas.append(Alerta(0.0, f"{onde}: {texto}", motivo, sugestao))
    return alertas
