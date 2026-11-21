"""Test Playwright #58: Zespół z paskiem etapów, osią terminów, profilem kompetencji i zestawieniem CSV.

Serwery jak w test_samoocena.py (KOMPAS_URL, PLAYWRIGHT_CHROMIUM, KOMPAS_ZRZUTY, TRYB=dark dla ciemnego).
Przełożony widzi profil i mapę kompetencji; HR ich nie dostaje (API 403), oś i pasek etapów ma.
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
    expect(page.get_by_role("heading", name="Etapy i terminy")).to_be_visible()
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


def _etapy_i_os(page: Page) -> None:
    etapy = page.locator("figure.udzialy", has_text="Etap cyklu oceny")
    expect(etapy.locator(".pasek-klik button").first).to_be_visible()
    expect(etapy.locator(".legenda")).to_contain_text("ustalenie kryteriów")
    expect(etapy.locator(".legenda")).to_contain_text("ocena końcowa")
    expect(page.locator(".os-terminow .punkt-osi").first).to_be_visible()


def test_przelozony_os_profil_csv(przegladarka):
    page = _zespol(przegladarka, "przelozony1")
    _etapy_i_os(page)
    expect(page.locator(".profil-lista li:not(.skala-profilu)").first).to_be_visible()
    expect(page.locator(".tabela-mapy")).to_be_visible()
    _zrzut(page, "zespol-przelozony")

    wiersze = _csv(page)
    assert wiersze[0].startswith(KOLUMNY + ";"), wiersze[0]
    assert "Komunikacja" in wiersze[0], "przełożony dostaje punkty kryteriów"
    assert len(wiersze) == 1 + int(page.locator(".naglowek-widoku .meta").inner_text().split()[0])

    # Punkt na osi otwiera kartę tej osoby.
    punkt = page.locator(".os-terminow button.punkt-osi").first
    osoba = punkt.get_attribute("aria-label").split(":")[0]
    punkt.click()
    expect(page.get_by_role("heading", level=1)).to_contain_text(osoba)
    page.close()


def test_hr_bez_profilu_i_mapy(przegladarka):
    page = _zespol(przegladarka, "hr")
    _etapy_i_os(page)
    expect(page.get_by_role("heading", name="Kompetencje zespołu")).to_have_count(0)
    expect(page.locator(".profil-lista")).to_have_count(0)
    expect(page.locator(".tabela-mapy")).to_have_count(0)
    _zrzut(page, "zespol-hr")

    wiersze = _csv(page)
    assert wiersze[0] == KOLUMNY, wiersze[0]

    # Klik w odcinek paska etapów otwiera listę z filtrem etapu (znacznik w liście albo aktywna pigułka w tabeli #54).
    page.locator("figure.udzialy", has_text="Etap cyklu oceny").locator(".pasek-klik button").first.click()
    expect(page.locator(".znacznik-filtra, .pigulka.aktywna").first).to_be_visible()
    page.close()
