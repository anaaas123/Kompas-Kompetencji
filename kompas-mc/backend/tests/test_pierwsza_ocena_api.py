"""Pierwsza ocena od pełnych decyzji kroku 5 do arkusza i zawiadomienia."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from kompas_core.pdf import znajdz_font
from pypdf import PdfReader

from kompas_mc.app import utworz_aplikacje


@pytest.fixture
def api_pierwszej(ustawienia, tmp_path):
    ustawienia = replace(ustawienia, baza=tmp_path / "pierwsza.db", log_llm=tmp_path / "llm.jsonl")
    with TestClient(utworz_aplikacje(ustawienia)) as klient:
        yield klient, _login(klient, "przelozony2")


def _login(klient, login):
    r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
    return {"Authorization": f"Bearer {_json(r)['token']}"}


def _json(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def _proces(klient, h, osoba="P-201", sciezka="pierwsza"):
    r = klient.post("/api/procesy", headers=h, json={"osoba_id": osoba, "sciezka": sciezka})
    return f"/api/procesy/{_json(r, 201)['id']}"


def _oceny(klient, h, proces, punkty):
    kryteria = _json(klient.get(f"{proces}/krok2", headers=h))["kryteria"]
    wskazniki = {
        k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]]
        for k in kryteria if k["rodzaj"] == "OBOWIAZKOWE"
    }
    _json(klient.put(f"{proces}/krok2", headers=h, json={"wskazniki": wskazniki}))
    wskaznik = next(iter(wskazniki.values()))[0]
    obserwacja = {"poziom": 9, "przyklady": [{"sytuacja": "Obsługa zgłoszeń", "dzialanie": "Uporządkował sprawy", "rezultat": "Zamknął zaległości"}]}
    ocena = _json(klient.put(f"{proces}/ocena/wskazniki", headers=h, json={"wskazniki": {wskaznik: obserwacja}}))
    sugestia = ocena["kryteria"][0]["sugestia"]
    assert ocena["skala"]["punkty"] == [3, 5, 7]
    assert (sugestia["poziom_modelu"], sugestia["punkty"]) == (9, 7)
    assert "mapowanie 5→3" in sugestia["opis"]
    _json(klient.put(f"{proces}/ocena/decyzje", headers=h, json={"decyzje": {
        k: {"punkty": p, "uzasadnienie": "Przełożony uwzględnił materiał z rozmowy oceniającej."}
        for k, p in zip(wskazniki, punkty, strict=True)
    }}))
    return list(wskazniki)


def _dane(termin_zlozenia):
    return {
        "wyznaczony_termin_sprawozdania": "2026-11-15",
        "data_zlozenia_sprawozdania": termin_zlozenia,
        "sprawozdanie_okres_od": "2026-03-02",
        "sprawozdanie_okres_do": "2026-10-15",
        "data_rozmowy_oceniajacej": "2026-11-18",
        "data_sporzadzenia_oceny": "2026-11-20",
        "sprawozdanie": {
            "zadania": "Analiza wpływających zgłoszeń.",
            "problemy_i_rozwiazania": "Porządkowanie kolejki zgłoszeń.",
            "nowe_umiejetnosci_i_wiedza": "Koordynowanie pracy z interesariuszami.",
            "propozycje_usprawnien": "Weryfikacja wpływu przed kolejną zmianą.",
        },
        "pola": {
            "kierujacy_komorka.imie": "Łucja",
            "kierujacy_komorka.nazwisko": "Wójcik-Demo",
            "kierujacy_komorka.stanowisko": "Dyrektor",
            "kierujacy_komorka.komorka_organizacyjna": "Departament Cyberbezpieczeństwa",
            "potwierdzenie_rozmowy_wstepnej.przelozony.miejscowosc": "Warszawa",
            "potwierdzenie_rozmowy_wstepnej.oceniany.miejscowosc": "Warszawa",
            "potwierdzenie_rozmowy_oceniajacej.przelozony.miejscowosc": "Warszawa",
            "potwierdzenie_rozmowy_oceniajacej.oceniany.miejscowosc": "Warszawa",
            "dokonanie_oceny.przelozony.miejscowosc": "Warszawa",
            "dokonanie_oceny.kierujacy.miejscowosc": "Warszawa",
        },
    }


def _tekst_pdf(r):
    assert r.status_code == 200 and r.headers["Content-Type"] == "application/pdf", r.text
    return " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(r.content)).pages)


@pytest.mark.parametrize(
    ("punkty", "zlozenie", "wynik", "srednia", "niespelniony"),
    [
        ((3, 3, 5, 7, 7), "2026-11-14", "negatywna", "5.0", "§ 10 ust. 1 pkt 3"),
        ((7, 7, 7, 7, 7), "2026-11-16", "negatywna", "7.0", "§ 10 ust. 1 pkt 2"),
        ((3, 5, 5, 7, 7), "2026-11-14", "pozytywna", "5.4", None),
    ],
)
def test_wynik_formularz_i_pdf(api_pierwszej, punkty, zlozenie, wynik, srednia, niespelniony):
    klient, h = api_pierwszej
    proces = _proces(klient, h)
    url = f"{proces}/pierwsza-ocena"
    przed = _json(klient.get(url, headers=h))
    assert przed["terminy"]["termin_rozmowy_wstepnej"]["data"] == "2026-03-23"
    assert przed["terminy"]["data_rozmowy_wstepnej"] == "2026-03-16"
    assert przed["terminy"]["pierwsza_ocena_od"]["data"] == "2026-11-03"
    assert przed["egzamin"]["wynik"] == "tak"
    assert przed["obliczenie"] is None
    assert len([p for s in przed["formularz"]["sekcje"] for p in s["pola"]]) == 60
    assert klient.get(f"{url}/arkusz.pdf", headers=h).status_code == 422
    assert klient.get(f"{proces}/wynik-okresowy", headers=h).status_code == 409
    assert klient.get(f"{proces}/arkusz-okresowy", headers=h).status_code == 409
    kryteria = _oceny(klient, h, proces, punkty)
    dane = _dane(zlozenie)
    _json(klient.put(url, headers=h, json={**dane, "egzamin": {"wynik": "nie_dotyczy"}}), 422)
    stan = _json(klient.put(url, headers=h, json=dane))
    assert stan["obliczenie"]["wynik"] == wynik
    assert Decimal(str(stan["obliczenie"]["srednia"])) == Decimal(srednia)
    assert stan["mapowanie"]["wartosci"] == {"1": 3, "3": 3, "5": 5, "7": 7, "9": 7}
    assert len(stan["warunki"]) == 4
    assert [w["zrodlo"]["lokalizator"] for w in stan["warunki"] if not w["spelniony"]] == (
        [niespelniony] if niespelniony else []
    )
    assert {w["zrodlo"]["doc_id"] for w in stan["warunki"]} == {"rozp-2015-pierwsza"}
    if wynik == "negatywna":
        assert not stan["wnioski_dostepne"] and stan["uzasadnienie_wymagane"]
        assert "uzasadnienie" in {b["id"] for b in stan["formularz"]["braki"]}
        assert klient.put(url, headers=h, json={**dane, "zatwierdz": True}).status_code == 422
        assert klient.put(url, headers=h, json={**dane, "wnioski_rozwojowe": "Niedostępne."}).status_code == 422
        dane["uzasadnienie"] = "Zastosowano przesłankę § 10 dotyczącą wyniku negatywnego."
    else:
        assert stan["wnioski_dostepne"] and not stan["uzasadnienie_wymagane"]
        dane["wnioski_rozwojowe"] = "Doskonalenie prowadzenia spotkań zespołu."
    pelny = _json(klient.put(url, headers=h, json={**dane, "zatwierdz": True}))
    assert pelny["formularz"]["zatwierdzony"] and pelny["formularz"]["pdf_dostepny"]
    assert _json(klient.get(proces, headers=h))["krok"] == 7
    rozwoj = _json(klient.get(f"{proces}/rozwoj", headers=h))
    assert rozwoj["wynik_oceny"] == wynik
    assert rozwoj["propozycje"]["dostepne"] == (wynik == "pozytywna")
    assert rozwoj["wnioski_w_arkuszu"] == dane.get("wnioski_rozwojowe")

    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")
    wydruk = klient.get(f"{url}/arkusz.pdf", headers=h)
    tekst = _tekst_pdf(wydruk)
    assert len(PdfReader(BytesIO(wydruk.content)).pages) == 3
    assert all(f in tekst for f in ("ARKUSZ PIERWSZEJ OCENY", "Łucja", "Wójcik-Demo", "20.11.2026"))
    assert f"{Decimal(srednia):.2f}".replace(".", ",") in tekst.split()  # ocena łączna jak na ekranie: 5,40
    assert "Wygenerowanie PDF" not in tekst and "SHA-256" not in tekst
    if wynik == "negatywna":
        assert dane["uzasadnienie"] in tekst
    assert ("Doskonalenie prowadzenia" in tekst) == (wynik == "pozytywna")
    assert "sprzeciw do dyrektora" not in tekst
    nowa = (3 if punkty[0] == 7 else 7)
    _json(klient.put(f"{proces}/ocena/decyzje", headers=h, json={
        "decyzje": {kryteria[0]: {"punkty": nowa, "uzasadnienie": "Zmiana decyzji po uzupełnieniu danych."}},
    }))
    zmieniony = _json(klient.get(url, headers=h))["formularz"]
    assert not zmieniony["zatwierdzony"] and not zmieniony["pdf_dostepny"]
    assert "aktualne_decyzje" in {b["id"] for b in zmieniony["braki"]}


def test_zastepstwo_zawiadomienie_i_izolacja_uprawnien(api_pierwszej):
    klient, h = api_pierwszej
    proces = _proces(klient, h, osoba="P-204")
    url = f"{proces}/pierwsza-ocena"
    poczatek = _json(klient.get(url, headers=h))
    assert poczatek["terminy"]["termin_rozmowy_wstepnej"]["data"] == "2026-02-04"
    assert poczatek["egzamin"] == {"wynik": "nie_dotyczy", "przeslanka": "zastepstwo"}
    assert klient.get(url).status_code == 401
    h_hr = _login(klient, "hr")
    assert klient.get(url, headers=h_hr).status_code == 403
    assert klient.get(f"{url}/arkusz.pdf", headers=h_hr).status_code == 403
    assert klient.get(f"{url}/zawiadomienie.pdf", headers=h_hr).status_code == 403
    assert klient.put(url, headers=h_hr, json={}).status_code == 403
    assert klient.get(f"{url}/zawiadomienie.pdf", headers=h).status_code == 404
    assert klient.get(url, headers=_login(klient, "przelozony1")).status_code == 403
    blad = _json(klient.put(url, headers=h, json={
        "wyznaczony_termin_sprawozdania": "2026-10-10",
        "przedluzenie": {
            "przyczyna": "obowiazki_poza_miejscem_pracy",
            "data_zawiadomienia": "2026-09-20",
            "nowy_termin": "2026-10-29",
        },
    }), 422)
    assert "Podaj okres" in blad["detail"]
    assert klient.get(f"{url}/zawiadomienie.pdf", headers=h).status_code == 404
    zapis = _json(klient.put(url, headers=h, json={
        "wyznaczony_termin_sprawozdania": "2026-10-10",
        "przedluzenie": {
            "przyczyna": "usprawiedliwiona_nieobecnosc",
            "data_zawiadomienia": "2026-09-20",
            "nowy_termin": "2026-10-29",
        },
    }))
    assert zapis["zawiadomienie_dostepne"]
    hr = _json(klient.get("/api/hr/procesy", headers=h_hr))
    wiersz = next(w for w in hr if w["osoba_id"] == "P-204")
    assert wiersz["najblizszy_termin"]["data"] == "2026-10-29"
    assert wiersz["najblizszy_termin"]["nazwa"] == "złożenie sprawozdania (§ 4–5)"
    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")
    pdf = _tekst_pdf(klient.get(f"{url}/zawiadomienie.pdf", headers=h))
    assert all(f in pdf for f in ("10.10.2026", "29.10.2026", "§ 5 ust. 4", "Dąbrowski-Demo"))
    drugi = _proces(klient, h, osoba="P-103", sciezka="okresowa")
    assert klient.get(f"{drugi}/pierwsza-ocena", headers=h).status_code == 409


def test_rozmowa_wstepna_pdf_po_zapisie_terminu_sprawozdania(api_pierwszej):
    klient, h = api_pierwszej
    proces = _proces(klient, h)
    assert klient.get(f"{proces}/pierwsza-ocena/rozmowa-wstepna.pdf", headers=h).status_code == 409

    stan = _json(klient.get(f"{proces}/pierwsza-ocena", headers=h))
    dane = {**stan["dane"], "data_rozmowy_wstepnej": "2026-03-16", "wyznaczony_termin_sprawozdania": "2026-11-15"}
    _json(klient.put(f"{proces}/pierwsza-ocena", headers=h, json=dane))
    r = klient.get(f"{proces}/pierwsza-ocena/rozmowa-wstepna.pdf", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    strony = PdfReader(BytesIO(r.content)).pages
    assert len(strony) == 1
    tekst = " ".join(strony[0].extract_text().split())
    assert all(f in tekst for f in ("CZĘŚĆ OGÓLNA", "ROZMOWA WSTĘPNA", "Kamińska-Demo", "16.03.2026", "15.11.2026"))
    for klucz in ("pierwsza_ocena_od", "pierwsza_ocena_do"):
        assert date.fromisoformat(stan["terminy"][klucz]["data"]).strftime("%d.%m.%Y") in tekst
    assert "ROZMOWA OCENIAJĄCA" not in tekst and "Wygenerowanie PDF" not in tekst
    assert klient.get(f"{proces}/pierwsza-ocena/rozmowa-wstepna.pdf", headers=_login(klient, "oceniany")).status_code == 403
