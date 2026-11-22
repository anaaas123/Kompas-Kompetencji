"""Test Playwright #58, #84: Zespół ze strukturą, zakresem per komórka, osią terminów, kompetencjami i CSV.

Serwery jak w test_samoocena.py (KOMPAS_URL, PLAYWRIGHT_CHROMIUM, KOMPAS_ZRZUTY, TRYB=dark dla ciemnego).
Przełożony widzi kompetencje; HR ich nie dostaje (API 403), strukturę, liczby i oś ma.
Klik wydziału zawęża całą stronę (liczby, linię zakresu, CSV); okruszek wraca do całości.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
ZRZUTY = Path(os.environ["KOMPAS_ZRZUTY"]) if os.environ.get("KOMPAS_ZRZUTY") else None
TRYB = os.environ.get("TRYB", "light")
KOLUMNY = "osoba;stanowisko;departament;wydział;ścieżka;czynność;termin;dni do terminu;ostatnia ocena"


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield b
        b.close()


def _zespol(przegladarka, login: str) -> Page:
    page = przegladarka.new_context(viewport={"width": 1440, "height": 900}, color_scheme=TRYB, accept_downloads=True).new_page()
    page.goto(URL)
    page.get_by_label("Login").fill(login)
    page.get_by_label("Hasło").fill("demo")
    page.keyboard.press("Enter")
    expect(page.locator("nav.menu")).to_be_visible()
    page.locator("nav.menu button.poz", has_text="Zespół").click()
    expect(page.get_by_role("heading", name="Struktura")).to_be_visible()
    return page


def _zrzut(page: Page, nazwa: str) -> None:
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"{nazwa}-{TRYB}.png"), full_page=True)


def _csv(page: Page) -> list[str]:
    with page.expect_download() as pobranie:
        page.get_by_role("button", name="Pobierz zestawienie (CSV)").click()
    tresc = Path(pobranie.value.path()).read_bytes()
    assert tresc.startswith(b"\xef\xbb\xbf"), "brak BOM UTF-8 dla Excela"
    return tresc.decode("utf-8-sig").splitlines()


def _osob(page: Page) -> int:
    """Liczba osób z linii zakresu pod tytułem („5 osób · 2 departamenty · 2 wydziały”)."""
    return int(page.locator(".linijka-zakresu").inner_text().split()[0])


def _uklad(page: Page) -> None:
    # Bez powtórzeń z poprzedniej wersji: podtytułu, paska etapów, dolnych komórek i przycisku do listy.
    for zbedny in ("Mój zespół", "Etap cyklu oceny", "Ostatnia ocena okresowa", "Komórki"):
        expect(page.get_by_text(zbedny, exact=True)).to_have_count(0)
    expect(page.locator(".liczba-zespolu")).to_have_count(3)
    osob = _osob(page)
    expect(page.locator(".struktura tr.wiersz-osoby")).to_have_count(osob)
    expect(page.locator(".linia-ocen")).to_contain_text("Ostatnie oceny:")
    legenda = page.locator(".sekcja-zespolu .legenda")
    expect(legenda).to_contain_text("ocena końcowa")
    expect(page.locator(".os-terminow .punkt-osi").first).to_be_visible()


def _zakres_wydzialu(page: Page) -> None:
    """Klik wydziału zawęża stronę, okruszek wraca do całości."""
    wszystkich = _osob(page)
    wydzial = page.locator("tr.wiersz-wydzialu button.zakres").first
    nazwa = wydzial.locator(".nazwa-zakresu").inner_text()
    w_wydziale = int(wydzial.locator(".liczba-zakresu").inner_text().split()[0])
    wydzial.click()
    expect(page.locator("nav.okruszki")).to_contain_text(nazwa)
    assert _osob(page) == w_wydziale
    expect(page.locator(".struktura tr.wiersz-osoby")).to_have_count(w_wydziale)
    assert len(_csv(page)) == 1 + w_wydziale
    page.locator("nav.okruszki button.link").first.click()
    expect(page.locator("nav.okruszki")).to_have_count(0)
    assert _osob(page) == wszystkich


def test_przelozony_struktura_kompetencje_csv(przegladarka):
    page = _zespol(przegladarka, "przelozony1")
    _uklad(page)
    tabela = page.locator(".tabela-kompetencji")
    expect(tabela).to_be_visible()
    expect(tabela.locator("tr.srednia")).to_contain_text("Średnia zespołu")
    expect(page.locator(".profil-lista")).to_have_count(0)
    # Wnioski z poprawną odmianą: „2 z 3 osób”, „(2 osoby)”.
    expect(page.locator(".wniosek").first).not_to_contain_text(" osoby poniżej")
    _zrzut(page, "zespol-przelozony")

    wiersze = _csv(page)
    assert wiersze[0].startswith(KOLUMNY + ";"), wiersze[0]
    assert "Komunikacja" in wiersze[0], "przełożony dostaje punkty kryteriów"
    assert len(wiersze) == 1 + _osob(page)

    _zakres_wydzialu(page)

    # Imię w strukturze otwiera kartę tej osoby.
    osoba = page.locator(".struktura tr.wiersz-osoby button.link").first
    nazwisko = osoba.inner_text()
    osoba.click()
    expect(page.get_by_role("heading", level=1)).to_contain_text(nazwisko)
    page.close()


def test_przelozony_punkt_osi_otwiera_karte(przegladarka):
    page = _zespol(przegladarka, "przelozony1")
    punkt = page.locator(".os-terminow button.punkt-osi").first
    osoba = punkt.get_attribute("aria-label").split(":")[0]
    punkt.click()
    expect(page.get_by_role("heading", level=1)).to_contain_text(osoba)
    page.close()


def test_hr_bez_kompetencji(przegladarka):
    page = _zespol(przegladarka, "hr")
    _uklad(page)
    expect(page.get_by_role("heading", name="Kompetencje")).to_have_count(0)
    expect(page.locator(".tabela-kompetencji")).to_have_count(0)
    _zrzut(page, "zespol-hr")

    wiersze = _csv(page)
    assert wiersze[0] == KOLUMNY, wiersze[0]

    # Klik etapu w legendzie osi otwiera listę z filtrem etapu (znacznik w liście albo aktywna pigułka w tabeli #54).
    page.locator(".sekcja-zespolu .legenda button.pozycja-legendy").first.click()
    expect(page.locator(".znacznik-filtra, .pigulka.aktywna").first).to_be_visible()
    page.close()
