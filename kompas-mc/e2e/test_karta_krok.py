"""Test Playwright #49: karta pracownika otwiera bieżący krok procesu, nie krok 1.

Przełożony ma proces oceny okresowej Roberta (P-105) z zapisanymi kryteriami i decyzjami (krok 5).
Jedno kliknięcie przycisku w ramce „Następny krok” na karcie otwiera kroki 3–5.
Uruchomienie i zmienne jak w test_samoocena.py; potrzebna świeża baza (proces P-105 bez wyniku).
"""

from __future__ import annotations

import os
import re
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
        yield p, b
        b.close()


@pytest.fixture(scope="module")
def proces_w_kroku_5(przegladarka):
    """Proces okresowy P-105: krok 2 zapisany, decyzje przełożonego przy wszystkich kryteriach."""
    p, _ = przegladarka
    api = p.request.new_context()
    r = api.post(f"{API}/api/auth/login", data={"login": "przelozony1", "hasło": "demo"})
    assert r.ok, r.text()
    h = {"authorization": f"Bearer {r.json()['token']}"}
    w_toku = [x for x in api.get(f"{API}/api/procesy", headers=h).json() if x["osoba_id"] == "P-105" and x["status"] == "W_TOKU"]
    pr = w_toku[0] if w_toku else api.post(f"{API}/api/procesy", headers=h, data={"osoba_id": "P-105", "sciezka": "okresowa"}).json()
    if pr.get("krok2") is None:
        k2 = api.get(f"{API}/api/procesy/{pr['id']}/krok2", headers=h).json()
        wsk = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in k2["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
        assert api.put(f"{API}/api/procesy/{pr['id']}/krok2", headers=h, data={"wskazniki": wsk}).ok
    stan = api.get(f"{API}/api/procesy/{pr['id']}/ocena", headers=h).json()
    decyzje = {k["kompetencja_id"]: {"punkty": 7, "uzasadnienie": "Przełożony potwierdził na podstawie rozmowy."} for k in stan["kryteria"]}
    r = api.put(f"{API}/api/procesy/{pr['id']}/ocena/decyzje", headers=h, data={"decyzje": decyzje})
    assert r.ok, r.text()
    assert api.get(f"{API}/api/procesy/{pr['id']}", headers=h).json()["krok"] == 5
    api.dispose()
    return pr["id"]


def test_karta_otwiera_kroki_3_5_jednym_kliknieciem(przegladarka, proces_w_kroku_5):
    _, b = przegladarka
    tryb = os.environ.get("TRYB", "light")
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.wait_for_selector(".powloka")
    page.locator(".lista button.pozycja", has_text="Maj-Demo").first.click()

    przycisk = page.locator(".ramka.nastepny button")
    expect(przycisk).to_have_count(1)
    przycisk.click()

    expect(page.get_by_text(re.compile(r"^Kroki 3–5"))).to_be_visible()
    expect(page.get_by_text("Krok 1 z 8")).to_have_count(0)
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"karta-krok5-kroki-3-5-{tryb}.png"))
    page.close()


def test_etapy_cyklu_na_karcie_otwieraja_swoj_krok(przegladarka, proces_w_kroku_5):
    """#55: etap zrobiony „Ustalenie kryteriów” otwiera krok 2 procesu, bieżący „Ocena” kroki 3–5; przyszłych brak."""
    _, b = przegladarka
    tryb = os.environ.get("TRYB", "light")
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.wait_for_selector(".powloka")
    page.locator(".lista button.pozycja", has_text="Maj-Demo").first.click()

    etapy = page.locator(".cykl .etapy button.etap")
    expect(etapy).to_have_count(3)
    etapy.filter(has_text="Ustalenie kryteriów").click()
    expect(page.get_by_text("Krok 2 z 8")).to_be_visible()

    page.locator("nav.menu button.poz", has_text="Pulpit").click()
    page.locator(".lista button.pozycja", has_text="Maj-Demo").first.click()
    page.locator(".cykl li.biezacy button.etap").click()
    expect(page.get_by_text(re.compile(r"^Kroki 3–5"))).to_be_visible()
    page.close()
