"""#36 krok 8: propozycje z kroków 3–5 dla procesu, wnioski wpisuje przełożony do arkusza i PDF."""

from io import BytesIO

import pytest
from kompas_core.pdf import znajdz_font
from pypdf import PdfReader

from test_arkusze import _json, _pola, _proces, _uzupelnienia, _zapisz_krok6, api_arkusza  # noqa: F401

PRZYKLAD = [{"sytuacja": "Projekt X", "dzialanie": "Rozdzielił zadania bez terminów", "rezultat": "Opóźnienie 2 tygodnie"}]


def _krok2_i_oceny(klient, h, proces, punkty=7):
    """Krok 2 (po 2 wskaźniki w kryteriach obowiązkowych), krok 3 (poniżej i powyżej oczekiwań), krok 5."""
    dane = _json(klient.get(f"{proces}/krok2", headers=h))["kryteria"]
    ob = [k for k in dane if k["rodzaj"] == "OBOWIAZKOWE"]
    wsk = {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:2]] for k in ob}
    _json(klient.put(f"{proces}/krok2", headers=h, json={"wskazniki": wsk, "dodatkowe": []}))
    pierwsze = ob[0]["kompetencja_id"]
    w_nisko, w_wysoko = wsk[pierwsze]
    _json(klient.put(f"{proces}/ocena/wskazniki", headers=h, json={"wskazniki": {
        w_nisko: {"poziom": 3, "przyklady": PRZYKLAD},
        w_wysoko: {"poziom": 9, "przyklady": PRZYKLAD},
    }}))
    _json(klient.put(f"{proces}/ocena/decyzje", headers=h, json={"decyzje": {
        k: {"punkty": punkty, "uzasadnienie": "Decyzja przełożonego."} for k in wsk
    }}))
    return ob[0]["nazwa"]


def test_propozycje_dla_procesu_a_wnioski_w_arkuszu_i_pdf(api_arkusza):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    kompetencja = _krok2_i_oceny(klient, h, proces)

    r = _json(klient.get(f"{proces}/rozwoj", headers=h))
    assert r["sciezka"] == "okresowa" and r["wynik_oceny"] == "pozytywna"
    prop = r["propozycje"]
    assert prop["dostepne"] and prop["tresc_wnioskow"] is None
    typy = {(p["typ"], p["poziom"]) for p in prop["propozycje"]}
    assert ("OBSZAR_ROZWOJOWY", 3) in typy and ("MOCNA_STRONA", 9) in typy
    for p in prop["propozycje"]:  # powiązanie ze wskaźnikiem i przykładem
        assert p["kompetencja"].upper() == kompetencja.upper() and p["wskaznik_id"]
        assert any("Projekt X" in x for x in p["przyklady"]) and p["formy"]
    assert r["pole_arkusza"] == "wnioski_iprz" and r["wnioski_w_arkuszu"] is None

    # Asystent niczego nie wpisał do arkusza.
    url = f"{proces}/arkusz-okresowy"
    assert not _pola(_json(klient.get(url, headers=h)))["wnioski_iprz"]["wartosc"]

    # Przełożony pisze wnioski sam → trafiają do arkusza i PDF.
    _zapisz_krok6(klient, h, proces, poprzednia_ocena_poziom="na poziomie oczekiwań")
    pola = {**_uzupelnienia(), "wnioski_iprz": "Delegowanie zadań – warsztaty i coaching z przełożonym."}
    _json(klient.put(url, headers=h, json={"pola": pola, "zatwierdz": True}))
    assert _json(klient.get(f"{proces}/rozwoj", headers=h))["wnioski_w_arkuszu"].startswith("Delegowanie zadań")
    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")
    pdf = klient.get(f"{url}/pdf", headers=h)
    tekst = " ".join(" ".join(s.extract_text().split()) for s in PdfReader(BytesIO(pdf.content)).pages)
    assert "Delegowanie zadań – warsztaty i coaching z przełożonym." in tekst


def test_przed_decyzjami_wynik_nieznany_a_propozycje_dostepne(api_arkusza):
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-101")
    dane = _json(klient.get(f"{proces}/krok2", headers=h))["kryteria"]
    wsk = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in dane if k["rodzaj"] == "OBOWIAZKOWE"}
    _json(klient.put(f"{proces}/krok2", headers=h, json={"wskazniki": wsk, "dodatkowe": []}))
    r = _json(klient.get(f"{proces}/rozwoj", headers=h))
    assert r["wynik_oceny"] is None and r["propozycje"]["propozycje"] == []


@pytest.mark.parametrize("login, kod", [("hr", 403), ("oceniany", 403)])
def test_tylko_przelozony(api_arkusza, login, kod):
    klient, naglowek = api_arkusza
    proces = _proces(klient, naglowek("przelozony1"), "P-101")
    assert klient.get(f"{proces}/rozwoj", headers=naglowek(login)).status_code == kod
