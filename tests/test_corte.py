from edit_ia_pro import corte
from edit_ia_pro.transcricao import Palavra

from .conftest import falas


def test_normalizar_tira_acento_e_pontuacao():
    assert corte.normalizar("Três, É!") == "tres e"


def test_tomada_repetida_fica_a_ultima_completa(roteiro):
    plano = corte.planejar(roteiro, roteiro[-1].fim + 0.8)
    textos = [p.texto for p in plano.palavras_mantidas]
    assert textos[:6] == ["Hoje", "eu", "vou", "te", "mostrar", "três"]
    assert textos.count("Hoje") == 1
    assert plano.frases_repetidas == 1


def test_frase_abandonada_mesmo_com_tres_tomadas():
    palavras = falas([
        ("Esse é o melhor jeito de", 0.8),
        ("Esse é o melhor jeito de editar.", 0.8),
        ("Esse é o melhor jeito de editar vídeo.", 0.8),
        ("Tchau.", 0.5),
    ])
    plano = corte.planejar(palavras, palavras[-1].fim + 1)
    textos = " ".join(p.texto for p in plano.palavras_mantidas)
    assert textos == "Esse é o melhor jeito de editar vídeo. Tchau."
    assert "terceira tomada" in plano.resumo()


def test_ultima_tomada_abandonada_fica_a_completa_anterior():
    palavras = falas([("Vou te contar um segredo.", 0.8), ("Vou te contar um", 0.8), ("Fim.", 0.5)])
    plano = corte.planejar(palavras, palavras[-1].fim + 1)
    assert " ".join(p.texto for p in plano.palavras_mantidas) == "Vou te contar um segredo. Fim."


def test_frases_diferentes_nao_sao_tomadas():
    palavras = falas([("Hoje eu vou falar de legenda.", 0.8), ("Amanhã eu falo de som.", 0.5)])
    plano = corte.planejar(palavras, palavras[-1].fim + 1)
    assert plano.frases_repetidas == 0
    assert len(plano.palavras_mantidas) == len(palavras)


def test_vicios_saem():
    palavras = falas([("Então éé hum a ideia é simples.", 0.5), ("Tipo assim, funciona.", 0.5)])
    plano = corte.planejar(palavras, palavras[-1].fim + 1)
    textos = [p.texto for p in plano.palavras_mantidas]
    assert "éé" not in textos and "hum" not in textos
    assert "Tipo" not in textos and "assim," not in textos
    assert "é" in textos  # o verbo "é" fica


def test_pausas_saem_e_bordas_nao_entram_na_vizinha():
    palavras = [Palavra("um.", 1.0, 1.3), Palavra("dois", 1.35, 1.6), Palavra("três", 2.5, 2.8), Palavra("quatro", 2.86, 3.1)]
    trechos, pausas = corte.montar_trechos(palavras, [0, 1, 2, 3], 4.0)
    assert pausas == 1
    assert len(trechos) == 2
    a, b = trechos
    assert a.inicio == 0.94 and a.fim == 1.70
    assert b.inicio == 2.44 and b.fim == 3.2
    # folga nunca entra na palavra vizinha removida
    trechos, _ = corte.montar_trechos(palavras, [0, 2], 4.0)
    assert trechos[0].fim <= palavras[1].inicio
    assert trechos[1].inicio >= palavras[1].fim


def test_nunca_corta_no_meio_da_palavra(roteiro):
    plano = corte.planejar(roteiro, roteiro[-1].fim + 0.8)
    for p in plano.palavras_mantidas:
        assert any(t.inicio <= p.inicio and p.fim <= t.fim for t in plano.trechos)


def test_silencedetect_confirma_pausa_escondida():
    palavras = [Palavra("a", 0.0, 0.5), Palavra("b", 0.55, 2.0)]  # "b" esticada pelo whisper
    trechos, _ = corte.montar_trechos(palavras, [0, 1], 2.5, silencios=[(0.5, 1.4)])
    assert len(trechos) == 2


def test_palavra_longa_vira_suspeita():
    palavras = [Palavra("isso", 0.0, 0.3), Palavra("aqui", 0.4, 1.9)]
    plano = corte.planejar(palavras, 2.0)
    assert plano.suspeitas and "confere" in plano.resumo()


def test_resumo_em_tres_linhas(roteiro):
    plano = corte.planejar(roteiro, roteiro[-1].fim + 0.8)
    linhas = plano.resumo().splitlines()
    assert len(linhas) <= 3
    assert linhas[0].startswith("tirei ") and "pausas" in linhas[0]
    assert "o vídeo foi de" in linhas[1]
    assert plano.duracao_final < plano.duracao_original


def test_mapear_tempos_e_emendas():
    trechos = [corte.Trecho(1.0, 2.0), corte.Trecho(3.0, 4.5)]
    assert corte.mapear_para_corte(trechos, 3.5) == 1.5
    assert corte.mapear_para_corte(trechos, 2.5) is None
    assert corte.mapear_para_original(trechos, 1.5) == 3.5
    assert corte.emendas(trechos) == [1.0]


def test_remover_intervalo_pedido_pela_pessoa():
    trechos = [corte.Trecho(0.0, 4.0), corte.Trecho(6.0, 10.0)]
    novos = corte.remover_intervalo(trechos, 3.0, 5.0)  # tempos do vídeo cortado
    assert [(t.inicio, t.fim) for t in novos] == [(0.0, 3.0), (7.0, 10.0)]
