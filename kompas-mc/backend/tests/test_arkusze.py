"""Odbiór kroku 7 przez API i kontrola pól z oryginalnych wzorów."""

from dataclasses import replace
from functools import cache
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from kompas_core.pdf import znajdz_font
from pypdf import PdfReader

from kompas_mc.app import utworz_aplikacje
from kompas_mc.arkusze import KOMUNIKAT_PODPIS, WzoryArkuszy
from kompas_mc.ustawienia import KATALOG_MC


@pytest.fixture
def api_arkusza(ustawienia, tmp_path):
    ustawienia = replace(ustawienia, baza=tmp_path / "oceny.db", log_llm=tmp_path / "llm.jsonl")
    with TestClient(utworz_aplikacje(ustawienia)) as klient:
        @cache
        def naglowek(login):
            odpowiedz = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
            return {"Authorization": f"Bearer {_json(odpowiedz)['token']}"}

        yield klient, naglowek


def _json(odpowiedz, oczekiwany=200):
    assert odpowiedz.status_code == oczekiwany, odpowiedz.text
    return odpowiedz.json()


def _pola(dokument):
    return {p["id"]: p for s in dokument["sekcje"] for p in s["pola"]}


def _proces(klient, naglowek, osoba_id, sciezka="okresowa"):
    odpowiedz = klient.post("/api/procesy", json={"osoba_id": osoba_id, "sciezka": sciezka}, headers=naglowek)
    return f"/api/procesy/{_json(odpowiedz, 201)['id']}"


def _zapisz_oceny(klient, h, proces, *, dodaj_kryterium=False):
    dane = _json(klient.get(f"{proces}/krok2", headers=h))["kryteria"]
    wybrane = [k for k in dane if k["rodzaj"] == "OBOWIAZKOWE"]
    dodatkowe = []
    if dodaj_kryterium:
        dodatkowe = [next(k for k in dane if k["rodzaj"] == "DODATKOWE_DOSTEPNE")]
        wybrane.extend(dodatkowe)
    wskazniki = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in wybrane}
    _json(klient.put(f"{proces}/krok2", headers=h, json={
        "wskazniki": wskazniki,
        "dodatkowe": [k["kompetencja_id"] for k in dodatkowe],
    }))
    _json(klient.put(f"{proces}/ocena/decyzje", headers=h, json={"decyzje": {
        k: {"punkty": 7, "uzasadnienie": "Przełożony potwierdził na podstawie rozmowy."} for k in wskazniki
    }}))
    return list(wskazniki)


def _zapisz_krok6(klient, h, proces, **dodatkowe):
    _json(klient.put(f"{proces}/wynik-okresowy", headers=h, json={
        "data_ustalenia_kryteriow": "2025-01-08",
        "data_zapoznania_z_kryteriami": "2025-01-09",
        "data_sporzadzenia_oceny": "2026-11-20",
        **dodatkowe,
    }))


def _uzupelnienia():
    return {
        "potwierdzenie_kryteriow.oceniajacy.miejscowosc": "Warszawa",
        "potwierdzenie_kryteriow.oceniany.miejscowosc": "Warszawa",
        "rozmowa_oceniajaca.data": "2026-11-18",
        "dokonanie_oceny.oceniajacy.miejscowosc": "Warszawa",
        "wnioski_iprz": "Rozwinąć umiejętności wystąpień i prowadzenia spotkań.",
    }


@pytest.mark.parametrize(
    "arkusz,osoba,login,docx_kryterium,liczba",
    [("B", "P-105", "przelozony1", "Zarządzanie ludźmi", 73), ("C", "P-101", "przelozony1", "Rzetelność", 73)],
)
def test_wzor_wszystkie_pola_i_zgodnosc_z_docx(api_arkusza, ustawienia, arkusz, osoba, login, docx_kryterium, liczba):
    klient, naglowek = api_arkusza
    h = naglowek(login)
    proces = _proces(klient, h, osoba)
    url = f"{proces}/arkusz-okresowy"
    widok = _json(klient.get(url, headers=h))
    wzor = WzoryArkuszy.z_pliku(ustawienia.wzory_arkuszy).dla(arkusz)
    pola = _pola(widok)
    assert widok["arkusz"] == arkusz and len(pola) == liczba
    assert list(pola) == [p.id for s in wzor.sekcje for p in s.pola]
    assert [s["tytul"] for s in widok["sekcje"]] == ["Część I", "Część II", "Część III"]
    plik_zrodlowy = KATALOG_MC.parent / widok["zrodlo"]["sciezka"]
    assert sha256(plik_zrodlowy.read_bytes()).hexdigest() == widok["zrodlo"]["sha256"]
    with ZipFile(plik_zrodlowy) as zrodlo:
        tresc_docx = zrodlo.read("word/document.xml").decode()
    assert docx_kryterium in tresc_docx
    assert docx_kryterium in {p["wartosc"] for p in pola.values() if p["id"].startswith("kryterium_obowiazkowe.")}
    assert "7 dni" in pola["pouczenie"]["wartosc"]
    assert widok["komunikat_podpis"] == KOMUNIKAT_PODPIS

    braki = _json(klient.get(f"{url}/pdf", headers=h), 422)["detail"]["braki"]
    assert braki == widok["braki"]
    assert "wynik_okresowy" in {b["id"] for b in braki}
    assert _json(klient.post(f"{url}/ezd", headers=h), 422)["detail"]["braki"] == braki
    assert klient.put(url, headers=h, json={"pola": {"srednia": "9,0"}}).status_code == 422
    assert klient.put(url, headers=h, json={"pola": {"rozmowa_oceniajaca.data": "2026-11-40"}}).status_code == 422
    assert klient.put(url, headers=h, json={"zatwierdz": True}).status_code == 422
    assert klient.get(url).status_code == 401
    assert klient.get(url, headers=naglowek("przelozony2")).status_code == 403
    assert klient.get(url, headers=naglowek("hr")).status_code == 403
    assert klient.get(f"{url}/pdf", headers=naglowek("hr")).status_code == 403
    assert klient.post(f"{url}/ezd", headers=naglowek("hr")).status_code == 403

    # Szkic można zapisać przed gotowością procesu do wydruku.
    zapis = _json(klient.put(url, headers=h, json={"pola": _uzupelnienia()}))
    assert not zapis["pdf_dostepny"]


@pytest.mark.parametrize("arkusz,osoba,login", [("B", "P-105", "przelozony1"), ("C", "P-101", "przelozony1")])
def test_pelna_sciezka_pdf_i_mock_ezd(api_arkusza, arkusz, osoba, login):
    klient, naglowek = api_arkusza
    h = naglowek(login)
    proces = _proces(klient, h, osoba)
    url = f"{proces}/arkusz-okresowy"
    kryteria = _zapisz_oceny(klient, h, proces, dodaj_kryterium=arkusz == "C")
    if arkusz == "C":
        _zapisz_krok6(klient, h, proces, poprzednia_ocena_poziom="na poziomie oczekiwań", dolacz_wniosek_o_stopien=True)
    else:
        _zapisz_krok6(klient, h, proces)
    widok = _json(klient.get(url, headers=h))
    pola = _uzupelnienia()
    f = _pola(widok)
    assert f["oceniajacy.czesc_I.imie"]["wartosc"] == "Marta"
    assert f["oceniajacy.czesc_II.nazwisko"]["wartosc"] == "Kowalczyk-Demo"
    assert f["ocena_obowiazkowa.1"]["wartosc"] == "7"
    assert f["wynik"]["wartosc"] == "POZYTYWNA"
    assert f["okres_oceny.od"]["wartosc"] == "2025-01-09"
    assert f["okres_oceny.do"]["wartosc"] == "2026-11-20"
    assert f["zapoznanie.oceniany.data"]["wymagane"] is False
    assert f["dokonanie_oceny.oceniajacy.podpis"]["edytowalne"] is False
    if arkusz == "C":
        assert f["ocena_dodatkowa.1.punkty"]["wartosc"] == "7"
        assert f["wniosek_o_stopien.status"]["wartosc"] == "TAK"
        pola.update({
            "urzednik.rok_mianowania": "2020",
            "urzednik.stopien_sluzbowy": "I",
            "urzednik.data_przyznania_stopnia": "2023-10-01",
            "wniosek_o_stopien.stopien": "II",
            "wniosek_o_stopien.umotywowanie": "Zaangażowanie i właściwa koordynacja zadań.",
            "wniosek_o_stopien.oceniajacy.miejscowosc": "Warszawa",
            "wniosek_o_stopien.oceniajacy.data": "2026-11-20",
        })
    else:
        assert f["wniosek_o_stopien.status"]["wartosc"] == "NIE DOTYCZY"
        assert not f["urzednik.imie"]["widoczne"]
    wynik = _json(klient.put(url, headers=h, json={"pola": pola, "zatwierdz": True}))
    assert wynik["braki"] == [] and wynik["pdf_dostepny"] and wynik["zatwierdzony"]
    assert _json(klient.get(proces, headers=h))["krok"] == 7

    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")
    pdf = klient.get(f"{url}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    strony = PdfReader(BytesIO(pdf.content)).pages
    assert len(strony) == (4 if arkusz == "C" else 3)
    tekst = " ".join(" ".join(page.extract_text().split()) for page in strony)
    for fragment in (
        f"ARKUSZ {arkusz}", "OCENA OKRESOWA", "20.11.2026", "Marta", "Kowalczyk-Demo",
        "7,00", "7 dni", "Rozwinąć umiejętności",
    ):
        assert fragment in tekst
    assert ("CZĘŚĆ III" in tekst) == (arkusz == "C")
    assert KOMUNIKAT_PODPIS not in tekst and "SHA-256" not in tekst
    rejestracja = _json(klient.post(f"{url}/ezd", headers=h))
    assert rejestracja["numer_sprawy"].startswith("EZD-MC-") and rejestracja["mock"] is True
    assert sha256(pdf.content).hexdigest() == rejestracja["sha256_pdf"]
    assert _json(klient.post(f"{url}/ezd", headers=h)) == rejestracja
    assert _json(klient.get(url, headers=h))["rejestracja_ezd"] == rejestracja
    assert sha256(klient.get(f"{url}/pdf", headers=h).content).hexdigest() == rejestracja["sha256_pdf"]

    _json(klient.put(f"{proces}/ocena/decyzje", headers=h, json={
        "decyzje": {kryteria[0]: {"punkty": 5, "uzasadnienie": "Zmiana decyzji przełożonego."}},
    }))
    po_zmianie = _json(klient.get(url, headers=h))
    assert not po_zmianie["pdf_dostepny"] and not po_zmianie["zatwierdzony"]
    assert po_zmianie["rejestracja_ezd"] is None
    assert klient.post(f"{url}/ezd", headers=h).status_code == 422


def test_pierwsza_ocena_nie_ma_arkusza_okresowego(api_arkusza):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony2")
    proces = _proces(klient, h, "P-201", sciezka="pierwsza")
    assert klient.get(f"{proces}/arkusz-okresowy", headers=h).status_code == 409
