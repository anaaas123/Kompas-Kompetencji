"""Test Playwright #82: krok 2 pół na pół na jednym ekranie (Karol 02:04).

Przełożony (przelozony2) otwiera kryteria Piotra (P-102, ocena okresowa) na 1440 × 900: obowiązkowe z lewej
w dwóch kolumnach, dodatkowe z prawej z jasnym zakresem „od 0 do 3” (§ 5 ust. 2), całość mieści się
w oknie, bez dopisków pod nagłówkami sekcji. Uruchomienie i zmienne jak w test_samoocena.py.
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
def test_krok2_pol_na_pol_na_jednym_ekranie(przegladarka, tryb):
    page = przegladarka.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony2")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.keyboard.press("Enter")
    page.wait_for_selector(".powloka")
    page.locator("nav.menu button.poz", has_text="Pracownicy").click()
    page.get_by_text("Piotr Nowak-Demo").first.click()
    page.locator(".ramka.nastepny button").first.click()
    start = page.locator("form.k1-start")
    start.or_(page.get_by_role("heading", name="Kryteria i wskaźniki")).first.wait_for()
    if start.count():  # świeża baza: start w kroku 1, dalej kryteria (z ekranem kroku 1 albo bez niego, #86)
        start.get_by_role("button", name="Rozpocznij ocenę").click()
        dalej = page.get_by_role("button", name="Dalej: krok 2")
        dalej.or_(page.get_by_role("heading", name="Kryteria i wskaźniki")).first.wait_for()
        if dalej.count():
            dalej.click()
    page.get_by_role("heading", name="Kryteria i wskaźniki").wait_for()

    obowiazkowe = page.locator(".k2-sekcja", has=page.get_by_role("heading", name="Obowiązkowe"))
    dodatkowe = page.locator(".k2-sekcja", has=page.get_by_role("heading", name="Dodatkowe"))
    expect(dodatkowe.get_by_role("heading")).to_contain_text("od 0 do 3")
    lewa, prawa = obowiazkowe.bounding_box(), dodatkowe.bounding_box()
    assert lewa["x"] + lewa["width"] <= prawa["x"], "dodatkowe z prawej obok obowiązkowych"
    pierwszy, drugi = (w.bounding_box() for w in obowiazkowe.locator(".k2-wiersz").all()[:2])
    assert abs(pierwszy["y"] - drugi["y"]) < 1 and drugi["x"] > pierwszy["x"], "obowiązkowe w dwóch kolumnach"
    assert page.evaluate("document.querySelector('.k2').getBoundingClientRect().bottom") <= 900
    expect(page.locator(".k2-sekcja p.meta")).to_have_count(0)

    obowiazkowe.get_by_role("button", name="Zmień wskaźniki").first.click()
    otwarty = obowiazkowe.locator(".k2-wiersz.otwarty")
    assert otwarty.bounding_box()["width"] > pierwszy["width"] * 1.5, "rozwinięte wskaźniki na całą szerokość listy"
    page.close()
