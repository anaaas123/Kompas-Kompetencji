"""Test Playwright: okno asystenta po zalogowaniu wysyła token i dostaje odpowiedź z cytatem (Helix G3, Grok 3).

Od tej zmiany POST /api/asystent wymaga zalogowania; bez tokenu API odpowiada 401, a okno pokazałoby błąd.
Uruchomienie i zmienne jak w test_samoocena.py (KOMPAS_URL, KOMPAS_API, PLAYWRIGHT_CHROMIUM, TRYB).
"""

from __future__ import annotations

import os

from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")


def test_asystent_po_zalogowaniu_odpowiada_z_cytatem():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=os.environ.get("TRYB", "light"))
        odmowy: list[int] = []
        page.on("response", lambda r: odmowy.append(r.status) if "/api/asystent" in r.url and r.status >= 400 else None)
        page.goto(URL)
        page.fill('input[aria-label="Login"]', "przelozony1")
        page.fill('input[aria-label="Hasło"]', "demo")
        page.click("form.logowanie-formularz button")
        page.wait_for_selector(".powloka")
        page.locator("nav.menu button.poz", has_text="Asystent formalny").click()
        page.get_by_label("Pytanie do asystenta formalnego").fill("Ile dni ma pracownik na sprzeciw od oceny okresowej?")
        page.get_by_label("Pytanie do asystenta formalnego").press("Enter")
        expect(page.locator(".odpowiedz").first).to_be_visible(timeout=20000)
        assert odmowy == []
        b.close()
