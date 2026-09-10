"""
CORS existe só para o frontend React (web/), que roda no browser do host e
chama a API por fetch -- o Streamlit nunca precisou disso porque chama a API
do lado do servidor com `requests`. Ver app/main.py e app/core/config.py
(cors_origins).
"""


def test_preflight_de_origem_permitida_recebe_cabecalho_cors(client):
    resp = client.options(
        "/api/casos",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_de_origem_nao_autorizada_nao_recebe_cabecalho_cors(client):
    resp = client.options(
        "/api/casos",
        headers={
            "Origin": "http://site-desconhecido.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in resp.headers
