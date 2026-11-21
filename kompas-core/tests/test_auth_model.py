from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from kompas_core.auth import KonfiguracjaRol, Konto, WpisDziennika

KONFIG = {
    "konta": [{"login": "p1", "hasło": "demo", "rola": "przelozony", "osoba_id": "P1"}],
    "uprawnienia": {"przelozony": ["czytaj"], "administrator": ["*"]},
    "reguły_dostępu": [{"zasób": "pracownik", "rola": "przelozony", "pole": "przelozony_id"}],
}


def test_konfiguracja_kluczami_ze_specyfikacji():
    k = KonfiguracjaRol.model_validate(KONFIG)
    assert k.konta[0].haslo == "demo"
    assert k.reguly_dostepu[0].zasob == "pracownik"
    assert k.reguly_dostepu[0].pole_uzytkownika == "osoba_id"


def test_konto_przyjmuje_obie_formy_i_zwraca_klucz_ze_specyfikacji():
    konto = Konto(login="p1", haslo="demo", rola="przelozony")
    assert konto.model_dump(by_alias=True, exclude_none=True) == {
        "login": "p1",
        "hasło": "demo",
        "rola": "przelozony",
    }


def test_nieznany_klucz_w_konfiguracji_jest_bledem():
    with pytest.raises(ValidationError):
        KonfiguracjaRol.model_validate({**KONFIG, "reguly": []})


def test_wpis_dziennika_kluczami_ze_specyfikacji():
    wpis = WpisDziennika(
        id=1,
        czas=datetime(2026, 11, 21, tzinfo=UTC),
        autor="p1",
        zasob="ocena",
        zasob_id="O1",
        roznica={"wynik": {"przed": None, "po": 5}},
        wersja_regul="2016",
    )
    dane = wpis.model_dump(by_alias=True)
    assert dane["różnica"] == {"wynik": {"przed": None, "po": 5}}
    assert dane["wersja_reguł"] == "2016"
