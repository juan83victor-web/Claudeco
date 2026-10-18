"""Efeitos sonoros simples gerados com o próprio ffmpeg e a agenda deles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ferramentas import ffmpeg

DISTANCIA_MINIMA = 0.6
VOLUME_NORMAL = -18.0   # dBFS (faixa -16 a -19)
VOLUME_FORTE = -11.0    # momentos fortes (faixa -10 a -12)

# nome: (duração, filtro lavfi, onde fica o pico em segundos)
RECEITAS = {
    "whoosh": (0.6, "anoisesrc=d=0.6:c=pink:a=0.8,bandpass=f=1800:w=1400,"
                    "afade=t=in:d=0.35:curve=exp,afade=t=out:st=0.35:d=0.25", 0.35),
    "whoosh_subindo": (0.6, "anoisesrc=d=0.6:c=white:a=0.6,highpass=f=600,lowpass=f=5000,"
                            "afade=t=in:d=0.5:curve=exp,afade=t=out:st=0.5:d=0.1", 0.5),
    "swish": (0.3, "anoisesrc=d=0.3:c=white:a=0.6,bandpass=f=3500:w=2500,"
                   "afade=t=in:d=0.12,afade=t=out:st=0.12:d=0.18", 0.12),
    "pop": (0.15, "sine=f=520:d=0.15,aeval='val(0)*exp(-28*t)*(1+0.6*sin(2*PI*1040*t))'", 0.0),
    "clique": (0.05, "anoisesrc=d=0.05:c=white:a=1,highpass=f=2000,aeval='val(0)*exp(-120*t)'", 0.0),
    "tique": (0.04, "sine=f=2400:d=0.04,aeval='val(0)*exp(-90*t)'", 0.0),
    "ding": (1.0, "sine=f=1318:d=1,aeval='val(0)*exp(-4.5*t)+0.4*sin(2*PI*2636*t)*exp(-7*t)'", 0.0),
    "impacto": (0.7, "sine=f=55:d=0.7,aeval='val(0)*exp(-6*t)+0.5*(random(0)*2-1)*exp(-30*t)',lowpass=f=900", 0.0),
    "impacto_seco": (0.35, "sine=f=90:d=0.35,aeval='val(0)*exp(-14*t)+0.7*(random(0)*2-1)*exp(-45*t)',lowpass=f=2500", 0.0),
    "teclado": (0.5, "anoisesrc=d=0.5:c=white:a=1,highpass=f=1500,"
                     "aeval='val(0)*exp(-60*mod(t\\,0.08))*lt(mod(t\\,0.08)\\,0.03)'", 0.0),
    "rabisco": (0.45, "anoisesrc=d=0.45:c=pink:a=0.7,bandpass=f=2500:w=1800,"
                      "aeval='val(0)*(0.6+0.4*sin(2*PI*14*t))',afade=t=out:st=0.3:d=0.15", 0.1),
}


@dataclass
class Som:
    tempo: float      # quando o pico do som acontece no vídeo
    nome: str
    forte: bool = False

    @property
    def volume(self) -> float:
        return VOLUME_FORTE if self.forte else VOLUME_NORMAL


def gerar(nome: str, pasta: str | Path) -> Path:
    """Gera o .wav do efeito (48 kHz estéreo)."""
    duracao, filtro, _ = RECEITAS[nome]
    destino = Path(pasta) / f"{nome}.wav"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg("-f", "lavfi", "-i", f"{filtro},aformat=sample_rates=48000:channel_layouts=stereo",
               "-t", f"{duracao}", "-af", "loudnorm=I=-16:TP=-1,aresample=48000", str(destino))
    return destino


def agendar(sons: list[Som], duracao: float) -> list[Som]:
    """Nunca dois sons a menos de 0,6 s um do outro; os fortes têm preferência."""
    escolhidos: list[Som] = []
    for s in sorted(sons, key=lambda s: (not s.forte, s.tempo)):
        if 0 <= s.tempo < duracao and all(abs(s.tempo - o.tempo) >= DISTANCIA_MINIMA for o in escolhidos):
            escolhidos.append(s)
    return sorted(escolhidos, key=lambda s: s.tempo)


def sons_sem_animacao(fim_gancho_entrada: float, tempos_imagens: list[float], tempo_chamada: float | None) -> list[Som]:
    """Sem animação: whoosh na entrada do gancho, pop quando entra imagem, ding na chamada."""
    sons = [Som(0.05 + RECEITAS["whoosh"][2], "whoosh")]
    sons += [Som(t, "pop") for t in tempos_imagens]
    if tempo_chamada is not None:
        sons.append(Som(tempo_chamada, "ding"))
    return sons


def inicio_do_arquivo(s: Som) -> float:
    """Desloca o arquivo pro pico cair no tempo certo."""
    return max(s.tempo - RECEITAS[s.nome][2], 0.0)
