"""Test Playwright #77: treść zadania pkt 2 („System nie ma być dostępny na smartfonach”).

Do 760 px zamiast logowania i aplikacji jest tylko ekran „Kompas działa na komputerze”; od 768 px
(tablet, komputer) aplikacja jak dotąd. Zmiana szerokości okna działa bez przeładowania.
Uruchomienie i zmienne jak w test_samoocena.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
ZRZUTY = Path(os.environ["KOMPAS_ZRZUTY"]) if os.environ.get("KOMPAS_ZRZUTY") else None


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("tryb", ["light", "dark"])
def test_smartfon_widzi_tylko_informacje_o_komputerze(przegladarka, tryb):
    page = przegladarka.new_page(viewport={"width": 390, "height": 844}, color_scheme=tryb)
    page.goto(URL)
    expect(page.get_by_role("heading", name="Kompas działa na komputerze")).to_be_visible()
    expect(page.locator('input[aria-label="Login"]')).to_be_hidden()
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"tylko-komputer-390-{tryb}.png"))

    page.set_viewport_size({"width": 1024, "height": 768})
    expect(page.locator('input[aria-label="Login"]')).to_be_visible()
    expect(page.get_by_role("heading", name="Kompas działa na komputerze")).to_be_hidden()

    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.wait_for_selector(".powloka")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator(".powloka")).to_be_hidden()
    expect(page.get_by_role("heading", name="Kompas działa na komputerze")).to_be_visible()
    page.close()
