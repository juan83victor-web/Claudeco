"""Linha de comando que segue o roteiro: receber, ouvir, cortar, amostra, final.

Exemplo:
    python -m edit_ia_pro receber video.mp4 --base .
    python -m edit_ia_pro ouvir video.mp4 --base .
    python -m edit_ia_pro cortar video.mp4 --base . [--tirar 3-5]
    python -m edit_ia_pro amostra video.mp4 --base . --estilo estilo.json
    python -m edit_ia_pro final video.mp4 --base . --estilo estilo.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import conferir, corte as corte_mod, estado, final, ganchos, meta, motion
from .ferramentas import detectar_silencios, garantir_ffmpeg, sondar
from .montagem import montar_corte
from .rosto import Rosto, detectar_rostos
from .transcricao import Palavra, carregar, salvar, transcrever


def _pasta(args) -> Path:
    return estado.pasta_do_video(args.base, args.video)


def cmd_receber(args) -> None:
    info = sondar(args.video)
    pasta = _pasta(args)
    formato = "vertical" if info["vertical"] else "horizontal"
    print(f"Vídeo de {info['duracao']:.0f} s, {formato}, {'com' if info['tem_audio'] else 'SEM'} som.")
    if info["duracao"] > 90:
        print("Passa de 90 s: sugiro dividir em partes.")
    if min(info["largura"], info["altura"]) < 720:
        print("Qualidade baixa: o resultado fica melhor com o arquivo original (salvo em Arquivos).")
    estado.anotar(pasta, f"recebido {Path(args.video).name}: {info['duracao']:.1f}s {formato}")


def cmd_ouvir(args) -> None:
    pasta = _pasta(args)
    if args.palavras:
        palavras = carregar(args.palavras)
    else:
        palavras = transcrever(args.video, args.modelo, args.nomes)
    salvar(palavras, pasta / "palavras.json")
    info = sondar(args.video)
    plano = corte_mod.planejar(palavras, info["duracao"], detectar_silencios(args.video))
    (pasta / "plano.json").write_text(json.dumps([asdict(t) for t in plano.trechos]))
    print(plano.resumo())
    print("Posso cortar?")


def _trechos(pasta: Path) -> list[corte_mod.Trecho]:
    return [corte_mod.Trecho(**t) for t in json.loads((pasta / "plano.json").read_text())]


def cmd_cortar(args) -> None:
    pasta = _pasta(args)
    trechos = _trechos(pasta)
    for pedido in args.tirar or []:
        de, ate = (float(x) for x in pedido.split("-"))
        trechos = corte_mod.remover_intervalo(trechos, de, ate)
        estado.anotar(pasta, f"tirado do corte: {de}s a {ate}s")
    (pasta / "plano.json").write_text(json.dumps([asdict(t) for t in trechos]))
    montar_corte(args.video, trechos, pasta / "corte.mp4")
    palavras = corte_mod.palavras_no_corte(carregar(pasta / "palavras.json"), trechos)
    salvar(palavras, pasta / "palavras_corte.json")
    (pasta / "emendas.json").write_text(json.dumps(corte_mod.emendas(trechos)))
    print(f"Corte pronto: {sum(t.duracao for t in trechos):.1f} s. Assiste. Tá bom?")


def _rostos(pasta: Path) -> list[Rosto]:
    arquivo = pasta / "rostos.json"
    if arquivo.exists():
        return [Rosto(**r) for r in json.loads(arquivo.read_text())]
    rostos = detectar_rostos(pasta / "corte.mp4")
    arquivo.write_text(json.dumps([asdict(r) for r in rostos]))
    return rostos


def _estilo(args, pasta: Path) -> final.Estilo:
    origem = Path(args.estilo) if args.estilo else pasta / "estilo.json"
    estilo = final.Estilo.de_json(json.loads(origem.read_text())) if origem.exists() else final.Estilo()
    (pasta / "estilo.json").write_text(json.dumps(estilo.para_json(), ensure_ascii=False, indent=1))
    return estilo


def cmd_sugerir(args) -> None:
    pasta = _pasta(args)
    palavras = carregar(pasta / "palavras_corte.json")
    print("Ganchos:")
    for i, g in enumerate(ganchos.sugerir_ganchos(palavras), 1):
        print(f"  {i}. {g}")
    duracao = sondar(pasta / "corte.mp4")["duracao"]
    momentos = motion.sugerir_momentos(palavras, args.ritmo, fim_gancho=3.0, duracao=duracao)
    print("Animações: " + (", ".join(m.descricao() for m in momentos) or "nenhum momento forte achado"))


def _compor(args, amostra: bool) -> None:
    pasta = _pasta(args)
    estilo = _estilo(args, pasta)
    corte = pasta / "corte.mp4"
    palavras = carregar(pasta / "palavras_corte.json")
    emendas = json.loads((pasta / "emendas.json").read_text())
    rostos = _rostos(pasta)
    duracao = sondar(corte)["duracao"]
    fim_gancho = 2.8 if estilo.texto_gancho else 0.5
    momentos = motion.sugerir_momentos(palavras, estilo.ritmo, fim_gancho=fim_gancho, duracao=duracao,
                                       bloqueios=estilo.bloqueios())
    janelas = final.janelas_da_amostra(duracao, momentos, estilo) if amostra else None
    nome = "amostra.mp4" if amostra else "final.mp4"
    res = final.compor(corte, palavras, emendas, estilo, pasta / ("work_amostra" if amostra else "work_final"),
                       pasta / nome, rostos, momentos, janelas)
    alertas = meta.conferir_fala(palavras, {"gancho": estilo.texto_gancho or "", "chamada": estilo.chamada or ""})
    for a in alertas:
        print("Atenção:", a)
    for aviso in res.avisos:
        print("Aviso:", aviso)
    if not amostra:
        ok, a, b = conferir.duracao_bate(res.arquivo, corte)
        print(f"Duração final {a:.2f}s x corte {b:.2f}s: {'ok' if ok else 'NÃO BATE'}")
        conferir.extrair_quadros(res.arquivo, pasta / "quadros")
        estado.anotar(pasta, f"final entregue com estilo {json.dumps(estilo.para_json(), ensure_ascii=False)}")
    else:
        estado.anotar(pasta, f"amostra feita: legenda {estilo.legenda}, gancho {estilo.gancho}, cor {estilo.cor}")
    print(f"Pronto: {res.arquivo}")
    print("Toque no vídeo, depois em compartilhar e em Salvar vídeo. Ele vai pra sua galeria.")


def cmd_meta(args) -> None:
    pasta = _pasta(args)
    arquivo = pasta / "palavras_corte.json"
    palavras = carregar(arquivo if arquivo.exists() else pasta / "palavras.json")
    alertas = meta.conferir_fala(palavras)
    print("\n".join(str(a) for a in alertas) or "Nenhuma frase que a Meta costuma reprovar.")


def main(argv: list[str] | None = None) -> None:
    garantir_ffmpeg()
    p = argparse.ArgumentParser(prog="edit_ia_pro", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)

    def novo(nome, funcao, ajuda):
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("video")
        s.add_argument("--base", default=".", help="onde fica a pasta edit-ia-pro/")
        s.set_defaults(funcao=funcao)
        return s

    novo("receber", cmd_receber, "confere duração, formato e som")
    s = novo("ouvir", cmd_ouvir, "transcreve e planeja o corte")
    s.add_argument("--modelo", default="small")
    s.add_argument("--nomes", nargs="*", help="nomes difíceis da fala (marca, produto)")
    s.add_argument("--palavras", help="usar uma transcrição pronta (json)")
    s = novo("cortar", cmd_cortar, "monta o corte.mp4")
    s.add_argument("--tirar", action="append", help="tirar um trecho do corte, ex.: 3-5")
    s = novo("sugerir", cmd_sugerir, "ganchos e momentos de animação")
    s.add_argument("--ritmo", default="medias", choices=["nenhuma", "poucas", "medias", "muitas"])
    for nome, amostra in (("amostra", True), ("final", False)):
        s = novo(nome, lambda a, amostra=amostra: _compor(a, amostra), f"monta {'a amostra' if amostra else 'o vídeo completo'}")
        s.add_argument("--estilo", help="json com o estilo aprovado")
    novo("meta", cmd_meta, "confere frases que a Meta reprova")
    args = p.parse_args(argv)
    args.funcao(args)


if __name__ == "__main__":
    main()
