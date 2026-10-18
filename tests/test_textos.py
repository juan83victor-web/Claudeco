import pytest
from PIL import Image

from edit_ia_pro import ZONA_SEGURA, cores, ganchos, legendas, meta
from edit_ia_pro.rosto import Rosto, posicao_vertical
from edit_ia_pro.sons import DISTANCIA_MINIMA, Som, agendar
from edit_ia_pro.transcricao import Palavra

from .conftest import falas


def _dentro_da_zona(img: Image.Image, folga: int = 0) -> bool:
    x0, y0, x1, y1 = img.getchannel("A").getbbox()
    zx0, zy0, zx1, zy1 = ZONA_SEGURA
    return x0 >= zx0 - folga and y0 >= zy0 and x1 <= zx1 + folga and y1 <= zy1


@pytest.mark.parametrize("entrada,esperado", [
    (None, "#FFC400"), ("amarelo", "#FFC400"), ("Azul Bebê", "#8EC9FF"), ("rosa", "#FF4FA3"),
    ("#ff0", "#FFFF00"), ("12ab34", "#12AB34"), ("um verde limão forte", "#B6FF3B"),
])
def test_cores(entrada, esperado):
    assert cores.resolver_cor(entrada) == esperado


def test_cor_desconhecida():
    with pytest.raises(ValueError):
        cores.resolver_cor("cor de burro quando foge")


def test_agrupar_uma_a_tres_palavras():
    palavras = falas([("Hoje eu vou te mostrar três erros.", 0.5), ("Acabou!", 0.5)])
    grupos = legendas.agrupar(palavras, "impacto")
    assert all(1 <= len(g.palavras) <= 3 for g in grupos)
    assert grupos[-1].palavras[0].texto == "Acabou!"
    assert grupos[-2].palavras[-1].texto == "erros."  # quebra na pontuação
    assert all(len(g.palavras) == 1 for g in legendas.agrupar(palavras, "gigante"))


def test_estados_cobrem_cada_palavra_sem_sobrepor():
    palavras = falas([("Um dois três quatro cinco.", 0.5)])
    est = legendas.estados(legendas.agrupar(palavras))
    assert len(est) == len(palavras)
    for a, b in zip(est, est[1:]):
        assert a.fim <= b.inicio + 1e-6


@pytest.mark.parametrize("estilo", legendas.ESTILOS)
def test_cada_estilo_de_legenda(estilo):
    grupo = legendas.Grupo([Palavra("Legenda", 0, 0.3), Palavra("bem", 0.3, 0.5), Palavra("grande", 0.5, 0.9)])
    img = legendas.desenhar(estilo, grupo, 1, "#FFC400")
    assert img.size == (1080, 1920)
    assert _dentro_da_zona(img, folga=20)
    # a palavra falada aparece na cor de destaque
    cores_usadas = {c for _, c in img.getcolors(1080 * 1920)}
    assert any(abs(c[0] - 255) < 3 and abs(c[1] - 196) < 3 and c[2] < 5 and c[3] > 200 for c in cores_usadas)


def test_nomes_dos_estilos():
    assert legendas.estilo_legenda("Caixa na palavra") == "caixa"
    assert legendas.estilo_legenda("Palavra gigante") == "gigante"
    assert ganchos.estilo_gancho("Vidro escuro") == "vidro"
    assert ganchos.estilo_gancho("Balão") == "balao"


@pytest.mark.parametrize("estilo", ganchos.ESTILOS)
def test_cada_estilo_de_gancho(estilo):
    img = ganchos.desenhar(estilo, "O erro que deixa seu vídeo sem visualização", "#FF4FA3")
    x0, y0, x1, y1 = img.getchannel("A").getbbox()
    assert 200 <= y0 and y1 <= 680  # no alto da tela, perto de y 250 a 600
    assert x0 >= ZONA_SEGURA[0] - 20 and x1 <= ZONA_SEGURA[2] + 20  # 20 px = sombra suave


def test_gancho_em_no_maximo_duas_linhas():
    linhas, _ = ganchos.dividir_linhas("Esse é um gancho bem comprido demais pra caber em uma linha", "anton", 110)
    assert len(linhas) <= 2


def test_sugerir_ganchos_tirados_da_fala():
    palavras = falas([
        ("Você comete esse erro no seu vídeo?", 0.5),
        ("Ganhe 5 mil reais por mês sem esforço.", 0.5),
        ("Hoje eu vou te mostrar como resolver.", 0.5),
    ])
    opcoes = ganchos.sugerir_ganchos(palavras)
    assert len(opcoes) == 2
    assert opcoes[0] == "Você comete esse erro no seu vídeo?"
    assert all("reais" not in o for o in opcoes)
    assert all(len(o.split()) <= 8 for o in opcoes)


@pytest.mark.parametrize("frase,motivo", [
    ("Ganhe 5 mil reais por mês com isso.", "valor em dinheiro"),
    ("Faturei R$ 10 mil no primeiro mês.", "valor em dinheiro"),
    ("Resultado em 7 dias.", "prazo"),
    ("É garantido.", "garantido"),
    ("Uma renda extra de verdade.", "renda extra"),
    ("Você vai ficar rico.", "rico"),
    ("Tudo sem esforço.", "esforço"),
    ("Você que ganha pouco precisa ver isso.", "característica"),
])
def test_meta_reprova(frase, motivo):
    alertas = meta.conferir_fala(falas([(frase, 0.5)]))
    assert alertas and motivo in alertas[0].motivo


def test_meta_aprova_fala_normal():
    assert meta.conferir_fala(falas([("Hoje eu vou te mostrar três erros de edição.", 0.5)])) == []
    assert meta.conferir_fala([], {"gancho": "Seu vídeo garantido"})[0].trecho.startswith("gancho")


def test_texto_sobe_quando_o_rosto_esta_embaixo():
    rosto = Rosto(0, 340, 1000, 400, 450)  # boca perto de y 1430
    y = posicao_vertical(230, [rosto])
    assert y + 115 <= rosto.zona_proibida()[0]
    assert y - 115 >= ZONA_SEGURA[1]
    assert posicao_vertical(230, []) == 1180


def test_sons_respeitam_distancia_minima():
    sons = [Som(1.0, "pop"), Som(1.3, "impacto", True), Som(2.0, "pop"), Som(2.5, "ding"), Som(99, "pop")]
    agenda = agendar(sons, 10)
    assert [s.nome for s in agenda] == ["impacto", "pop", "ding"] or all(
        b.tempo - a.tempo >= DISTANCIA_MINIMA for a, b in zip(agenda, agenda[1:]))
    assert any(s.nome == "impacto" for s in agenda)  # forte tem preferência
    assert all(b.tempo - a.tempo >= DISTANCIA_MINIMA for a, b in zip(agenda, agenda[1:]))
    assert all(s.tempo < 10 for s in agenda)
