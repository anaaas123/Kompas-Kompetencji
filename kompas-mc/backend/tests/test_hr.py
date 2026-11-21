"""Panel HR (#38): terminy, filtr zagrożonych, przypomnienia w skrzynce i historii, bez treści ocen."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje
from kompas_mc.hr import Termin

DZIS = date(2026, 11, 21)


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("hr")
    ust = replace(ustawienia, baza=dane / "hr.db", log_llm=dane / "llm.jsonl")
    with TestClient(utworz_aplikacje(ust)) as k:
        k.app.state.dzis = lambda: DZIS
        yield k


@pytest.fixture(scope="module")
def h(klient):
    def zaloguj(login: str) -> dict:
        r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


@pytest.fixture(scope="module")
def procesy(klient, h):
    """P-101 (termin za 3 dni → zagrożony), P-102 (za 20 dni), P-202 (bez terminu)."""
    ids = {}
    for login, osoba, sciezka in [
        ("przelozony1", "P-101", "okresowa"),
        ("przelozony2", "P-102", "okresowa"),
        ("przelozony1", "P-202", "pierwsza"),
    ]:
        r = klient.post("/api/procesy", json={"osoba_id": osoba, "sciezka": sciezka}, headers=h(login))
        assert r.status_code == 201, r.text
        ids[osoba] = r.json()["id"]
    za = {ids["P-101"]: 3, ids["P-102"]: 20}
    klient.app.state.terminy = lambda proces, p, dzis: (
        [Termin(nazwa="sporządzenie oceny na piśmie", data=dzis + timedelta(days=za[proces.id]))]
        if proces.id in za else []
    )
    # notatka przełożonego, której HR nie może zobaczyć
    klient.post("/api/pracownicy/P-101/notatki", json={"tresc": "TAJNA NOTATKA"}, headers=h("przelozony1"))
    return ids


def test_lista_procesow_z_terminem_i_krokiem(klient, h, procesy):
    r = klient.get("/api/hr/procesy", headers=h("hr"))
    assert r.status_code == 200
    w = {x["osoba_id"]: x for x in r.json()}
    assert set(procesy) <= set(w)
    a = w["P-101"]
    assert a["sciezka"] == "okresowa" and a["arkusz"] in {"B", "C"} and a["krok"] >= 1 and a["status"] == "W_TOKU"
    assert a["najblizszy_termin"]["data"] == (DZIS + timedelta(days=3)).isoformat() and a["dni_do_terminu"] == 3
    assert w["P-202"]["najblizszy_termin"] is None and "Brak terminu" in w["P-202"]["komunikat"]


def test_termin_w_ciagu_7_dni_w_filtrze_zagrozonych(klient, h, procesy):
    zagrozone = klient.get("/api/hr/procesy?zagrozone=true", headers=h("hr")).json()
    osoby = {x["osoba_id"] for x in zagrozone}
    assert "P-101" in osoby and "P-102" not in osoby and "P-202" not in osoby
    assert all(x["zagrozony"] for x in zagrozone)


def test_propozycja_przypomnienia_dla_zagrozonego(klient, h, procesy):
    prop = klient.get("/api/hr/przypomnienia/propozycje", headers=h("hr")).json()
    assert [p["proces_id"] for p in prop] == [procesy["P-101"]]
    p = prop[0]
    assert p["adresat"] == "P-001" and "za 3 dni" in p["tresc"] and p["termin"]["nazwa"]


def test_wyslane_przypomnienie_w_skrzynce_i_historii(klient, h, procesy):
    pid = procesy["P-101"]
    tresc = klient.get("/api/hr/przypomnienia/propozycje", headers=h("hr")).json()[0]["tresc"]
    r = klient.post("/api/hr/przypomnienia", headers=h("hr"),
                    json={"proces_id": pid, "adresat": "P-001", "tresc": tresc})
    assert r.status_code == 201, r.text
    wyslane = r.json()
    assert wyslane["nadawca"] == "hr" and wyslane["wyslano"]

    skrzynka = klient.get(f"/api/hr/skrzynka?proces_id={pid}", headers=h("hr")).json()
    assert [s["id"] for s in skrzynka] == [wyslane["id"]]
    assert skrzynka[0]["tresc"] == tresc and skrzynka[0]["adresat"] == "P-001"

    historia = klient.app.state.dziennik.historia("proces", str(pid))
    assert any("przypomnienie" in str(w.roznica) and w.autor == "hr" for w in historia)


def test_hr_nie_widzi_tresci_ocen_ani_notatek(klient, h, procesy):
    tekst = klient.get("/api/hr/procesy", headers=h("hr")).text
    for zakazane in ("oceny_wskaznikow", "decyzje", "przyklady", "uzasadnienie", "krok1", "krok2", "TAJNA NOTATKA"):
        assert zakazane not in tekst, zakazane
    assert klient.get("/api/pracownicy/P-101/notatki", headers=h("hr")).status_code == 403


def test_uprawnienia_panelu(klient, h, procesy):
    for login in ("przelozony1", "oceniany"):
        assert klient.get("/api/hr/procesy", headers=h(login)).status_code == 403
        assert klient.post("/api/hr/przypomnienia", headers=h(login),
                           json={"proces_id": procesy["P-101"], "adresat": "P-001", "tresc": "x"}).status_code == 403
    assert klient.get("/api/hr/procesy").status_code == 401
    assert klient.post("/api/hr/przypomnienia", headers=h("hr"),
                       json={"proces_id": 999999, "adresat": "P-001", "tresc": "x"}).status_code == 404


def test_zakonczony_proces_nie_jest_zagrozony():
    from kompas_mc.hr import wiersz

    class P:
        osoba_id, imie, nazwisko, stanowisko, przelozony_id = "P-1", "A", "B", "radca", "P-0"

    class Proc:
        id, sciezka, arkusz, krok, status = 1, "okresowa", "C", 9, "ZAKONCZONY"

    w = wiersz(Proc, P, [Termin(nazwa="x", data=DZIS)], DZIS)
    assert w.zagrozony is False and w.dni_do_terminu == 0


def test_terminy_z_regul_oceny_okresowej(ustawienia, tmp_path_factory):
    """Reguły #32 na danych demo: P-102 po ocenie negatywnej 2026-11-16 → kryteria w 7 dni
    (2026-11-23) → zagrożony; P-101 (ostatnia ocena 2024-12-02) → ocena po 24 miesiącach."""
    dane = tmp_path_factory.mktemp("hr-reguly")
    ust = replace(ustawienia, baza=dane / "r.db", log_llm=dane / "l.jsonl")
    with TestClient(utworz_aplikacje(ust)) as k:
        k.app.state.dzis = lambda: DZIS
        tok = lambda l: {"Authorization": "Bearer " + k.post(  # noqa: E731
            "/api/auth/login", json={"login": l, "hasło": "demo"}).json()["token"]}
        assert k.post("/api/procesy", json={"osoba_id": "P-102", "sciezka": "okresowa"},
                      headers=tok("przelozony2")).status_code == 201
        assert k.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"},
                      headers=tok("przelozony1")).status_code == 201
        w = {x["osoba_id"]: x for x in k.get("/api/hr/procesy", headers=tok("hr")).json()}
    assert w["P-102"]["najblizszy_termin"]["data"] == "2026-11-23" and w["P-102"]["zagrozony"]
    assert w["P-101"]["najblizszy_termin"]["nazwa"] == "sporządzenie oceny na piśmie"
    assert w["P-101"]["najblizszy_termin"]["data"] >= "2026-12-02" and not w["P-101"]["zagrozony"]
