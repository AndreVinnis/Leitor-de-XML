"""Teto de tamanho do corpo (app/core/limite_corpo.py), aplicado antes de
qualquer rota -- inclusive antes da autenticação e do parse do multipart."""
from app.core.config import settings


def test_content_length_acima_do_teto_e_recusado_sem_autenticar(client, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_bytes_por_lote", 0)

    resposta = client.post(
        "/api/notas/upload",
        content=b"x" * (2 * 1024 * 1024),
        headers={"content-type": "multipart/form-data; boundary=abc"},
    )

    assert resposta.status_code == 413
    assert "maior que o permitido" in resposta.json()["detail"]


def test_corpo_sem_content_length_e_cortado_ao_passar_do_teto(client, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_bytes_por_lote", 0)

    def gerador():
        for _ in range(4):
            yield b"x" * (1024 * 1024)

    resposta = client.post(
        "/api/notas/upload",
        content=gerador(),
        headers={"content-type": "multipart/form-data; boundary=abc"},
    )

    assert resposta.status_code == 413


def test_corpo_dentro_do_teto_segue_normal(client):
    # Sem login: passa pelo teto e chega na autenticação (401).
    resposta = client.post("/api/consulta", json={"pergunta": "x", "cliente_caso_id": 1})
    assert resposta.status_code == 401
