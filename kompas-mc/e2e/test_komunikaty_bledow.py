"""Test Playwright #76: komunikat błędu pokazuje powód z API, a nie stałe „Proces oceny tej osoby już trwa”.

Sprawdza `opisBledu` z modułu aplikacji w przeglądarce (serwer deweloperski Vite) oraz prawdziwy 409
przy drugim procesie tej samej osoby. Uruchomienie i zmienne jak w test_samoocena.py.
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
API = os.environ.get("KOMPAS_API", "http://127.0.0.1:8002")


@pytest.fixture(scope="module")
def strona():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        page = b.new_page()
        page.goto(URL)
        yield p, page
        b.close()


def opis(page, status: int, detail) -> str:
    return page.evaluate(
        """async ([status, detail]) => {
            const { BladApi } = await import("/src/api.ts");
            const { opisBledu } = await import("/src/Krok1.tsx");
            return opisBledu(new BladApi(status, detail));
        }""",
        [status, detail],
    )


def test_opis_bledu_bierze_powod_z_api(strona):
    p, page = strona
    ctx = p.request.new_context()
    h = {"authorization": "Bearer " + ctx.post(f"{API}/api/auth/login", data={"login": "przelozony1", "hasło": "demo"}).json()["token"]}
    nowy = {"osoba_id": "P-104", "sciezka": "okresowa"}
    ctx.post(f"{API}/api/procesy", headers=h, data=nowy)
    duplikat = ctx.post(f"{API}/api/procesy", headers=h, data=nowy)
    assert duplikat.status == 409
    assert opis(page, 409, duplikat.json()["detail"]) == "Ta osoba ma już proces oceny w toku"
    ctx.dispose()

    assert opis(page, 409, "Proces nie jest w toku.") == "Proces nie jest w toku."
    assert opis(page, 422, {"komunikat": "Uzupełnij dane pierwszej oceny.", "braki": []}) == "Uzupełnij dane pierwszej oceny."
    assert opis(page, 409, None) == "Tej czynności nie można teraz wykonać."
    assert opis(page, 403, "Brak uprawnienia") == "Nie masz uprawnień do tej czynności."
