"""Test Playwright #11: cele rozwojowe w interfejsie pracownika i przełożonego.

Na świeżej bazie, jak test_samoocena.py (API 8002, interfejs 5174):

    KOMPAS_MC_DANE=$(mktemp -d) uv run kompas-mc                      # kompas-mc/backend
    npm run dev                                                         # kompas-mc/frontend
    uv run --with playwright --with pytest pytest kompas-mc/e2e -q      # z katalogu repo

Wariant z ``pracownik_moze_edytowac: false`` potrzebuje drugiej pary serwerów
(KOMPAS_MC_CELE=kompas-mc/e2e/cele-bez-edycji.yaml) i zmiennej KOMPAS_URL_BEZ_EDYCJI;
bez niej test jest pomijany. Zmienne jak w test_samoocena.py: KOMPAS_URL, PLAYWRIGHT_CHROMIUM.
"""

from __future__ import annotations

import os
import time

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
URL_BEZ_EDYCJI = os.environ.get("KOMPAS_URL_BEZ_EDYCJI")


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield b
        b.close()


def _strona(przegladarka, url: str, login: str) -> Page:
    page = przegladarka.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.goto(url)
    page.get_by_label("Login").fill(login)
    page.get_by_label("Hasło").fill("demo")
    page.keyboard.press("Enter")
    expect(page.locator("nav.menu")).to_be_visible()
    return page


def _menu(page: Page, pozycja: str) -> None:
    page.locator("nav.menu button.poz", has_text=pozycja).click()


def _cel_na_karcie_anny(page: Page, nazwa: str):
    _menu(page, "Pracownicy")
    page.get_by_text("Anna Zielińska-Demo").first.click()
    cel = page.locator(".cel", has_text=nazwa)
    cel.locator("button.cel-glowa").click()
    return cel


def test_propozycja_poprawka_i_akceptacja(przegladarka):
    nazwa = f"Prowadzenie spotkań zespołu {time.time_ns()}"  # unikalna przy ponownym użyciu bazy
    pracownik = _strona(przegladarka, URL, "oceniany")
    _menu(pracownik, "Twoje cele")
    pracownik.get_by_role("button", name="Dodaj cel", exact=True).click()
    pracownik.get_by_label("Cel", exact=True).fill(nazwa)
    pracownik.get_by_label("Miernik").fill("3 spotkania")
    pracownik.get_by_label("Termin").fill("30.06.2027")
    pracownik.get_by_role("button", name="Wyślij do akceptacji").click()
    moj = pracownik.locator(".cel", has_text=nazwa)
    expect(moj.locator(".status", has_text="do akceptacji")).to_be_visible()

    przelozony = _strona(przegladarka, URL, "przelozony1")
    cel = _cel_na_karcie_anny(przelozony, nazwa)
    cel.locator(".cel-akcje").get_by_role("button", name="Odeślij do poprawy", exact=True).click()
    cel.get_by_label("Co poprawić?").fill("Dodaj liczbę uczestników do miernika.")
    cel.locator(".cel-odrzucenie").get_by_role("button", name="Odeślij do poprawy", exact=True).click()
    expect(cel.locator(".status", has_text="do poprawy")).to_be_visible()

    pracownik.reload()
    _menu(pracownik, "Twoje cele")
    moj.locator("button.cel-glowa").click()
    expect(moj.locator(".cel-komentarz")).to_contain_text("Dodaj liczbę uczestników")
    moj.get_by_role("button", name="Popraw", exact=True).click()
    moj.get_by_label("Miernik").fill("3 spotkania, min. 5 osób")
    moj.get_by_role("button", name="Wyślij do akceptacji", exact=True).click()
    expect(moj.locator(".status", has_text="do akceptacji")).to_be_visible()

    przelozony.reload()
    cel = _cel_na_karcie_anny(przelozony, nazwa)
    cel.locator(".cel-akcje").get_by_role("button", name="Zatwierdź", exact=True).click()
    expect(cel.locator(".status", has_text="zatwierdzony")).to_be_visible()
    expect(cel.locator(".cel-historia li")).to_have_count(4)
    expect(cel.locator(".cel-historia li").nth(1)).to_contain_text("zmiana: miernik")


@pytest.mark.skipif(not URL_BEZ_EDYCJI, reason="brak serwera z cele-bez-edycji.yaml (KOMPAS_URL_BEZ_EDYCJI)")
def test_bez_edycji_pracownik_nie_widzi_formularza(przegladarka):
    nazwa = f"Szkolenie z AI Act {time.time_ns()}"
    przelozony = _strona(przegladarka, URL_BEZ_EDYCJI, "przelozony1")
    _menu(przelozony, "Pracownicy")
    przelozony.get_by_text("Anna Zielińska-Demo").first.click()
    przelozony.get_by_role("button", name="Dodaj cel", exact=True).click()
    przelozony.get_by_label("Cel", exact=True).fill(nazwa)
    przelozony.get_by_label("Miernik").fill("certyfikat")
    przelozony.get_by_label("Termin").fill("31.03.2027")
    przelozony.locator("form.cel-formularz").get_by_role("button", name="Dodaj cel").click()
    cel_p = przelozony.locator(".cel", has_text=nazwa)
    expect(cel_p.locator(".status", has_text="do akceptacji")).to_be_visible()  # akceptacja zawsze osobnym krokiem (#40)
    cel_p.locator(".cel-akcje").get_by_role("button", name="Zatwierdź", exact=True).click()
    expect(cel_p.locator(".status", has_text="zatwierdzony")).to_be_visible()

    pracownik = _strona(przegladarka, URL_BEZ_EDYCJI, "oceniany")
    _menu(pracownik, "Twoje cele")
    expect(pracownik.get_by_text("Cele ustala przełożony.")).to_be_visible()
    expect(pracownik.get_by_role("button", name="Dodaj cel", exact=True)).to_have_count(0)
    cel = pracownik.locator(".cel", has_text=nazwa)
    cel.locator("button.cel-glowa").click()
    expect(cel.get_by_role("button", name="Edytuj", exact=True)).to_have_count(0)
    cel.get_by_role("button", name="Rozpocznij realizację", exact=True).click()
    expect(cel.locator(".status", has_text="w realizacji")).to_be_visible()
