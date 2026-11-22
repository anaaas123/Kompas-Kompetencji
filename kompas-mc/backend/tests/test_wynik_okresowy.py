"""Odbiór HTTP kroku 6 od założenia procesu do zapisu wyniku i zawiadomienia."""

from dataclasses import replace
from decimal import Decimal
from functools import cache
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from kompas_core.pdf import znajdz_font
from pypdf import PdfReader

from kompas_mc.app import utworz_aplikacje


@pytest.fixture(scope="module")
def api_wyniku(ustawienia, tmp_path_factory):
    katalog = tmp_path_factory.mktemp("wynik-okresowy")
    ustawienia = replace(ustawienia, baza=katalog / "oceny.db", log_llm=katalog / "llm.jsonl")
    with TestClient(utworz_aplikacje(ustawienia)) as klient:
        @cache
        def naglowek(login):
            r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
            return {"Authorization": f"Bearer {_json(r)['token']}"}

        yield klient, naglowek


def _json(odpowiedz, status=200):
    assert odpowiedz.status_code == status, odpowiedz.text
    return odpowiedz.json()


def _przygotuj_proces(klient, h, osoba_id):
    proces = _json(
        klient.post("/api/procesy", headers=h, json={"osoba_id": osoba_id, "sciezka": "okresowa"}), 201
    )
    url = f"/api/procesy/{proces['id']}"
    kryteria = _json(klient.get(f"{url}/krok2", headers=h))["kryteria"]
    wskazniki = {
        k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]]
        for k in kryteria if k["rodzaj"] == "OBOWIAZKOWE"
    }
    _json(klient.put(f"{url}/krok2", headers=h, json={"wskazniki": wskazniki}))
    return url, list(wskazniki)


def _zapisz_punkty(klient, h, url, kryteria, punkty):
    decyzje = {
        k: {"punkty": p, "uzasadnienie": "Ocena na podstawie wykonanych zadań."}
        for k, p in zip(kryteria, punkty, strict=True)
    }
    _json(klient.put(f"{url}/ocena/decyzje", headers=h, json={"decyzje": decyzje}))


def test_wynik_ze_zatwierdzonych_ocen_i_ponowny_zapis_po_zmianie_punktow(api_wyniku):
    klient, naglowek = api_wyniku
    h = naglowek("przelozony1")
    proces, kryteria = _przygotuj_proces(klient, h, "P-101")
    url = f"{proces}/wynik-okresowy"
    assert klient.get(url, headers=h).status_code == 409

    _zapisz_punkty(klient, h, proces, kryteria, (1, 7, 7, 9, 9))
    podglad = _json(klient.get(url, headers=h))
    obliczenie = podglad["obliczenie"]
    assert Decimal(str(obliczenie["srednia"])) == Decimal("6.6")
    assert obliczenie["poziom"] == "powyżej oczekiwań"
    assert obliczenie["wynik"] == "negatywna"
    regula = obliczenie["regula_rozstrzygajaca"]
    assert regula["id"] == "negatywna-za-ocene-czastkowa"
    assert regula["zrodlo"]["lokalizator"] == "§ 11 ust. 1 pkt 4"
    assert any(krok["regula"] == regula for krok in obliczenie["slad"])
    assert podglad["uzasadnienie_wymagane"] is True
    assert podglad["czesc_iii"]["dostepna"] is False
    assert podglad["zapisany"] is False
    # Kadry nie podają poziomu poprzedniej oceny: liczy się z jej ocen cząstkowych w aktach (7, 7, 5, 5, 3 → 5,4).
    assert podglad["poprzednia_ocena"] == {"data": "2024-12-02", "wynik": "pozytywna", "poziom": "na poziomie oczekiwań"}
    for dane in ({}, {"uzasadnienie": " \n "}, {"uzasadnienie": "Ocena negatywna", "dolacz_wniosek_o_stopien": True}):
        assert klient.put(url, headers=h, json=dane).status_code == 422

    zapis = _json(klient.put(url, headers=h, json={
        "uzasadnienie": "  Kryterium otrzymało najniższą ocenę cząstkową.  ",
        "poprzednia_ocena_poziom": "na poziomie oczekiwań",
        "data_sporzadzenia_oceny": "2026-11-19",
        "data_zapoznania_z_ocena": "2026-11-20",
    }))
    assert zapis["zapisany"] is True
    assert zapis["poprzednia_ocena"] == {
        "data": "2024-12-02", "wynik": "pozytywna", "poziom": "na poziomie oczekiwań",
    }
    assert zapis["terminy"]["termin_bazowy"]["data"] == "2026-12-02"
    sprzeciw = zapis["terminy"]["termin_sprzeciwu"]
    assert sprzeciw["data"] == "2026-11-27"
    assert sprzeciw["slad"][0]["regula"]["zrodlo"]["lokalizator"]
    assert _json(klient.get(url, headers=h))["dane"]["uzasadnienie"] == (
        "Kryterium otrzymało najniższą ocenę cząstkową."
    )
    assert _json(klient.get(proces, headers=h))["krok"] == 6

    _zapisz_punkty(klient, h, proces, kryteria[:1], (7,))
    aktualny = _json(klient.get(url, headers=h))
    assert aktualny["obliczenie"]["wynik"] == "pozytywna"
    assert aktualny["zapisany"] is False
    assert aktualny["dane"]["uzasadnienie"] is None
    assert aktualny["czesc_iii"]["dostepna"] is True
    assert aktualny["czesc_iii"]["dolaczana"] is False

    wniosek = _json(klient.put(url, headers=h, json={"dolacz_wniosek_o_stopien": True}))
    assert wniosek["zapisany"] is True
    assert wniosek["czesc_iii"]["dolaczana"] is True


def test_pozytywna_ocena_pracownika_bez_czesci_iii(api_wyniku):
    klient, naglowek = api_wyniku
    h = naglowek("przelozony2")
    proces, kryteria = _przygotuj_proces(klient, h, "P-102")
    _zapisz_punkty(klient, h, proces, kryteria, (5, 5, 5, 5, 5))
    url = f"{proces}/wynik-okresowy"
    wynik = _json(klient.put(url, headers=h, json={}))
    assert wynik["obliczenie"]["wynik"] == "pozytywna"
    assert wynik["poprzednia_ocena"] is None
    assert wynik["czesc_iii"]["dostepna"] is False
    assert wynik["terminy"]["termin_kryteriow"]["data"] == "2026-11-23"
    assert klient.put(url, headers=h, json={"dolacz_wniosek_o_stopien": True}).status_code == 422


def test_krok6_respektuje_uprawnienia_do_procesu(api_wyniku):
    klient, naglowek = api_wyniku
    h = naglowek("przelozony1")
    proces, kryteria = _przygotuj_proces(klient, h, "P-104")
    _zapisz_punkty(klient, h, proces, kryteria, (5, 5, 5, 5, 5))
    url = f"{proces}/wynik-okresowy"
    assert klient.get(url).status_code == 401
    assert klient.get(url, headers=naglowek("przelozony2")).status_code == 403
    assert klient.put(url, headers=naglowek("przelozony2"), json={}).status_code == 403
    assert klient.get(f"{url}/zawiadomienie.pdf", headers=naglowek("przelozony2")).status_code == 403
    assert klient.get(url, headers=naglowek("hr")).status_code == 403
    assert klient.get(f"{url}/zawiadomienie.pdf", headers=naglowek("hr")).status_code == 403
    assert klient.put(url, headers=naglowek("hr"), json={}).status_code == 403


def test_zawiadomienie_pdf_dopiero_po_zapisie_zmiany_terminu(api_wyniku):
    klient, naglowek = api_wyniku
    h = naglowek("przelozony2")
    proces, kryteria = _przygotuj_proces(klient, h, "P-103")
    _zapisz_punkty(klient, h, proces, kryteria, (5, 5, 5, 5, 5))
    url = f"{proces}/wynik-okresowy"
    assert klient.get(f"{url}/zawiadomienie.pdf", headers=h).status_code == 404

    zapis = _json(klient.put(url, headers=h, json={"zmiana_terminu": {
        "nowy_termin": "2027-06-24",
        "data_zawiadomienia": "2026-11-18",
        "przyczyna": "wniosek_ocenianego",
    }}))
    assert zapis["zawiadomienie_dostepne"] is True
    assert zapis["terminy"]["termin_bazowy"]["data"] == "2027-06-30"
    assert zapis["terminy"]["termin_sporzadzenia_oceny"]["data"] == "2027-06-24"

    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")
    pdf = klient.get(f"{url}/zawiadomienie.pdf", headers=h)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("attachment;")
    tekst = PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    assert all(pole in tekst for pole in ("30.06.2027", "24.06.2027", "18.11.2026", "§ 8"))


def test_zmiana_terminu_trafia_do_cyklu_i_panelu_hr(api_wyniku):
    """Helix G3, pkt 5 (zgłoszenie 124, wariant z rundy 2): zmiana terminu zapisana w ocenie na piśmie przesuwa
    termin także na pulpicie i karcie (/api/cykl) oraz w panelu HR, również gdy data zapoznania z kryteriami
    w ocenie na piśmie jest starsza niż zapis kroku 2 w aplikacji."""
    klient, naglowek = api_wyniku
    h = naglowek("przelozony1")
    proces, kryteria = _przygotuj_proces(klient, h, "P-105")
    _zapisz_punkty(klient, h, proces, kryteria, (5, 5, 5, 5, 5))
    # Wariant z rundy 2: data zapoznania z kryteriami sprzed zapisu kroku 2 w aplikacji nie może zgubić zmiany terminu.
    _json(klient.put(f"{proces}/wynik-okresowy", headers=h, json={
        "data_zapoznania_z_kryteriami": "2025-01-09",
        "zmiana_terminu": {"nowy_termin": "2026-12-15", "data_zawiadomienia": "2026-11-18", "przyczyna": "wniosek_ocenianego"},
    }))
    cykl = {e["osoba_id"]: e for e in _json(klient.get("/api/cykl", headers=h))}
    assert cykl["P-105"]["termin"]["data"] == "2026-12-15"
    pid = int(proces.rsplit("/", 1)[1])
    hr = next(p for p in _json(klient.get("/api/hr/procesy", headers=naglowek("hr"))) if p["proces_id"] == pid)
    assert "2026-12-15" in str(hr) and "2026-12-03" not in str(hr), hr
