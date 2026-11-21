"""Część I arkusza B/C do podpisu po rozmowie na początku okresu (rozp. 2016 § 5 ust. 3, § 6)."""

from io import BytesIO

import pytest
from kompas_core.pdf import znajdz_font
from pypdf import PdfReader

from kompas_mc.qnt import MockQnt
from kompas_mc.terminy_okresowej import DaneTerminow, KonfiguracjaTerminow, oblicz_terminy

from test_arkusze import _json, _pola, _proces, _zapisz_krok6, _zapisz_oceny, api_arkusza  # noqa: F401


def _zapisz_krok2(klient, h, proces, *, dodatkowe=0):
    dane = _json(klient.get(f"{proces}/krok2", headers=h))["kryteria"]
    wybrane = [k for k in dane if k["rodzaj"] == "OBOWIAZKOWE"]
    dodatkowe_k = [k for k in dane if k["rodzaj"] == "DODATKOWE_DOSTEPNE"][:dodatkowe]
    wybrane.extend(dodatkowe_k)
    _json(klient.put(f"{proces}/krok2", headers=h, json={
        "wskazniki": {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in wybrane},
        "dodatkowe": [k["kompetencja_id"] for k in dodatkowe_k],
    }))
    return [k["nazwa"] for k in dodatkowe_k]


def _tekst(pdf: bytes) -> str:
    return " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(pdf)).pages)


def _wymagaj_fontu():
    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")


def _pola_czesci_i(widok):
    return {p["id"]: p["wartosc"] for s in widok["sekcje"] if s["tytul"] == "Część I" for p in s["pola"]}


def test_przed_krokiem_2_brak_wydruku_czesci_i(api_arkusza):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    odpowiedz = klient.get(f"{proces}/arkusz-okresowy/czesc-i/pdf", headers=h)
    assert odpowiedz.status_code == 409
    assert "krok 2" in str(odpowiedz.json()["detail"])


def test_termin_w_czesci_i_rowny_oblicz_terminy(api_arkusza, ustawienia):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    _zapisz_krok2(klient, h, proces)

    pracownik = MockQnt.z_pliku(ustawienia.qnt).pracownik("P-101")
    konf = KonfiguracjaTerminow.z_pliku(ustawienia.terminy_okresowej)
    termin = oblicz_terminy(pracownik, DaneTerminow(), konf).termin_sporzadzenia_oceny
    assert termin is not None

    widok = _json(klient.get(f"{proces}/arkusz-okresowy", headers=h))
    assert _pola(widok)["termin_sporzadzenia_oceny"]["wartosc"] == termin.data.isoformat()

    _wymagaj_fontu()
    pdf = klient.get(f"{proces}/arkusz-okresowy/czesc-i/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    tekst = _tekst(pdf.content)
    assert "ARKUSZ C" in tekst and "Część I" in tekst and "Część II" not in tekst
    assert termin.data.strftime("%d.%m.%Y") in tekst
    assert "Potwierdzamy" in tekst


def test_dostep_do_czesci_i(api_arkusza):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    _zapisz_krok2(klient, h, proces)
    url = f"{proces}/arkusz-okresowy/czesc-i/pdf"
    assert klient.get(url).status_code == 401
    assert klient.get(url, headers=naglowek("hr")).status_code == 403
    assert klient.get(url, headers=naglowek("przelozony2")).status_code == 403


def test_zmiana_kryteriow_zmienia_wydruk_czesci_i(api_arkusza):
    _wymagaj_fontu()
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    url = f"{proces}/arkusz-okresowy/czesc-i/pdf"
    _zapisz_krok2(klient, h, proces)
    przed = klient.get(url, headers=h).content
    assert klient.get(url, headers=h).content == przed
    nazwy = _zapisz_krok2(klient, h, proces, dodatkowe=1)
    po = klient.get(url, headers=h).content
    assert po != przed
    assert nazwy[0] in _tekst(po)


def test_pelny_arkusz_po_ocenie_ma_te_sama_czesc_i(api_arkusza):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    url = f"{proces}/arkusz-okresowy"
    _zapisz_krok2(klient, h, proces, dodatkowe=1)
    przed = _pola_czesci_i(_json(klient.get(url, headers=h)))

    _zapisz_oceny(klient, h, proces, dodaj_kryterium=True)
    _zapisz_krok6(klient, h, proces)
    po = _pola_czesci_i(_json(klient.get(url, headers=h)))
    # Daty potwierdzenia przełożony wpisuje w kroku 6, reszta części I się nie zmienia.
    daty = {"potwierdzenie_kryteriow.oceniajacy.data", "potwierdzenie_kryteriow.oceniany.data"}
    assert {k: v for k, v in po.items() if k not in daty} == {k: v for k, v in przed.items() if k not in daty}
    assert przed["termin_sporzadzenia_oceny"] is not None


def test_po_ocenie_negatywnej_termin_z_daty_zapoznania_w_aktach(api_arkusza):
    # Po ocenie negatywnej termin liczy się od zapoznania z nią (§ 7 pkt 2); data jest w aktach (QNT, demo).
    klient, naglowek = api_arkusza
    h = naglowek("przelozony2")
    proces = _proces(klient, h, "P-102")
    _zapisz_krok2(klient, h, proces)
    odpowiedz = klient.get(f"{proces}/arkusz-okresowy/czesc-i/pdf", headers=h)
    assert odpowiedz.status_code == 200, odpowiedz.text
    assert odpowiedz.content.startswith(b"%PDF")


def test_bez_terminu_czesc_i_zwraca_422_z_brakiem(api_arkusza):
    # Umowa na czas określony bez poprzedniej oceny: nie ma od czego liczyć terminu oceny okresowej.
    klient, naglowek = api_arkusza
    h = naglowek("przelozony2")
    r = klient.post("/api/procesy", json={"osoba_id": "P-201", "sciezka": "okresowa", "uzasadnienie": "Test braku terminu."}, headers=h)
    proces = f"/api/procesy/{_json(r, 201)['id']}"
    _zapisz_krok2(klient, h, proces)
    odpowiedz = klient.get(f"{proces}/arkusz-okresowy/czesc-i/pdf", headers=h)
    assert odpowiedz.status_code == 422, odpowiedz.text
    szczegoly = odpowiedz.json()["detail"]
    assert "termin" in szczegoly["komunikat"]
    assert szczegoly["braki_terminu"]
