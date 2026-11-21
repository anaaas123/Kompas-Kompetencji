"""Test Playwright #9: oceniany wypełnia i przekazuje samoocenę, przełożony widzi ją w kroku 3 z rozbieżnością.

Na świeżej bazie (proces P-101 nie może mieć przekazanej samooceny):

    KOMPAS_MC_DANE=$(mktemp -d) uv run kompas-mc                      # kompas-mc/backend, API 8002
    npm run dev                                                         # kompas-mc/frontend, 5174
    uv run --with playwright --with pytest pytest kompas-mc/e2e -q      # z katalogu repo

Zmienne: KOMPAS_URL (domyślnie http://127.0.0.1:5174), KOMPAS_API (http://127.0.0.1:8002),
PLAYWRIGHT_CHROMIUM (ścieżka przeglądarki, gdy nie ma `playwright install chromium`),
KOMPAS_ZRZUTY (katalog na zrzuty ekranów, opcjonalnie).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
API = os.environ.get("KOMPAS_API", "http://127.0.0.1:8002")
ZRZUTY = Path(os.environ["KOMPAS_ZRZUTY"]) if os.environ.get("KOMPAS_ZRZUTY") else None


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield p, b
        b.close()


def _zaloguj_api(api, login: str) -> dict:
    r = api.post(f"{API}/api/auth/login", data={"login": login, "hasło": "demo"})
    assert r.ok, r.text()
    return {"authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def proces(przegladarka):
    """Proces P-101 z zapisanym krokiem 2 i oceną przełożonego 3 przy pierwszym wskaźniku."""
    p, _ = przegladarka
    api = p.request.new_context()
    h = _zaloguj_api(api, "przelozony1")
    procesy = [x for x in api.get(f"{API}/api/procesy", headers=h).json() if x["osoba_id"] == "P-101" and x["status"] == "W_TOKU"]
    pr = procesy[0] if procesy else api.post(f"{API}/api/procesy", headers=h, data={"osoba_id": "P-101", "sciezka": "okresowa"}).json()
    if pr.get("krok2") is None:
        k2 = api.get(f"{API}/api/procesy/{pr['id']}/krok2", headers=h).json()
        wsk = {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:2]] for k in k2["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
        assert api.put(f"{API}/api/procesy/{pr['id']}/krok2", headers=h, data={"wskazniki": wsk}).ok
    stan = api.get(f"{API}/api/procesy/{pr['id']}/ocena", headers=h).json()
    pierwszy = stan["kryteria"][0]["wskazniki"][0]["wskaznik_id"]
    assert api.put(f"{API}/api/procesy/{pr['id']}/ocena/wskazniki", headers=h, data={"wskazniki": {pierwszy: {"poziom": 3}}}).ok
    api.dispose()
    return pr["id"]


def _zaloguj(page: Page, login: str) -> None:
    page.goto(URL)
    page.fill('input[aria-label="Login"]', login)
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.wait_for_selector(".powloka")


def _zrzut(page: Page, nazwa: str) -> None:
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"{nazwa}.png"), full_page=True)


def test_samoocena_od_pracownika_do_kroku_3(przegladarka, proces):
    _, b = przegladarka
    tryb = os.environ.get("TRYB", "light")

    # Pracownik: karta → „Rozpocznij samoocenę” → 9 przy pierwszym wskaźniku, 5 przy reszcie → przekazanie.
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb)
    _zaloguj(page, "oceniany")
    page.locator(".lista button.pozycja", has_text="Zielińska").first.click()
    page.get_by_role("button", name="Rozpocznij samoocenę").click()
    expect(page.get_by_role("heading", name="Moja samoocena")).to_be_visible()
    licznik = page.locator(".postep-samooceny .meta")
    expect(licznik).to_contain_text("Kryterium 1 z")
    kryteriow = int(re.search(r"Kryterium 1 z (\d+)", licznik.inner_text()).group(1))
    for i in range(kryteriow):
        expect(licznik).to_contain_text(f"Kryterium {i + 1} z {kryteriow}")
        for j, wsk in enumerate(page.locator(".wskaznik-samooceny").all()):
            poziom = "9" if i == 0 and j == 0 else "5"
            wsk.locator(".poziom-samooceny", has=page.locator(".numer-poziomu", has_text=poziom)).click()
            expect(wsk.locator('.poziom-samooceny[aria-checked="true"]')).to_have_count(1)
        if i == 0:
            _zrzut(page, f"samoocena-kryterium-{tryb}")
        page.get_by_role("button", name="Dalej", exact=True).click()
    expect(page.get_by_role("heading", name="Podsumowanie")).to_be_visible()
    _zrzut(page, f"samoocena-podsumowanie-{tryb}")
    page.get_by_role("button", name="Przekaż przełożonemu").click()
    page.get_by_role("button", name="Tak, przekaż").click()
    expect(page.get_by_text("Przekazano")).to_be_visible()
    _zrzut(page, f"samoocena-przekazana-{tryb}")
    page.close()

    # Przełożony: karta Anny → krok 1 → krok 2 → kroki 3–5: porównanie z rozbieżnością przy pierwszym wskaźniku.
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb)
    _zaloguj(page, "przelozony1")
    page.locator(".lista button.pozycja", has_text="Zielińska").first.click()
    page.get_by_role("button", name="Kontynuuj ocenę").click()
    page.get_by_role("button", name="Dalej: krok 2").click()
    page.get_by_role("button", name="Dalej: kroki 3–5").click()
    expect(page.get_by_text("Pracownik przekazał samoocenę")).to_be_visible()
    rozbieznosc = page.locator(".porownanie.rozbieznosc").first
    expect(rozbieznosc).to_be_visible()
    expect(rozbieznosc).to_contain_text("Samoocena 9")
    expect(rozbieznosc).to_contain_text("Twoja ocena 3")
    expect(rozbieznosc).to_contain_text("do omówienia")
    _zrzut(page, f"krok3-przelozony-{tryb}")

    # Krok 6: samoocena na rozmowie, rozbieżność na górze z pytaniem do rozmowy.
    page.get_by_role("button", name="Dalej: rozmowa oceniająca").click()
    agenda = page.locator(".agenda")
    expect(agenda).to_contain_text("Samoocena na rozmowie")
    expect(agenda.locator(".lista-agendy > li").first).to_contain_text("Jaka sytuacja z pracy stoi za samooceną?")
    _zrzut(page, f"krok6-przelozony-{tryb}")
    page.close()
