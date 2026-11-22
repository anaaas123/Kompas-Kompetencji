"""Helix G3 (22.11, #114): zapis oceny po zakończeniu procesu i decyzje sprzed zmiany kryteriów.

Własna baza (nie wspólna z resztą testów), bo testy zmieniają status procesu i unieważniają decyzje.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import kompas_mc.ocena_api as ocena_api
from kompas_mc.app import utworz_aplikacje


@pytest.fixture
def osobny(ustawienia, tmp_path):
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=tmp_path / "helix.db"))) as kl:
        h = {"Authorization": f"Bearer {kl.post('/api/auth/login', json={'login': 'przelozony2', 'hasło': 'demo'}).json()['token']}"}
        r = kl.post("/api/procesy", json={"osoba_id": "P-103", "sciezka": "okresowa"}, headers=h)
        assert r.status_code == 201, r.text
        proces = r.json()
        p = kl.get(f"/api/procesy/{proces['id']}/krok2", headers=h).json()
        body = {"wskazniki": {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:1]] for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}}
        assert kl.put(f"/api/procesy/{proces['id']}/krok2", json=body, headers=h).status_code == 200
        yield kl, h, proces["id"], body


def _wszystkie_decyzje(kl, h, pid, punkty):
    url = f"/api/procesy/{pid}/ocena"
    for kr in kl.get(url, headers=h).json()["kryteria"]:
        assert kl.put(f"{url}/decyzje", json={"decyzje": {kr["kompetencja_id"]: {"punkty": punkty}}}, headers=h).status_code == 200


def test_spozniony_zapis_po_zakonczeniu_procesu_daje_409(osobny, monkeypatch):
    """Zapis przeszedł kontrolę W_TOKU, a proces zakończył się przed UPDATE: 409 i punkty bez zmian."""
    kl, h, pid, _ = osobny
    _wszystkie_decyzje(kl, h, pid, 7)
    baza = kl.app.state.baza
    with baza:
        baza.execute("UPDATE procesy SET status = 'ZAKONCZONY' WHERE id = ?", (pid,))
    # Odczyt sprzed zakończenia: proces widziany jeszcze jako W_TOKU.
    oryginal = ocena_api.wczytaj_proces
    monkeypatch.setattr(ocena_api, "wczytaj_proces", lambda b, i: oryginal(b, i).model_copy(update={"status": "W_TOKU"}))
    kr = kl.get(f"/api/procesy/{pid}/ocena", headers=h).json()["kryteria"][0]["kompetencja_id"]
    r = kl.put(f"/api/procesy/{pid}/ocena/decyzje", json={"decyzje": {kr: {"punkty": 1}}}, headers=h)
    assert r.status_code == 409, r.text
    monkeypatch.setattr(ocena_api, "wczytaj_proces", oryginal)
    with baza:
        baza.execute("UPDATE procesy SET status = 'W_TOKU' WHERE id = ?", (pid,))
    stan = kl.get(f"/api/procesy/{pid}/ocena", headers=h).json()
    assert {k["decyzja"]["punkty"] for k in stan["kryteria"]} == {7}


def test_po_ponownym_zapisie_kryteriow_stare_decyzje_nie_licza_sie(osobny):
    """Ekran oceny i wynik mówią to samo: decyzje sprzed nowego zapisu kryteriów nie są kompletne."""
    kl, h, pid, body = osobny
    _wszystkie_decyzje(kl, h, pid, 5)
    url = f"/api/procesy/{pid}/ocena"
    k = kl.get(url, headers=h).json()["kompletnosc"]
    assert k["kryteria_z_decyzja"] == k["kryteria"] > 0
    assert kl.get(f"/api/procesy/{pid}", headers=h).json()["krok"] == 5
    assert kl.put(f"/api/procesy/{pid}/krok2", json=body, headers=h).status_code == 200
    stan = kl.get(url, headers=h).json()
    assert stan["kompletnosc"]["kryteria_z_decyzja"] == 0
    assert all(k["decyzja"] is None for k in stan["kryteria"])
    assert kl.get(f"/api/procesy/{pid}", headers=h).json()["krok"] == 3
