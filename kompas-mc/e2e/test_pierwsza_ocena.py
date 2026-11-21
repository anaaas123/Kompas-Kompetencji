"""Test Playwright #48: pierwsza ocena od kroków 3–5 do pobrania PDF arkusza (zał. nr 2 rozp. 2015).

Przełożony (przelozony1) ma proces pierwszej oceny Zofii (P-203) z zapisanymi kryteriami i decyzjami.
Z karty pracownika przechodzi podsumowanie ocen, rozmowę i ekran pierwszej oceny: zapisuje sprawozdanie
i daty, uzupełnia pola arkusza, zatwierdza go i pobiera PDF. Uruchomienie i zmienne jak w test_samoocena.py;
TRYB=dark robi to samo w ciemnym motywie, KOMPAS_ZRZUTY zapisuje zrzuty.
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

# Sprawozdanie złożone przed wyznaczonym terminem; dane jak _dane() w backend/tests/test_pierwsza_ocena_api.py.
DATY = {
    "Wyznaczony termin sprawozdania": "2026-11-15",
    "Złożenie sprawozdania": "2026-11-14",
    "Sprawozdanie za okres od": "2026-03-02",
    "Sprawozdanie za okres do": "2026-10-15",
    "Rozmowa oceniająca": "2026-11-18",
    "Sporządzenie oceny": "2026-11-20",
}
SPRAWOZDANIE = (
    "Analiza wpływających zgłoszeń.",
    "Porządkowanie kolejki zgłoszeń.",
    "Koordynowanie pracy z interesariuszami.",
    "Weryfikacja wpływu przed kolejną zmianą.",
)


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield p, b
        b.close()


@pytest.fixture(scope="module")
def proces_pierwszej(przegladarka):
    """Pierwsza ocena P-203: krok 2 zapisany, decyzje 3, 5, 5, 7, 7 (wynik pozytywny przy sprawozdaniu w terminie)."""
    p, _ = przegladarka
    api = p.request.new_context()
    r = api.post(f"{API}/api/auth/login", data={"login": "przelozony1", "hasło": "demo"})
    assert r.ok, r.text()
    h = {"authorization": f"Bearer {r.json()['token']}"}
    w_toku = [x for x in api.get(f"{API}/api/procesy", headers=h).json() if x["osoba_id"] == "P-203" and x["status"] == "W_TOKU"]
    pr = w_toku[0] if w_toku else api.post(f"{API}/api/procesy", headers=h, data={"osoba_id": "P-203", "sciezka": "pierwsza"}).json()
    assert pr["sciezka"] == "pierwsza", pr
    if pr.get("krok2") is None:
        k2 = api.get(f"{API}/api/procesy/{pr['id']}/krok2", headers=h).json()
        wsk = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in k2["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
        assert api.put(f"{API}/api/procesy/{pr['id']}/krok2", headers=h, data={"wskazniki": wsk}).ok
    stan = api.get(f"{API}/api/procesy/{pr['id']}/ocena", headers=h).json()
    decyzje = {
        k["kompetencja_id"]: {"punkty": pkt, "uzasadnienie": "Przełożony potwierdził na podstawie rozmowy."}
        for k, pkt in zip(stan["kryteria"], (3, 5, 5, 7, 7))
    }
    r = api.put(f"{API}/api/procesy/{pr['id']}/ocena/decyzje", headers=h, data={"decyzje": decyzje})
    assert r.ok, r.text()
    api.dispose()
    return pr["id"]


def test_pierwsza_ocena_od_krokow_3_5_do_pdf_arkusza(przegladarka, proces_pierwszej):
    _, b = przegladarka
    tryb = os.environ.get("TRYB", "light")
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb, accept_downloads=True)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.get_by_role("button", name="Zaloguj").click()
    page.wait_for_selector(".powloka")

    page.locator("button.pozycja", has_text="Zofia Szymańska-Demo").first.click()
    page.get_by_role("button", name="Oceń kompetencje").first.click()
    page.locator("main button", has_text="Podsumowanie").first.click()
    page.get_by_role("button", name="Dalej: rozmowa oceniająca").click()
    expect(page.get_by_role("heading", name="Zakres rozmowy")).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Dalej: wynik")).click()

    expect(page.get_by_role("heading", name="Wynik pierwszej oceny")).to_be_visible()
    dane = page.locator("section:has(h2:has-text('Daty, sprawozdanie'))")
    for etykieta, data in DATY.items():
        dane.locator(f"label:has-text('{etykieta}') input").first.fill(data)
    for i, tekst in enumerate(SPRAWOZDANIE):
        dane.locator("label:has-text('Sprawozdanie:') textarea").nth(i).fill(tekst)
    for pole in page.locator(".pola-arkusza .pole-arkusza").all():
        wejscie = pole.locator("input, textarea")
        if wejscie.count() and not wejscie.first.input_value():
            etykieta = pole.locator("label.etykieta").first.inner_text()
            wejscie.first.fill("2026-11-21" if "Data" in etykieta else "Warszawa")
    page.get_by_role("button", name="Zapisz", exact=True).click()
    expect(page.locator("p.wartosc")).to_contain_text("ocena pozytywna")
    expect(page.locator("section:has(h2:has-text('Braki')) li")).to_have_count(0)

    page.get_by_role("button", name="Zatwierdź arkusz").click()
    expect(page.get_by_text("Arkusz zatwierdzony.")).to_be_visible()
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=ZRZUTY / f"pierwsza-ocena-{tryb}.png", full_page=True)
    with page.expect_download() as pobranie:
        page.get_by_role("button", name="Pobierz arkusz PDF").click()
    sciezka = pobranie.value.path()
    assert sciezka and Path(sciezka).read_bytes()[:5] == b"%PDF-"
