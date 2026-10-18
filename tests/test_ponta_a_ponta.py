"""Roteiro inteiro sobre um vídeo sintético: corte, vídeo completo e amostra."""

import json

import pytest

from edit_ia_pro import cli, conferir, corte, final, montagem
from edit_ia_pro.audio import medir_lufs
from edit_ia_pro.ferramentas import detectar_silencios, ffmpeg, sondar

pytestmark = pytest.mark.lento


@pytest.fixture(scope="module")
def cortado(tmp_path_factory, video_sintetico, roteiro):
    pasta = tmp_path_factory.mktemp("corte")
    info = sondar(video_sintetico)
    plano = corte.planejar(roteiro, info["duracao"], detectar_silencios(video_sintetico))
    saida = montagem.montar_corte(video_sintetico, plano.trechos, pasta / "corte.mp4")
    return pasta, saida, plano


def test_corte_vertical_e_com_a_duracao_planejada(cortado, video_sintetico):
    _, saida, plano = cortado
    info = sondar(saida)
    assert (info["largura"], info["altura"]) == (1080, 1920)
    assert info["fps"] == 30
    assert abs(info["duracao"] - plano.duracao_final) < 0.1
    assert info["duracao"] < sondar(video_sintetico)["duracao"] - 5


def test_corte_sem_respiro(cortado):
    _, saida, _ = cortado
    # o roteiro tem bipes contínuos: no corte não pode sobrar silêncio maior que 0,25 s
    assert detectar_silencios(saida, minimo=0.25) == []


def test_video_completo(cortado, roteiro, tmp_path):
    _, saida, plano = cortado
    palavras = corte.palavras_no_corte(roteiro, plano.trechos)
    ffmpeg("-f", "lavfi", "-i", "testsrc=s=800x600:d=1", "-frames:v", "1", str(tmp_path / "img.png"))
    ffmpeg("-f", "lavfi", "-i", "sine=f=220:d=4", "-ar", "48000", str(tmp_path / "trilha.wav"))
    estilo = final.Estilo(
        legenda="pulso", gancho="tarjas", texto_gancho="O erro que trava seu vídeo", cor="rosa",
        chamada="Toque em Saiba Mais", trilha=str(tmp_path / "trilha.wav"),
        telas_divididas=[final.TelaDividida(str(tmp_path / "img.png"), 5.0, 6.5)],
    )
    res = final.compor(saida, palavras, corte.emendas(plano.trechos), estilo, tmp_path / "work", tmp_path / "final.mp4")
    ok, a, b = conferir.duracao_bate(res.arquivo, saida)
    assert ok, (a, b)
    assert abs(medir_lufs(res.arquivo) - (-14)) < 1.0
    assert res.momentos and all(m.inicio >= 2.8 for m in res.momentos)
    assert all(m.fim <= 5.0 or m.inicio >= 6.5 for m in res.momentos)
    assert all(y.tempo - x.tempo >= 0.6 for x, y in zip(res.sons, res.sons[1:]))
    quadros = conferir.extrair_quadros(res.arquivo, tmp_path / "quadros")
    assert len(quadros) == 6 and all(q.stat().st_size > 1000 for q in quadros)


def test_amostra_so_com_o_comeco(cortado, roteiro, tmp_path):
    _, saida, plano = cortado
    palavras = corte.palavras_no_corte(roteiro, plano.trechos)
    estilo = final.Estilo(texto_gancho="Três erros de edição", ritmo="medias")
    janelas = [(0.0, 4.0)]
    res = final.compor(saida, palavras, corte.emendas(plano.trechos), estilo, tmp_path / "w", tmp_path / "amostra.mp4",
                       janelas=janelas)
    assert abs(res.duracao - 4.0) < 0.1


def test_janelas_da_amostra():
    from edit_ia_pro.motion import Momento

    estilo = final.Estilo(telas_divididas=[final.TelaDividida("x.png", 20.0, 24.0)])
    janelas = final.janelas_da_amostra(40.0, [Momento("impacto", 14.0, 15.5, {"texto": "X"})], estilo)
    assert janelas[0] == (0.0, 9.0)
    assert any(a <= 14.0 < b for a, b in janelas)
    assert any(a <= 20.0 < b for a, b in janelas)


def test_cli_do_comeco_ao_fim(tmp_path, video_sintetico, roteiro, capsys):
    from edit_ia_pro.transcricao import salvar

    salvar(roteiro, tmp_path / "palavras.json")
    base = ["--base", str(tmp_path)]
    video = str(video_sintetico)
    cli.main(["receber", video, *base])
    cli.main(["ouvir", video, *base, "--palavras", str(tmp_path / "palavras.json")])
    cli.main(["cortar", video, *base])
    cli.main(["sugerir", video, *base])
    (tmp_path / "estilo.json").write_text(json.dumps({"legenda": "Caixa na palavra", "gancho": "Vidro escuro",
                                                      "texto_gancho": "Três erros de edição", "cor": "azul bebê"}))
    cli.main(["final", video, *base, "--estilo", str(tmp_path / "estilo.json")])
    saida = capsys.readouterr().out
    assert "Posso cortar?" in saida
    assert "Ganchos:" in saida and "Animações:" in saida
    assert "ok" in saida and "Salvar vídeo" in saida
    pasta = tmp_path / "edit-ia-pro" / "bruto"
    assert (pasta / "final.mp4").exists()
    assert len(list((pasta / "quadros").glob("*.jpg"))) == 6
    linhas = (pasta / "estado.md").read_text()
    assert "final entregue" in linhas and "#8EC9FF" in linhas
    assert video_sintetico.exists()  # o original nunca é alterado
