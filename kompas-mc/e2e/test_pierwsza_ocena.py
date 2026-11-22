"""Test Playwright #48: pierwsza ocena od kroków 3–5 do pobrania PDF arkusza (zał. nr 2 rozp. 2015).

Przełożony (przelozony1) ma proces pierwszej oceny Zofii (P-203) z zapisanymi kryteriami i decyzjami.
Z karty („Zakończ ocenę”) przechodzi rozmowę oceniającą, zapisuje obszary rozwoju i datę rozmowy („Zakończ rozmowę”),
a w części 3 („Ocena na piśmie”) widzi je przeniesione, uzupełnia sprawozdanie i pola arkusza, zatwierdza go
i pobiera PDF. Uruchomienie i zmienne jak w test_samoocena.py;
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
    # Nowa karta do druku: zapamiętujemy adres, który aplikacja w niej otwiera (chrome-headless-shell nie ma
    # przeglądarki PDF i przerywa nawigację na PDF, więc nie sprawdzamy samej karty).
    page.add_init_script("""
        window.__druk = null;
        window.open = () => {
            const okno = { close() {}, location: {} };
            Object.defineProperty(okno.location, "href", { set(v) { window.__druk = v; } });
            return okno;
        };
    """)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.get_by_role("button", name="Zaloguj").click()
    page.wait_for_selector(".powloka")

    page.locator(".lista button.pozycja", has_text="Szymańska-Demo").first.click()
    page.locator(".ramka.nastepny button").click()
    expect(page.get_by_role("heading", level=1, name="Rozmowa oceniająca")).to_be_visible()
    wnioski = "Koordynowanie pracy z interesariuszami."
    while not page.get_by_role("heading", name="Podsumowanie i punkty").is_visible():
        obszary = page.get_by_label("Obszary rozwoju")
        if obszary.count():
            obszary.fill(wnioski)
        przed = page.locator(".oc-licznik").inner_text()
        page.locator(".oc-nawigacja > button:not(.link)").click()
        expect(page.locator(".oc-licznik", has_text=re.compile(f"^{re.escape(przed)}$"))).to_have_count(0)
    expect(page.get_by_text("Wszystkie kryteria mają punkty.")).to_be_visible()
    page.get_by_label("Data rozmowy oceniającej").fill("2026-11-18")
    page.get_by_role("button", name="Zakończ rozmowę").click()

    expect(page.get_by_role("heading", name="Zakończenie oceny")).to_be_visible()
    expect(page.get_by_text("Część 3 z 3 · Ocena na piśmie", exact=True)).to_be_visible()
    expect(page.get_by_label("Miejscowość", exact=True)).to_have_value("Warszawa")

    def rozwin(nazwa):
        przycisk = page.get_by_role("button", name=nazwa, exact=True)
        if przycisk.get_attribute("aria-expanded") == "false":
            przycisk.click()

    rozwin("Daty (z wcześniejszych kroków)")
    expect(page.get_by_label("Zapoznanie ocenianego z oceną")).to_have_value("")
    expect(page.get_by_role("textbox", name=re.compile("^Rozmowa oceniająca"))).to_have_value("2026-11-18")
    rozwin("Sprawozdanie")
    for etykieta, data in DATY.items():
        page.get_by_role("textbox", name=re.compile("^" + re.escape(etykieta))).fill(data)
    for pole, tekst in zip(("zadania", "problemy_i_rozwiazania", "nowe_umiejetnosci_i_wiedza", "propozycje_usprawnien"), SPRAWOZDANIE):
        page.locator("#sprawozdanie-" + pole).fill(tekst)

    rozwin("Pola arkusza")
    rozwin("Część ogólna")
    for klucz, wartosc in {
        "imie": "Łucja", "nazwisko": "Wójcik-Demo", "stanowisko": "Dyrektor",
        "komorka_organizacyjna": "Departament Cyberbezpieczeństwa",
    }.items():
        page.locator(f'[id="pole-kierujacy_komorka.{klucz}"] input').fill(wartosc)
    expect(page.get_by_role("textbox", name="Data podpisu kierującego komórką")).to_have_value("")
    page.get_by_role("button", name="Zapisz szkic").click()
    expect(page.get_by_role("heading", name="Ocena pozytywna", exact=True)).to_be_visible()
    expect(page.get_by_text("Średnia 5,40 pkt", exact=True)).to_be_visible()
    expect(page.get_by_role("textbox", name="Wnioski rozwojowe")).to_have_value(wnioski)

    page.get_by_role("button", name="Zatwierdź arkusz").click()
    expect(page.get_by_text("Arkusz zatwierdzony. Dalej: decyzja kadrowa (umowa/mianowanie).")).to_be_visible()
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=ZRZUTY / f"pierwsza-ocena-{tryb}.png", full_page=True)
    # „Drukuj do podpisu” otwiera arkusz w nowej karcie (podpis odręczny na wydruku).
    page.get_by_role("button", name="Drukuj do podpisu").click()
    page.wait_for_function("() => window.__druk && window.__druk.startsWith('blob:')")
    assert page.evaluate("async () => (await (await fetch(window.__druk)).text()).slice(0, 5)") == "%PDF-"
    with page.expect_download() as pobranie:
        page.get_by_role("button", name="Pobierz PDF").click()
    sciezka = pobranie.value.path()
    assert sciezka and Path(sciezka).read_bytes()[:5] == b"%PDF-"
