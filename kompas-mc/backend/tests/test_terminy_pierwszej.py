from datetime import date
from pathlib import Path

import pytest

from kompas_mc.qnt import MockQnt, Nieobecnosc, Pracownik
from kompas_mc.terminy_pierwszej import (
    DaneTerminowPierwszej,
    KonfiguracjaTerminowPierwszej,
    PrzedluzeniePierwszej,
    oblicz_terminy_pierwszej,
)


KONFIGURACJA = Path(__file__).resolve().parents[2] / "konfiguracja"


@pytest.fixture(scope="module")
def konf() -> KonfiguracjaTerminowPierwszej:
    return KonfiguracjaTerminowPierwszej.z_pliku(KONFIGURACJA / "terminy-pierwszej.yaml")


@pytest.fixture(scope="module")
def qnt() -> MockQnt:
    return MockQnt.z_pliku(KONFIGURACJA / "qnt.yaml")


@pytest.fixture
def pracownik(qnt: MockQnt) -> Pracownik:
    osoba = qnt.pracownik("P-201")
    assert osoba is not None
    return osoba


def test_okno_pierwszej_oceny_jak_w_przykladzie_poradnika(pracownik, konf):
    osoba = pracownik.model_copy(update={"data_zatrudnienia": date(2015, 9, 1), "pierwsza_ocena": None})
    dane = DaneTerminowPierwszej(data_konca_zatrudnienia=date(2016, 8, 31))

    wynik = oblicz_terminy_pierwszej(osoba, dane, konf)

    assert wynik.termin_rozmowy_wstepnej.data == date(2015, 9, 22)
    assert wynik.pierwsza_ocena_od.data == date(2016, 5, 2)
    assert wynik.pierwsza_ocena_do.data == date(2016, 7, 30)
    assert wynik.pierwsza_ocena_do.slad[-1].regula.zrodlo.strona == 9


def test_bez_dat_umowy_lub_sprawozdania_zwraca_dostepne_terminy(pracownik, konf):
    osoba = pracownik.model_copy(update={"data_zatrudnienia": date(2026, 1, 31)})
    wynik = oblicz_terminy_pierwszej(osoba, DaneTerminowPierwszej(), konf)

    assert wynik.data_rozmowy_wstepnej == date(2026, 3, 16)
    assert wynik.pierwsza_ocena_od.data == date(2026, 10, 1)
    assert wynik.pierwsza_ocena_do is None
    assert wynik.termin_sprawozdania_od.data == date(2026, 10, 1)
    assert wynik.termin_sprawozdania_do is None
    assert wynik.sprawozdanie_w_terminie is None
    assert wynik.sprawozdanie_min_7_miesiecy is None
    assert any("końca zatrudnienia" in brak for brak in wynik.braki)


@pytest.mark.parametrize(("zlozenie", "w_terminie"), [
    (date(2026, 11, 3), False), (date(2026, 11, 4), True),
    (date(2026, 12, 1), True), (date(2026, 12, 2), False),
])
def test_sprawozdanie_w_terminie_od_i_do(pracownik, konf, zlozenie, w_terminie):
    dane = DaneTerminowPierwszej(
        data_konca_zatrudnienia=date(2027, 3, 1),
        termin_sprawozdania_od=date(2026, 11, 4),
        wyznaczony_termin_sprawozdania=date(2026, 12, 1),
        data_zlozenia_sprawozdania=zlozenie,
        sprawozdanie_okres_od=date(2026, 3, 2),
        sprawozdanie_okres_do=date(2026, 10, 2),
    )

    wynik = oblicz_terminy_pierwszej(pracownik, dane, konf)

    assert wynik.sprawozdanie_w_terminie is w_terminie
    assert wynik.sprawozdanie_min_7_miesiecy is True
    assert {krok.regula.zrodlo.lokalizator for krok in wynik.slad} >= {"§ 6 ust. 1", "§ 10 ust. 1 pkt 2"}


def test_jawne_niezlozenie_nie_usuwa_terminu(pracownik, konf):
    dane = DaneTerminowPierwszej(
        data_konca_zatrudnienia=date(2027, 3, 1),
        wyznaczony_termin_sprawozdania=date(2026, 12, 1),
        sprawozdanie_niezlozone=True,
    )

    wynik = oblicz_terminy_pierwszej(pracownik, dane, konf)

    assert wynik.termin_sprawozdania_od.data == date(2026, 11, 3)
    assert wynik.termin_sprawozdania_do.data == date(2026, 12, 1)
    assert wynik.sprawozdanie_w_terminie is False
    assert wynik.sprawozdanie_min_7_miesiecy is None
    assert wynik.braki == ()


def test_zastepstwo_liczy_rozmowe_od_ustalenia_i_przedluzenie_o_19_dni_z_qnt(qnt, konf):
    osoba = qnt.pracownik("P-204")
    assert osoba is not None
    dane = DaneTerminowPierwszej(
        data_ustalenia_oceny_zastepstwa=date(2026, 1, 20),
        data_konca_zatrudnienia=date(2026, 12, 31),
        wyznaczony_termin_sprawozdania=date(2026, 10, 10),
        przedluzenie=PrzedluzeniePierwszej(
            przyczyna="usprawiedliwiona_nieobecnosc",
            data_zawiadomienia=date(2026, 9, 20),
            nowy_termin=date(2026, 10, 29),
        ),
        data_zlozenia_sprawozdania=date(2026, 10, 29),
        sprawozdanie_okres_od=date(2026, 1, 12),
        sprawozdanie_okres_do=date(2026, 8, 31),
    )

    wynik = oblicz_terminy_pierwszej(osoba, dane, konf)

    assert wynik.termin_rozmowy_wstepnej.data == date(2026, 2, 10)
    assert wynik.termin_sprawozdania_od.data == date(2026, 9, 13)
    assert wynik.termin_sprawozdania_bazowy_do.data == date(2026, 10, 10)
    assert wynik.termin_sprawozdania_do.data == date(2026, 10, 29)
    assert wynik.sprawozdanie_w_terminie is True
    assert wynik.sprawozdanie_min_7_miesiecy is True
    assert wynik.braki == ()
    assert {krok.regula.zrodlo.lokalizator for krok in wynik.termin_sprawozdania_do.slad} >= {
        "§ 5 ust. 1", "§ 5 ust. 3", "§ 5 ust. 4",
    }
    assert konf.zrodlo_przedluzenia.lokalizator == "§ 5 ust. 4"


def test_zastepstwo_bez_daty_ustalenia_nie_dziedziczy_daty_zatrudnienia(qnt, konf):
    osoba = qnt.pracownik("P-204")
    assert osoba is not None

    wynik = oblicz_terminy_pierwszej(osoba, DaneTerminowPierwszej(), konf)

    assert wynik.termin_rozmowy_wstepnej is None
    assert wynik.data_rozmowy_wstepnej == date(2026, 1, 26)
    assert any("zastępstwo" in brak for brak in wynik.braki)


def test_przedluzona_umowa_zachowuje_pierwotne_i_nowe_okno(pracownik, konf):
    dane = DaneTerminowPierwszej(
        data_konca_zatrudnienia=date(2027, 7, 1),
        termin_sprawozdania_od=date(2026, 11, 4),
        wyznaczony_termin_sprawozdania=date(2026, 12, 1),
        przedluzenie=PrzedluzeniePierwszej(
            przyczyna="przedluzenie_umowy", data_zawiadomienia=date(2026, 11, 25),
            nowy_termin_od=date(2027, 1, 4), nowy_termin=date(2027, 2, 1),
        ),
        data_zlozenia_sprawozdania=date(2026, 11, 30),
    )

    wynik = oblicz_terminy_pierwszej(pracownik, dane, konf)

    assert wynik.pierwsza_ocena_do.data == date(2027, 5, 31)
    assert wynik.termin_sprawozdania_bazowy_od.data == date(2026, 11, 4)
    assert wynik.termin_sprawozdania_od.data == date(2027, 1, 4)
    assert wynik.termin_sprawozdania_do.data == date(2027, 2, 1)
    assert wynik.sprawozdanie_w_terminie is False
    assert konf.zrodlo_przyczyny(dane.przedluzenie.przyczyna).lokalizator == "§ 5 ust. 2"


@pytest.mark.parametrize(("nowy_termin", "blad"), [
    (date(2026, 12, 2), "Przedłużenie o 2 dni daje termin 2026-12-03"),
    (date(2027, 2, 1), "musi umożliwić dokonanie pierwszej oceny"),
])
def test_bledny_termin_przedluzenia_jest_odrzucany(pracownik, konf, nowy_termin, blad):
    dane = DaneTerminowPierwszej(
        data_konca_zatrudnienia=date(2027, 3, 1), wyznaczony_termin_sprawozdania=date(2026, 12, 1),
        przedluzenie=PrzedluzeniePierwszej(
            przyczyna="obowiazki_poza_miejscem_pracy", data_zawiadomienia=date(2026, 11, 30),
            nowy_termin=nowy_termin, okres_od=date(2026, 11, 24), okres_do=date(2026, 11, 25),
        ),
    )

    with pytest.raises(ValueError, match=blad):
        oblicz_terminy_pierwszej(pracownik, dane, konf)


def test_sprawozdanie_mierzy_przepracowany_okres_po_odjeciu_nieobecnosci(pracownik, konf):
    osoba = pracownik.model_copy(update={"nieobecnosci": [
        Nieobecnosc(od=date(2026, 4, 7), do=date(2026, 4, 8), rodzaj="usprawiedliwiona"),
        Nieobecnosc(od=date(2026, 4, 8), do=date(2026, 4, 9), rodzaj="usprawiedliwiona"),
    ]})
    dane = DaneTerminowPierwszej(
        sprawozdanie_okres_od=date(2026, 3, 2), sprawozdanie_okres_do=date(2026, 10, 4),
    )

    za_krotkie = oblicz_terminy_pierwszej(osoba, dane, konf)
    wystarczajace = oblicz_terminy_pierwszej(
        osoba, dane.model_copy(update={"sprawozdanie_okres_do": date(2026, 10, 5)}), konf,
    )

    assert za_krotkie.sprawozdanie_min_7_miesiecy is False
    assert wystarczajace.sprawozdanie_min_7_miesiecy is True


def test_przedluzenie_wymaga_konca_zatrudnienia(pracownik, konf):
    dane = DaneTerminowPierwszej(
        wyznaczony_termin_sprawozdania=date(2026, 12, 1),
        przedluzenie=PrzedluzeniePierwszej(
            przyczyna="przedluzenie_umowy",
            data_zawiadomienia=date(2026, 11, 30),
            nowy_termin=date(2026, 12, 3),
        ),
    )
    with pytest.raises(ValueError, match="datę końca zatrudnienia"):
        oblicz_terminy_pierwszej(pracownik, dane, konf)
