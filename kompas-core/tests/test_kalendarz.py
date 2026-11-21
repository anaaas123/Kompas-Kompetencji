from datetime import date

import pytest

from kompas_core.kalendarz import Okres, RegulaTerminu, polacz_nieobecnosci, wyznacz_termin
from kompas_core.slad import Regula
from kompas_core.zrodla import Kategoria, SourceRef


@pytest.fixture
def regula() -> Regula:
    return Regula(
        "test-kalendarza",
        SourceRef(kategoria=Kategoria.BRAK_ZRODLA, uzasadnienie="Reguła syntetyczna do testu."),
    )


@pytest.mark.parametrize(
    ("zdarzenie", "miesiace", "oczekiwana"),
    [
        (date(2024, 1, 31), 13, date(2025, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2024, 3, 16), 24, date(2026, 3, 16)),
        (date(2024, 1, 31), 2, date(2024, 3, 31)),
        (date(2024, 3, 31), -1, date(2024, 2, 29)),
    ],
)
def test_termin_miesieczny(zdarzenie, miesiace, oczekiwana, regula):
    wynik = wyznacz_termin(zdarzenie, RegulaTerminu(miesiace, "miesiace", regula))

    assert wynik.data == oczekiwana
    assert wynik.slad[0].regula.zrodlo is regula.zrodlo


@pytest.mark.parametrize(
    ("zdarzenie", "dni", "oczekiwana"),
    [
        (date(2025, 3, 1), 7, date(2025, 3, 8)),
        (date(2025, 3, 8), -7, date(2025, 3, 1)),
        (date(2025, 3, 1), 0, date(2025, 3, 1)),
    ],
)
def test_termin_dzienny_bez_przesuwania_dni_wolnych(zdarzenie, dni, oczekiwana, regula):
    wynik = wyznacz_termin(
        zdarzenie, RegulaTerminu(dni, "dni", regula), dni_wolne={oczekiwana}
    )

    assert wynik.data == oczekiwana
    assert wynik.slad[0].regula.zrodlo is regula.zrodlo


@pytest.mark.parametrize(
    ("zdarzenie", "dni_wolne", "oczekiwana"),
    [
        (date(2025, 3, 1), set(), date(2025, 3, 10)),
        (date(2026, 3, 1), set(), date(2026, 3, 9)),
        (date(2025, 3, 1), {date(2025, 3, 10)}, date(2025, 3, 11)),
    ],
)
def test_termin_przesuniety_na_nastepny_dzien_roboczy(zdarzenie, dni_wolne, oczekiwana, regula):
    przesuniecie = Regula(
        "test-dnia-roboczego",
        SourceRef(kategoria=Kategoria.BRAK_ZRODLA, uzasadnienie="Osobna reguła syntetyczna."),
    )
    wynik = wyznacz_termin(
        zdarzenie, RegulaTerminu(7, "dni", regula, przesuniecie), dni_wolne=dni_wolne
    )

    assert wynik.data == oczekiwana
    assert wynik.slad[0].regula.zrodlo is regula.zrodlo
    assert any(krok.regula.zrodlo is przesuniecie.zrodlo for krok in wynik.slad[1:])


def test_dzien_wolny_nie_przerywa_nieobecnosci(regula):
    pierwszy = Okres(date(2024, 10, 5), date(2024, 10, 31))
    drugi = Okres(date(2024, 11, 2), date(2024, 11, 6))

    wynik = polacz_nieobecnosci(
        iter((drugi, pierwszy)), regula=regula, dni_wolne={date(2024, 11, 1)}
    )

    assert wynik.okresy == (Okres(pierwszy.od, drugi.do),)
    assert wynik.slad
    assert all(krok.regula.zrodlo is regula.zrodlo for krok in wynik.slad)


def test_nakladanie_styk_weekend_i_przerwa_w_dniu_roboczym(regula):
    okresy = [
        Okres(date(2025, 3, 12), date(2025, 3, 12)),
        Okres(date(2025, 3, 10), date(2025, 3, 10)),
        Okres(date(2025, 3, 6), date(2025, 3, 7)),
        Okres(date(2025, 3, 4), date(2025, 3, 5)),
        Okres(date(2025, 3, 4), date(2025, 3, 4)),
        Okres(date(2025, 3, 3), date(2025, 3, 4)),
    ]

    wynik = polacz_nieobecnosci(okresy, regula=regula)

    assert wynik.okresy == (
        Okres(date(2025, 3, 3), date(2025, 3, 10)),
        Okres(date(2025, 3, 12), date(2025, 3, 12)),
    )


def test_odwrocony_okres_jest_bledem(regula):
    with pytest.raises(ValueError):
        polacz_nieobecnosci([Okres(date(2025, 3, 2), date(2025, 3, 1))], regula=regula)
