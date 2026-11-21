"""Wersje metodyki sugestii i mapowania 5→3: nowa wersja, zatwierdzenie, przypięcie do oceny.

Scenariusz zmienia aktywną metodykę, więc działa na osobnej aplikacji i bazie.
"""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje

PRZYKLAD = [{"sytuacja": "S", "dzialanie": "D", "rezultat": "R"}]
MAPOWANIE_2 = {"1": 3, "3": 3, "5": 5, "7": 5, "9": 7}


@pytest.fixture(scope="module")
def app_m(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("metodyka")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "m.db", log_llm=dane / "l.jsonl"))) as k:
        yield k


def _h(klient, login):
    r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _ocena_pierwsza(klient, osoba_id, login, poziom):
    """Proces pierwszej oceny do kroku 3: oba wskaźniki pierwszego kryterium na `poziom`."""
    h = _h(klient, login)
    proces = klient.post("/api/procesy", json={"osoba_id": osoba_id, "sciezka": "pierwsza"}, headers=h).json()
    url = f"/api/procesy/{proces['id']}"
    p = klient.get(f"{url}/krok2", headers=h).json()
    wsk = {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:2]]
           for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
    assert klient.put(f"{url}/krok2", json={"wskazniki": wsk}, headers=h).status_code == 200
    stan = klient.get(f"{url}/ocena", headers=h).json()
    w1, w2 = (w["wskaznik_id"] for w in stan["kryteria"][0]["wskazniki"])
    r = klient.put(f"{url}/ocena/wskazniki", headers=h, json={"wskazniki": {
        w1: {"poziom": poziom, "przyklady": PRZYKLAD}, w2: {"poziom": poziom, "przyklady": PRZYKLAD}}})
    assert r.status_code == 200, r.text
    return url, h


def test_zmiana_metodyki_tworzy_wersje_a_ocena_zapisuje_uzyta(app_m):
    hr = _h(app_m, "hr")
    stan = app_m.get("/api/metodyka", headers=hr).json()
    assert stan["aktywna"] == "sugestia-mc-1"
    assert stan["wersje"][0]["status"] == "PROJEKT"

    # Ocena A rozpoczęta według pierwszej metodyki: 7 → 7 pkt.
    url_a, h_a = _ocena_pierwsza(app_m, "P-203", "przelozony1", 7)
    a = app_m.get(f"{url_a}/ocena", headers=h_a).json()
    assert a["metodyka"]["id"] == "sugestia-mc-1"
    assert a["kryteria"][0]["sugestia"]["punkty"] == 7

    # Zmiana mapowania tworzy NOWĄ wersję; projekt nie trafia do ocen.
    r = app_m.post("/api/metodyka", headers=hr, json={
        "minimalny_udzial_ocenionych": 0.5, "mapowanie_pierwsza": MAPOWANIE_2,
        "zmiana": "Mentor MC: poziom 7 modelu to w pierwszej ocenie „na poziomie oczekiwań”."})
    assert r.status_code == 200, r.text
    assert (r.json()["id"], r.json()["status"]) == ("sugestia-mc-2", "PROJEKT")
    assert app_m.get("/api/metodyka", headers=hr).json()["aktywna"] == "sugestia-mc-1"

    # Zatwierdzenie z osobą i datą.
    r = app_m.post("/api/metodyka/sugestia-mc-2/zatwierdz", headers=hr,
                   json={"osoba": "Anna Kowalska (mentor MC)", "dzien": "2026-11-21"})
    assert r.status_code == 200, r.text
    w2 = r.json()
    assert (w2["status"], w2["zatwierdzil"], w2["data_zatwierdzenia"]) == (
        "ZATWIERDZONA", "Anna Kowalska (mentor MC)", "2026-11-21")
    assert app_m.post("/api/metodyka/sugestia-mc-2/zatwierdz", headers=hr, json={}).status_code == 409

    # Ocena A nadal liczy według wersji, którą przypięła.
    a = app_m.get(f"{url_a}/ocena", headers=h_a).json()
    assert a["metodyka"]["id"] == "sugestia-mc-1"
    assert a["kryteria"][0]["sugestia"]["punkty"] == 7

    # Nowa ocena B dostaje zatwierdzoną wersję 2: 7 → 5 pkt, etykieta z osobą i datą.
    url_b, h_b = _ocena_pierwsza(app_m, "P-201", "przelozony2", 7)
    b = app_m.get(f"{url_b}/ocena", headers=h_b).json()
    assert b["metodyka"]["id"] == "sugestia-mc-2"
    assert b["kryteria"][0]["sugestia"]["punkty"] == 5
    assert "Anna Kowalska (mentor MC), 2026-11-21" in b["metodyka"]["status"]


def test_kolejne_zatwierdzenie_zastepuje_poprzednie(app_m):
    hr = _h(app_m, "hr")
    nowa = app_m.post("/api/metodyka", headers=hr, json={
        "minimalny_udzial_ocenionych": 0.6, "mapowanie_pierwsza": MAPOWANIE_2, "zmiana": "wyższy próg"}).json()
    app_m.post(f"/api/metodyka/{nowa['id']}/zatwierdz", headers=hr, json={"dzien": "2026-11-22"})
    stan = app_m.get("/api/metodyka", headers=hr).json()
    statusy = {w["id"]: w["status"] for w in stan["wersje"]}
    assert stan["aktywna"] == nowa["id"]
    assert statusy["sugestia-mc-2"] == "ZASTĄPIONA" and statusy[nowa["id"]] == "ZATWIERDZONA"
    assert next(w for w in stan["wersje"] if w["id"] == nowa["id"])["zatwierdzil"] == "hr"


@pytest.mark.parametrize("mapowanie, kod", [
    ({"1": 1, "3": 3, "5": 5, "7": 7, "9": 9}, 422),   # 1 i 9 spoza skali 3/5/7
    ({"1": 3, "5": 5, "9": 7}, 422),                   # brak poziomów 3 i 7
])
def test_niepoprawne_mapowanie(app_m, mapowanie, kod):
    r = app_m.post("/api/metodyka", headers=_h(app_m, "hr"), json={
        "minimalny_udzial_ocenionych": 0.5, "mapowanie_pierwsza": mapowanie, "zmiana": "test"})
    assert r.status_code == kod


@pytest.mark.parametrize("login", ["przelozony1", "oceniany"])
def test_tylko_hr_zarzadza_metodyka(app_m, login):
    h = _h(app_m, login)
    assert app_m.get("/api/metodyka", headers=h).status_code == 200
    r = app_m.post("/api/metodyka", headers=h, json={
        "minimalny_udzial_ocenionych": 0.5, "mapowanie_pierwsza": MAPOWANIE_2, "zmiana": "x"})
    assert r.status_code == 403
    assert app_m.post("/api/metodyka/sugestia-mc-1/zatwierdz", headers=h, json={}).status_code == 403
