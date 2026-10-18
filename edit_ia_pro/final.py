"""Passos 4 e 5 · Amostra e vídeo completo, sempre sobre o corte.mp4 aprovado."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from . import ALTURA, FPS, LARGURA, ZONA_SEGURA
from . import ganchos, legendas, motion
from .audio import arquivos_de_som, filtro_mix, normalizar_volume
from .cores import resolver_cor, rgb
from .desenho import Peca, caber, desenhar_linhas, escalar, retangulo_arredondado
from .ferramentas import ffmpeg, sondar
from .rosto import LEGENDA_Y, Rosto, centro_do_rosto, posicao_vertical, rostos_entre
from .sons import Som, agendar, sons_sem_animacao
from .transcricao import Palavra

ZOOM = 1.08
DURACAO_CHAMADA = 1.8


@dataclass
class TelaDividida:
    imagem: str
    inicio: float
    fim: float


@dataclass
class Estilo:
    """O que a pessoa aprovou. Padrão = recomendação do roteiro."""

    legenda: str = "impacto"
    gancho: str = "manchete"
    texto_gancho: str | None = None
    cor: str = "#FFC400"
    zoom: bool = True
    ritmo: str = "medias"
    efeitos_sonoros: bool = True
    chamada: str | None = None
    trilha: str | None = None
    telas_divididas: list[TelaDividida] = field(default_factory=list)
    alvos_destaque: dict[str, list[int]] = field(default_factory=dict)  # "12.3" -> [x, y]

    @classmethod
    def de_json(cls, dados: dict) -> "Estilo":
        dados = dict(dados)
        dados["telas_divididas"] = [TelaDividida(**t) for t in dados.get("telas_divididas", [])]
        estilo = cls(**dados)
        estilo.legenda = legendas.estilo_legenda(estilo.legenda)
        estilo.gancho = ganchos.estilo_gancho(estilo.gancho)
        estilo.cor = resolver_cor(estilo.cor)
        return estilo

    def bloqueios(self) -> list[tuple[float, float]]:
        return [(t.inicio, t.fim) for t in self.telas_divididas]

    def para_json(self) -> dict:
        return asdict(self)


@dataclass
class Resultado:
    arquivo: Path
    duracao: float
    momentos: list[motion.Momento]
    sons: list[Som]
    quadros: list[Path] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _quadro(t: float) -> int:
    return int(round(t * FPS))


def filtro_zoom(emendas: list[float], total_quadros: int, centro: tuple[int, int]) -> tuple[str, int]:
    """Alterna 1,00 e 1,08 a cada emenda, centralizado no rosto. Corta por quadro (sem escorregar)."""
    limites = [0] + sorted({_quadro(e) for e in emendas if 0 < _quadro(e) < total_quadros}) + [total_quadros]
    n = len(limites) - 1
    if n <= 1:
        return "[0:v]null[zoom]", 1
    w, h = int(round(LARGURA * ZOOM / 2) * 2), int(round(ALTURA * ZOOM / 2) * 2)
    cx, cy = centro
    x = min(max(int(cx * ZOOM - LARGURA / 2), 0), w - LARGURA)
    y = min(max(int(cy * ZOOM - ALTURA / 2), 0), h - ALTURA)
    partes = [f"[0:v]split={n}" + "".join(f"[zs{i}]" for i in range(n))]
    for i, (a, b) in enumerate(zip(limites, limites[1:])):
        cadeia = f"[zs{i}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS"
        if i % 2 == 1:
            cadeia += f",scale={w}:{h},crop={LARGURA}:{ALTURA}:{x}:{y},setsar=1"
        partes.append(cadeia + f"[zt{i}]")
    partes.append("".join(f"[zt{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,setpts=N/{FPS}/TB[zoom]")
    return ";\n".join(partes), n


def desenhar_chamada(texto: str, cor: str, y_centro: int) -> Image.Image:
    img = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    f = caber(texto, "montserrat", 72, 640, 900)
    rascunho = Image.new("RGBA", img.size)
    x0, y0, x1, y1 = desenhar_linhas(rascunho, [Peca(texto, f, (20, 20, 24, 255))], LARGURA // 2, y_centro, 680)
    retangulo_arredondado(img, (x0 - 50, y0 - 40, x1 + 50, y1 + 52), 32, (255, 255, 255, 245), sombra=True)
    from PIL import ImageDraw
    ImageDraw.Draw(img).rounded_rectangle(((x0 + x1) // 2 - 60, y1 + 18, (x0 + x1) // 2 + 60, y1 + 28), 5, fill=rgb(cor))
    img.alpha_composite(rascunho)
    return img


def _camada_chamada(texto: str, cor: str, pasta: Path, duracao: float, rostos: list[Rosto]) -> Path:
    inicio = max(duracao - DURACAO_CHAMADA, 0)
    y = posicao_vertical(260, rostos_entre(rostos, inicio, duracao), preferido=760)
    parado = desenhar_chamada(texto, cor, y)
    conteudo = parado.getchannel("A").getbbox()
    recorte = parado.crop(conteudo)
    entradas = []
    for i, escala in enumerate((0.9, 0.95, 0.98, 1.0)):
        img = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
        peq = escalar(recorte, escala)
        img.alpha_composite(peq, (int((conteudo[0] + conteudo[2]) / 2 - peq.width / 2), int((conteudo[1] + conteudo[3]) / 2 - peq.height / 2)))
        arq = pasta / f"chamada_{i}.png"
        img.save(arq, compress_level=1)
        t0 = inicio + i / FPS
        entradas.append((arq, t0, t0 + 1 / FPS if i < 3 else duracao))
    vazio = pasta / "vazio.png"
    Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0)).save(vazio)
    return legendas.escrever_concat(entradas, duracao, pasta / "chamada.ffconcat", vazio)


def _cruza_legenda(caixa: tuple[int, int, int, int]) -> bool:
    meio = legendas.altura_estimada("impacto") // 2
    return caixa[1] < LEGENDA_Y + meio and caixa[3] > LEGENDA_Y - meio


def compor(
    corte: str | Path,
    palavras: list[Palavra],
    emendas: list[float],
    estilo: Estilo,
    pasta: str | Path,
    saida: str | Path,
    rostos: list[Rosto] | None = None,
    momentos: list[motion.Momento] | None = None,
    janelas: list[tuple[float, float]] | None = None,
) -> Resultado:
    """Monta o vídeo na ordem do roteiro. Com `janelas`, só esses trechos (amostra)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    info = sondar(corte)
    duracao = info["duracao"]
    total_quadros = _quadro(duracao)
    rostos = rostos or []
    avisos: list[str] = []

    def importa(a: float, b: float) -> bool:
        return janelas is None or any(min(b, j1) > max(a, j0) for j0, j1 in janelas)

    entradas: list[list[str]] = [["-i", str(corte)]]

    def nova_entrada(*args: str) -> int:
        entradas.append(list(args))
        return len(entradas) - 1

    # 1. zoom nos cortes
    grafo = []
    if estilo.zoom:
        trecho, _ = filtro_zoom(emendas, total_quadros, centro_do_rosto(rostos))
        grafo.append(trecho)
    else:
        grafo.append("[0:v]null[zoom]")
    atual = "[zoom]"

    # 2. tela dividida: imagem em cima (1080x960), pessoa embaixo recortada pelo rosto
    for n, tela in enumerate(estilo.telas_divididas):
        if not importa(tela.inicio, tela.fim):
            continue
        k = nova_entrada("-loop", "1", "-framerate", str(FPS), "-t", f"{duracao:.3f}", "-i", tela.imagem)
        _, cy = centro_do_rosto(rostos_entre(rostos, tela.inicio, tela.fim))
        y = min(max(cy - 480, 0), ALTURA - 960)
        quando = f"between(t,{tela.inicio:.3f},{tela.fim:.3f})"
        grafo.append(
            f"{atual}split=2[td_base{n}][td_p{n}];"
            f"[td_p{n}]crop={LARGURA}:960:0:{y}[td_pessoa{n}];"
            f"[{k}:v]scale={LARGURA}:960:force_original_aspect_ratio=increase,crop={LARGURA}:960,setsar=1,format=rgba[td_img{n}];"
            f"[td_base{n}][td_img{n}]overlay=0:0:enable='{quando}'[td_a{n}];"
            f"[td_a{n}][td_pessoa{n}]overlay=0:960:enable='{quando}'[td{n}]"
        )
        atual = f"[td{n}]"

    # 3. gancho
    fim_gancho = 0.0
    if estilo.texto_gancho:
        lista_gancho, fim_gancho = ganchos.gerar_camada(estilo.texto_gancho, estilo.gancho, estilo.cor, pasta / "gancho", duracao)
    # 4. momentos das animações (nada durante o gancho)
    if momentos is None:
        momentos = motion.sugerir_momentos(palavras, estilo.ritmo, fim_gancho=max(fim_gancho, 0.5), duracao=duracao,
                                           bloqueios=estilo.bloqueios())
    ocultar: list[tuple[float, float]] = []
    animacoes = []
    for n, m in enumerate(momentos):
        if not importa(m.inicio, m.fim):
            continue
        alvo = estilo.alvos_destaque.get(f"{m.inicio:.1f}")
        pos = motion.posicionar(m, rostos, tuple(alvo) if alvo else None)
        caixa = motion.caixa_na_tela(m, pos)
        if _cruza_legenda(caixa):
            ocultar.append((m.inicio, m.fim))
        if caixa[0] < ZONA_SEGURA[0] - 40 or caixa[2] > ZONA_SEGURA[2] + 40:
            avisos.append(f"animação em {m.inicio:.1f}s encosta na borda da zona segura")
        animacoes.append((m, pos, motion.renderizar(m, estilo.cor, pasta / f"motion_{n:02d}")))

    # 5. chamada final (se não houver comentário sendo digitado no fim)
    chamada_inicio = None
    tem_comentario_final = any(m.tipo == "comentario" and m.fim > duracao - DURACAO_CHAMADA for m in momentos)
    if estilo.chamada and not tem_comentario_final and importa(duracao - DURACAO_CHAMADA, duracao):
        chamada_inicio = max(duracao - DURACAO_CHAMADA, 0)
        ocultar.append((chamada_inicio, duracao + 1))
        lista_chamada = _camada_chamada(estilo.chamada, estilo.cor, pasta / "chamada", duracao, rostos)

    # 6. legenda
    lista_legenda = legendas.gerar_camada(palavras, estilo.legenda, estilo.cor, pasta / "legenda", duracao, rostos, ocultar)
    k = nova_entrada("-f", "concat", "-safe", "0", "-i", str(lista_legenda))
    grafo.append(f"[{k}:v]format=rgba[leg];{atual}[leg]overlay=0:0:eof_action=pass:format=auto[c_leg]")
    atual = "[c_leg]"
    if estilo.texto_gancho:
        k = nova_entrada("-f", "concat", "-safe", "0", "-i", str(lista_gancho))
        grafo.append(f"[{k}:v]format=rgba[gan];{atual}[gan]overlay=0:0:eof_action=pass:format=auto[c_gan]")
        atual = "[c_gan]"
    for n, (m, (x, y), mov) in enumerate(animacoes):
        k = nova_entrada("-i", str(mov))
        grafo.append(
            f"[{k}:v]format=rgba,setpts=PTS-STARTPTS+{m.inicio:.3f}/TB[m{n}];"
            f"{atual}[m{n}]overlay={x}:{y}:eof_action=pass:format=auto:enable='between(t,{m.inicio:.3f},{m.fim:.3f})'[c_m{n}]"
        )
        atual = f"[c_m{n}]"
    if chamada_inicio is not None:
        k = nova_entrada("-f", "concat", "-safe", "0", "-i", str(lista_chamada))
        grafo.append(f"[{k}:v]format=rgba[cha];{atual}[cha]overlay=0:0:eof_action=pass:format=auto[c_cha]")
        atual = "[c_cha]"
    grafo.append(f"{atual}format=yuv420p[vfinal]")

    # 7. efeitos sonoros
    sons: list[Som] = []
    if estilo.efeitos_sonoros:
        if animacoes:
            for m, _, _ in animacoes:
                sons += [Som(t, nome, forte) for t, nome, forte in motion.sons_do_momento(m)]
            if estilo.texto_gancho:
                sons.append(Som(0.4, "whoosh"))
            if chamada_inicio is not None:
                sons.append(Som(chamada_inicio + 0.05, "ding"))
        else:
            sons = sons_sem_animacao(0.0, [t.inicio for t in estilo.telas_divididas], chamada_inicio)
            if not estilo.texto_gancho:
                sons = [s for s in sons if s.nome != "whoosh"]
        sons = agendar(sons, duracao)
    primeira_som = len(entradas)
    for arq in arquivos_de_som(sons, pasta / "sons"):
        nova_entrada("-i", str(arq))
    # 8. trilha (só se a pessoa mandou)
    indice_trilha = nova_entrada("-stream_loop", "-1", "-i", estilo.trilha) if estilo.trilha else None
    filtro_audio, rotulo_audio = filtro_mix(sons, duracao, primeira_som, indice_trilha)
    grafo.append(filtro_audio)

    rotulo_video, rotulo_final_audio = "[vfinal]", rotulo_audio
    if janelas:
        grafo.append(_filtro_janelas(janelas, rotulo_video, rotulo_audio))
        rotulo_video, rotulo_final_audio = "[vjan]", "[ajan]"

    script = pasta / "final.filtro.txt"
    script.write_text(";\n".join(grafo))
    mix = pasta / "mix.mp4"
    args = [a for e in entradas for a in e]
    ffmpeg(*args, "-filter_complex_script", str(script), "-map", rotulo_video, "-map", rotulo_final_audio,
           "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "pcm_s16le", "-ar", "48000", str(mix.with_suffix(".mov")))
    # 9. volume final: loudnorm em duas passadas, -14 LUFS
    final = normalizar_volume(mix.with_suffix(".mov"), saida)
    resultado = Resultado(Path(final), sondar(final)["duracao"], momentos, sons, avisos=avisos)
    (pasta / "montagem.json").write_text(json.dumps({
        "estilo": estilo.para_json(),
        "momentos": [m.descricao() for m in momentos],
        "sons": [asdict(s) for s in sons],
        "avisos": avisos,
    }, ensure_ascii=False, indent=1))
    return resultado


def _filtro_janelas(janelas: list[tuple[float, float]], video: str, audio: str) -> str:
    n = len(janelas)
    partes = [f"{video}split={n}" + "".join(f"[jv{i}]" for i in range(n)),
              f"{audio}asplit={n}" + "".join(f"[ja{i}]" for i in range(n))]
    pares = ""
    for i, (a, b) in enumerate(janelas):
        partes.append(f"[jv{i}]trim=start_frame={_quadro(a)}:end_frame={_quadro(b)},setpts=PTS-STARTPTS[jvt{i}]")
        partes.append(f"[ja{i}]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,"
                      f"afade=t=out:st={max(b - a - 0.01, 0):.3f}:d=0.01[jat{i}]")
        pares += f"[jvt{i}][jat{i}]"
    partes.append(f"{pares}concat=n={n}:v=1:a=1[vjan][ajan]")
    return ";\n".join(partes)


def janelas_da_amostra(duracao: float, momentos: list[motion.Momento], estilo: Estilo, primeiros: float = 9.0) -> list[tuple[float, float]]:
    """Primeiros 8 a 10 s; mais 4 s em volta da 1ª animação e da tela dividida, se caírem depois."""
    janelas = [(0.0, min(primeiros, duracao))]
    if momentos and momentos[0].inicio >= primeiros - 1:
        m = momentos[0]
        janelas.append((max(m.inicio - 1.0, primeiros), min(m.inicio + 3.0, duracao)))
    for tela in estilo.telas_divididas:
        if tela.inicio >= janelas[-1][1]:
            janelas.append((tela.inicio - 0.5, min(tela.inicio + 3.5, duracao)))
            break
    return [(a, b) for a, b in janelas if b - a > 0.5]
