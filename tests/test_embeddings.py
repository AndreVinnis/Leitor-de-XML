from app.ai.embeddings import selecionar_candidatos_similares


def test_selecionar_candidatos_similares_devolve_mais_proximo_primeiro():
    embeddings_canonicos = {
        1: [1.0, 0.0],
        2: [0.0, 1.0],
        3: [0.9, 0.1],
    }
    embeddings_descricoes = {"chave-a": [1.0, 0.0]}

    ids = selecionar_candidatos_similares(
        ["chave-a"], embeddings_descricoes, embeddings_canonicos, top_k=2, max_total=10
    )

    assert ids[0] == 1  # idêntico ao vetor da descrição -- fica em primeiro
    assert 2 not in ids  # ortogonal ao vetor da descrição -- fora do top 2
    assert len(ids) == 2


def test_selecionar_candidatos_similares_une_top_k_de_varias_descricoes_sem_duplicar():
    embeddings_canonicos = {1: [1.0, 0.0], 2: [0.0, 1.0]}
    embeddings_descricoes = {
        "a": [1.0, 0.0],
        "b": [1.0, 0.0],  # mesma direção de "a" -- não deve duplicar o id 1
        "c": [0.0, 1.0],
    }

    ids = selecionar_candidatos_similares(
        ["a", "b", "c"], embeddings_descricoes, embeddings_canonicos, top_k=1, max_total=10
    )

    assert ids == [1, 2]


def test_selecionar_candidatos_similares_respeita_max_total():
    embeddings_canonicos = {i: [float(i), 1.0] for i in range(5)}
    embeddings_descricoes = {"a": [0.0, 1.0]}

    ids = selecionar_candidatos_similares(
        ["a"], embeddings_descricoes, embeddings_canonicos, top_k=5, max_total=2
    )

    assert len(ids) == 2


def test_selecionar_candidatos_similares_sem_canonicos_devolve_vazio():
    assert (
        selecionar_candidatos_similares(["x"], {"x": [1.0]}, {}, top_k=5, max_total=10) == []
    )


def test_selecionar_candidatos_similares_ignora_descricao_sem_embedding():
    embeddings_canonicos = {1: [1.0, 0.0]}

    ids = selecionar_candidatos_similares(
        ["sem-embedding"], {}, embeddings_canonicos, top_k=5, max_total=10
    )

    assert ids == []
