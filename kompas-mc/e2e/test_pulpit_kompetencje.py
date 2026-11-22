"""Test Playwright (zgłoszenie 110): pulpit przełożonego wykorzystuje prawą kolumnę (Karol 22.11 02:04).

Na 1440 × 900 po prawej jest „Mój zespół” i kompetencje zespołu w skrócie (do rozwoju, mocna strona).
Średnie na kryterium i tabela osób są pod spodem na całą szerokość, bez przewijania w poziomie.
Uruchomienie i zmienne jak w test_samoocena.py.
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("tryb", ["light", "dark"])
def test_prawa_kolumna_z_kompetencjami_w_skrocie(przegladarka, tryb):
    page = przegladarka.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.keyboard.press("Enter")
    page.wait_for_selector(".powloka")

    boczna = page.locator(".pulpit-boczna")
    expect(boczna.get_by_role("heading", name="Mój zespół")).to_be_visible()
    expect(boczna.get_by_role("heading", name="Kompetencje zespołu")).to_be_visible()
    expect(boczna.get_by_text("Do rozwoju w zespole")).to_be_visible()
    expect(boczna.get_by_text("Mocna strona zespołu")).to_be_visible()
    expect(boczna.locator(".tabela-mapy, .profil-lista")).to_have_count(0)

    lista = page.locator(".pulpit-kolumny > .sekcja").first.bounding_box()
    prawa = boczna.bounding_box()
    assert abs(prawa["height"] - lista["height"]) < lista["height"] * 0.6, "obie kolumny podobnej wysokości"
    tabela = page.locator(".mapa-kompetencji .tabela-mapy")
    expect(tabela).to_have_count(1)
    assert tabela.evaluate("e => e.scrollWidth <= e.clientWidth + 1"), "tabela bez przewijania w poziomie"
    page.close()
