import pytest
from PIL import Image

from edit_ia_pro import ZONA_SEGURA, corte, motion
from edit_ia_pro.rosto import Rosto

from .conftest import falas


def _no_corte(palavras):
    plano = corte.planejar(palavras, palavras[-1].fim + 1)
    return corte.palavras_no_corte(palavras, plano.trechos)


def test_detecta_os_momentos_do_roteiro(roteiro):
    palavras = _no_corte(roteiro)
    tipos = {m.tipo: m for m in motion.detectar_candidatos(palavras)}
    assert [i["texto"] for i in tipos["lista"].dados["itens"]] == ["Não cortar pausas", "Legenda pequena", "Sem gancho"]
    assert tipos["numero"].dados == {"texto": "5", "rotulo": "MINUTOS"}
    assert tipos["carimbo"].dados["texto"] == "PRONTO"
    assert tipos["impacto"].dados["texto"] == "ACABOU"
    assert tipos["comentario"].dados["texto"] == "EDIT"


def test_segundo_como_tempo_nao_vira_lista():
    palavras = falas([("Espera 5 segundos.", 0.5), ("Primeiro, abre o app.", 0.5)])
    tipos = [m.tipo for m in motion.detectar_candidatos(palavras)]
    assert "lista" not in tipos


def test_numero_de_dinheiro_nao_anima():
    palavras = falas([("Isso custa 50 reais.", 0.5)])
    assert not [m for m in motion.detectar_candidatos(palavras) if m.tipo == "numero"]


def test_passo_a_passo():
    palavras = falas([("Passo 1 abre o app.", 0.5), ("Passo 2 grava o vídeo.", 0.5)])
    m = next(m for m in motion.detectar_candidatos(palavras) if m.tipo == "passo")
    assert [e["numero"] for e in m.dados["etapas"]] == [1, 2]
    assert m.dados["etapas"][0]["nome"] == "ABRE O APP"


def test_regras_de_escolha(roteiro):
    palavras = _no_corte(roteiro)
    candidatos = motion.detectar_candidatos(palavras)
    assert motion.escolher(candidatos, "nenhuma") == []
    medias = motion.escolher(candidatos, "medias", fim_gancho=2.8)
    poucas = motion.escolher(candidatos, "poucas", fim_gancho=2.8)
    assert len(poucas) <= len(medias)
    for lista in (medias, poucas):
        assert all(m.inicio >= 2.8 for m in lista)
        for a, b in zip(lista, lista[1:]):
            assert a.fim <= b.inicio  # uma animação por vez
    nao_cta = [m for m in poucas if m.tipo != "comentario"]
    assert all(b.inicio - a.inicio >= 10 for a, b in zip(nao_cta, nao_cta[1:]))
    assert any(m.tipo == "comentario" for m in medias)


def test_contagem_mantem_formato():
    assert motion.formatar_contagem("05", 0.0) == "00"
    assert motion.formatar_contagem("05", 1.0) == "05"
    assert motion.formatar_contagem("50%", 0.5) == "25%"
    assert motion.formatar_contagem("2,5", 1.0) == "2,5"


@pytest.mark.parametrize("tipo,dados", [
    ("impacto", {"texto": "SEM EDITOR"}),
    ("lista", {"itens": [{"texto": "Um", "t": 1.0}, {"texto": "Dois", "t": 1.6}, {"texto": "Três", "t": 2.2}]}),
    ("passo", {"etapas": [{"numero": 1, "nome": "GRAVAR", "t": 1.0}, {"numero": 2, "nome": "EDITAR", "t": 2.0}]}),
    ("numero", {"texto": "5", "rotulo": "MINUTOS"}),
    ("notificacao", {"titulo": "Nova mensagem", "texto": "Chegou mais um pedido pra você"}),
    ("carimbo", {"texto": "APROVADO"}),
    ("destaque", {"texto": "OLHA ISSO"}),
    ("comentario", {"texto": "EDIT"}),
    ("barra", {"texto": "O DOBRO"}),
])
def test_cada_receita_desenha(tipo, dados):
    m = motion.Momento(tipo, 1.0, 3.6, dados)
    meio_entrada = motion.quadro(m, 0.15, "#FFC400") if tipo != "notificacao" else motion._quadro_notificacao(m, 0.15, "#FFC400", motion.tamanho_render(m))
    parado = motion.quadro(m, 1.5, "#FFC400") if tipo != "notificacao" else motion._quadro_notificacao(m, 1.5, "#FFC400", motion.tamanho_render(m))
    assert parado.getchannel("A").getbbox() is not None
    assert parado.size == motion.tamanho_render(m)
    assert isinstance(meio_entrada, Image.Image)
    # posicionado dentro da zona segura (com folga do destaque) e fora do rosto
    rosto = Rosto(1.5, 340, 900, 400, 450)
    pos = motion.posicionar(m, [rosto])
    x0, y0, x1, y1 = motion.caixa_na_tela(m, pos)
    assert y0 >= ZONA_SEGURA[1] and y1 <= ZONA_SEGURA[3]
    if tipo != "destaque":
        assert y1 <= rosto.zona_proibida()[0] or y0 >= rosto.zona_proibida()[1]


def test_saida_some_no_fim():
    m = motion.Momento("impacto", 0.0, 1.5, {"texto": "ACABOU"})
    ultimo = motion.quadro(m, 1.5 - 1 / 30 / 4, "#FFC400")
    assert ultimo.getchannel("A").getextrema()[1] < 40


def test_sons_das_animacoes():
    m = motion.Momento("lista", 2.0, 6.0, {"itens": [{"texto": "a", "t": 2.1}, {"texto": "b", "t": 3.0}]})
    assert [n for _, n, _ in motion.sons_do_momento(m)] == ["pop", "pop"]
    assert motion.sons_do_momento(motion.Momento("carimbo", 1, 2, {"texto": "X"}))[0][2] is True


def test_rotulo_do_numero_com_por():
    palavras = falas([("Faço 3 vídeos por dia.", 0.5)])
    m = next(m for m in motion.detectar_candidatos(palavras) if m.tipo == "numero")
    assert m.dados == {"texto": "3", "rotulo": "VÍDEOS POR DIA"}


def test_sem_animacao_durante_tela_dividida(roteiro):
    palavras = _no_corte(roteiro)
    escolhidos = motion.sugerir_momentos(palavras, "medias", 2.8, bloqueios=[(4.0, 7.0)])
    assert all(m.fim <= 4.0 or m.inicio >= 7.0 for m in escolhidos)
