"""Test Playwright #73: pierwsza ocena, krok 2 kończy się rozmową wstępną z wydrukiem części I–II arkusza.

Przełożony ma proces pierwszej oceny Kacpra (P-202) z zapisanym krokiem 2 i bez daty rozmowy wstępnej.
Na końcu kroku 2 termin sprawozdania jest już podpowiedziany (pierwszy możliwy dzień), data sprzed
8 miesięcy pracy blokuje zapis z ludzkim komunikatem; zapis pobiera PDF, a cykl przestaje pokazywać „Rozmowa wstępna” jako czynność do zrobienia (rozp. 2015 § 3–4).
Uruchomienie i zmienne jak w test_samoocena.py; potrzebna świeża baza (P-202 bez procesu).
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
        yield p, b
        b.close()


@pytest.fixture(scope="module")
def api(przegladarka):
    p, _ = przegladarka
    ctx = p.request.new_context()
    r = ctx.post(f"{API}/api/auth/login", data={"login": "przelozony1", "hasło": "demo"})
    assert r.ok, r.text()
    yield ctx, {"authorization": f"Bearer {r.json()['token']}"}
    ctx.dispose()


@pytest.fixture(scope="module")
def proces_po_kroku_2(api):
    ctx, h = api
    pr = ctx.post(f"{API}/api/procesy", headers=h, data={"osoba_id": "P-202", "sciezka": "pierwsza"})
    assert pr.ok, pr.text()
    pid = pr.json()["id"]
    k2 = ctx.get(f"{API}/api/procesy/{pid}/krok2", headers=h).json()
    wsk = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in k2["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
    assert ctx.put(f"{API}/api/procesy/{pid}/krok2", headers=h, data={"wskazniki": wsk}).ok
    stan = ctx.get(f"{API}/api/procesy/{pid}/pierwsza-ocena", headers=h).json()
    assert stan["terminy"]["data_rozmowy_wstepnej"] is None
    return pid, stan["terminy"]["termin_sprawozdania_od"]["data"]


def test_rozmowa_wstepna_zapis_i_wydruk_czesci_i_ii(przegladarka, api, proces_po_kroku_2):
    _, b = przegladarka
    ctx, h = api
    pid, najwczesniej = proces_po_kroku_2
    tryb = os.environ.get("TRYB", "light")
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=tryb, accept_downloads=True)
    bledy: list[str] = []
    page.on("pageerror", lambda e: bledy.append(str(e)))
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.wait_for_selector(".powloka")
    page.locator("nav.menu button.poz", has_text="Pracownicy").click()
    page.get_by_text("Kacper Mazur-Demo").first.click()
    page.locator(".cykl .etapy button.etap", has_text="Rozpoczęcie: rozmowa wstępna").click()
    page.get_by_role("button", name="Zatwierdź kryteria i dalej").click()

    przycisk = page.get_by_role("button", name="Zapisz i wydrukuj części I–II")
    expect(page.get_by_text("Termin sprawozdania wyznaczasz na rozmowie")).to_be_visible()
    pole = page.get_by_label("Termin sprawozdania pracownika")
    expect(pole).to_have_value(najwczesniej)
    pole.fill("2026-11-23")
    expect(przycisk).to_be_disabled()
    expect(page.locator(".k2-ustalone p.blad")).to_contain_text("najwcześniej")
    pole.fill(najwczesniej)
    with page.expect_download() as pobranie:
        przycisk.click()
    assert pobranie.value.suggested_filename == f"pierwsza-ocena-{pid}-rozmowa-wstepna.pdf"
    expect(page.locator(".k2-ustalone strong", has_text="Rozmowa wstępna")).to_be_visible()
    expect(page.get_by_role("button", name="Wydrukuj części I–II do podpisu")).to_be_visible()
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"rozmowa-wstepna-{tryb}.png"))

    cykl = {e["osoba_id"]: e for e in ctx.get(f"{API}/api/cykl", headers=h).json()}
    assert cykl["P-202"]["czynnosc"] != "Rozmowa wstępna", cykl["P-202"]
    assert not bledy, bledy
    page.close()
