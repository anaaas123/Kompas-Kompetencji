"""Stan pokazu (#57): skrypt na świeżej aplikacji daje sugestię przy każdym kryterium, rozbieżność samooceny,
jeden pusty wskaźnik i cele; drugie uruchomienie nic nie zmienia."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from kompas_mc.app import utworz_aplikacje
from kompas_mc.stan_demo import przygotuj


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("demo")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "d.db", log_llm=dane / "l.jsonl"))) as k:
        yield k


def _wywolanie(k: TestClient):
    def wywolaj(metoda: str, sciezka: str, token: str | None = None, dane: object = None):
        r = k.request(metoda, sciezka, json=dane, headers={"Authorization": f"Bearer {token}"} if token else {})
        return r.status_code, (r.json() if r.content else None)

    return wywolaj


def test_stan_demo_raz_i_bez_dublowania(klient):
    opis = przygotuj(_wywolanie(klient))
    assert opis.startswith("Gotowe")
    h = {"Authorization": f"Bearer {klient.post('/api/auth/login', json={'login': 'przelozony1', 'hasło': 'demo'}).json()['token']}"}
    pid = next(p["id"] for p in klient.get("/api/procesy", headers=h).json() if p["osoba_id"] == "P-101")
    ocena = klient.get(f"/api/procesy/{pid}/ocena", headers=h).json()
    assert all(kr["sugestia"]["status"] != "NIEWYSTARCZAJACE_DANE" for kr in ocena["kryteria"]), "sugestia przy każdym kryterium"
    wskazniki = [w for kr in ocena["kryteria"] for w in kr["wskazniki"]]
    assert sum(1 for w in wskazniki if w.get("ocena") is None) >= 1, "jeden wskaźnik pusty do kliknięcia na żywo"
    assert ocena["samoocena_status"] == "przekazana"
    assert any(
        w.get("samoocena") and w.get("ocena") and w["ocena"].get("poziom") and abs(w["samoocena"]["poziom"] - w["ocena"]["poziom"]) >= 4
        for w in wskazniki
    ), "rozbieżność samooceny co najmniej 4"
    cele = klient.get("/api/pracownicy/P-101/cele", headers=h).json()["cele"]
    assert {c["status"] for c in cele} == {"zatwierdzony", "propozycja"}

    liczba_procesow = len(klient.get("/api/procesy", headers=h).json())
    assert przygotuj(_wywolanie(klient)).startswith("Stan demo już jest")
    assert len(klient.get("/api/procesy", headers=h).json()) == liczba_procesow
    assert len(klient.get("/api/pracownicy/P-101/cele", headers=h).json()["cele"]) == len(cele)
