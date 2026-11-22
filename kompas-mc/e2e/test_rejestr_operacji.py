"""Test Playwright: rejestr operacji dla HR (Karol 22.11 02:11, rada 3/3 CONDITIONAL_GO).

Przełożony zakłada proces, oceniany dostaje odmowę 403; HR otwiera „Rejestr operacji”: widzi operacje,
filtruje odmowy, pobiera CSV. Przełożony nie ma tej pozycji w menu. Uruchomienie i zmienne jak w
test_samoocena.py; potrzebna świeża baza.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
API = os.environ.get("KOMPAS_API", "http://127.0.0.1:8002")
ZRZUTY = Path(os.environ["KOMPAS_ZRZUTY"]) if os.environ.get("KOMPAS_ZRZUTY") else None


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        api = p.request.new_context()
        token = lambda login: api.post(f"{API}/api/auth/login", data={"login": login, "hasło": "demo"}).json()["token"]  # noqa: E731
        h = {"authorization": f"Bearer {token('przelozony1')}"}
        pid = api.post(f"{API}/api/procesy", headers=h, data={"osoba_id": "P-104", "sciezka": "okresowa"}).json()["id"]
        assert api.get(f"{API}/api/procesy/{pid}/krok2", headers={"authorization": f"Bearer {token('oceniany')}"}).status == 403
        api.dispose()
        yield b
        b.close()


def zaloguj(b, login: str, tryb: str):
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb, accept_downloads=True)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', login)
    page.fill('input[aria-label="Hasło"]', "demo")
    page.keyboard.press("Enter")
    page.wait_for_selector(".powloka")
    return page


@pytest.mark.parametrize("tryb", ["light", "dark"])
def test_hr_widzi_rejestr_filtruje_i_pobiera_csv(przegladarka, tryb):
    page = zaloguj(przegladarka, "hr", tryb)
    bledy: list[str] = []
    page.on("pageerror", lambda e: bledy.append(str(e)))
    page.locator("nav.menu button.poz", has_text="Rejestr operacji").click()
    expect(page.get_by_role("heading", level=1, name="Rejestr operacji")).to_be_visible()
    wiersze = page.locator(".rejestr-tabela tbody tr")
    expect(wiersze.first).to_be_visible()
    expect(page.locator(".rejestr-tabela")).to_contain_text("przelozony1")
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"rejestr-{tryb}.png"))

    page.get_by_role("group", name="Wynik operacji").get_by_role("button", name="odmowy").click()
    expect(page.locator(".rejestr-tabela")).to_contain_text("oceniany")
    expect(page.locator(".rejestr-tabela .status.pozytywna")).to_have_count(0)
    with page.expect_download() as pobranie:
        page.get_by_role("button", name="Pobierz CSV").click()
    assert pobranie.value.suggested_filename == "rejestr-operacji.csv"
    assert "czas;uzytkownik;rola;akcja" in Path(pobranie.value.path()).read_text(encoding="utf-8-sig")
    assert not bledy, bledy
    page.close()


def test_przelozony_nie_ma_rejestru(przegladarka):
    page = zaloguj(przegladarka, "przelozony1", "light")
    expect(page.locator("nav.menu button.poz", has_text="Rejestr operacji")).to_have_count(0)
    page.close()
