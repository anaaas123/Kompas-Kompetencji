from datetime import date
from pathlib import Path

import pytest

from kompas_mc.qnt import MockQnt
from kompas_mc.terminy_okresowej import (
    DaneTerminow,
    KonfiguracjaTerminow,
    ZmianaStanowiska,
    ZmianaTerminu,
    oblicz_terminy,
)


@pytest.fixture(scope="module")
def terminy_config():
    konfiguracja = Path(__file__).resolve().parents[2] / "konfiguracja"
    return (
        MockQnt.z_pliku(konfiguracja / "qnt.yaml"),
        KonfiguracjaTerminow.z_pliku(konfiguracja / "terminy-okresowej.yaml"),
    )


def test_zwykly_cykl_i_sprzeciw_od_zapoznania(terminy_config):
    qnt, konf = terminy_config
    dane = DaneTerminow(
        data_sporzadzenia_oceny=date(2026, 11, 9), data_zapoznania_z_ocena=date(2026, 11, 13),
    )
    wynik = oblicz_terminy(qnt.pracownik("P-101"), dane, konf)

    assert wynik.termin_kryteriow.data == date(2025, 1, 2)  # 1.01 to Nowy Rok (dni_wolne), termin przesuwa się
    assert wynik.termin_kryteriow.slad[0].regula.zrodlo.lokalizator == "§ 7 pkt 1"
    assert wynik.termin_bazowy.data == date(2026, 12, 2)
    assert wynik.termin_sprzeciwu.data == date(2026, 11, 20)
    assert wynik.termin_sprzeciwu.slad[0].regula.zrodlo.strona == 32


def test_pierwsza_okresowa_i_przesuniecie_z_niedzieli_i_skatalogowanego_swieta(terminy_config):
    qnt, konf = terminy_config
    konf = konf.model_copy(update={"dni_wolne": frozenset({date(2026, 10, 5)})})
    osoba = qnt.pracownik("P-101").model_copy(
        update={"ostatnia_ocena_okresowa": None, "data_zatrudnienia": date(2026, 9, 4)},
    )
    wynik = oblicz_terminy(osoba, DaneTerminow(), konf)

    assert wynik.termin_kryteriow.data == date(2026, 10, 6)
    assert [krok.regula.zrodlo.strona for krok in wynik.termin_kryteriow.slad] == [2, 9, 9]
    assert wynik.termin_bazowy.data == date(2028, 9, 4)


def test_negatywna_ma_7_dni_na_kryteria_i_powtorke_od_zapoznania(terminy_config):
    qnt, konf = terminy_config
    z_akt = qnt.pracownik("P-102")
    osoba = z_akt.model_copy(update={
        "ostatnia_ocena_okresowa": z_akt.ostatnia_ocena_okresowa.model_copy(update={"data_zapoznania": None}),
    })

    niepelny = oblicz_terminy(osoba, DaneTerminow(), konf)
    assert niepelny.termin_kryteriow.data == date(2026, 11, 23)
    assert niepelny.termin_kryteriow.slad[0].regula.zrodlo.lokalizator == "§ 7 pkt 2"
    assert niepelny.termin_bazowy is None
    assert niepelny.braki

    dane = DaneTerminow(data_zapoznania_z_poprzednia_ocena=date(2026, 11, 19))
    wynik = oblicz_terminy(osoba, dane, konf)
    assert wynik.termin_bazowy.data == date(2027, 5, 20)
    assert not wynik.braki

    # Bez daty w formularzu: data zapoznania z arkusza w aktach osobowych (kartoteka QNT, demo 18.11.2026).
    assert z_akt.ostatnia_ocena_okresowa.data_zapoznania == date(2026, 11, 18)
    z_kartoteki = oblicz_terminy(z_akt, DaneTerminow(), konf)
    assert z_kartoteki.termin_bazowy.data == date(2027, 5, 19) and not z_kartoteki.braki
    # Formularz kroku 7 ma pierwszeństwo przed kartoteką.
    assert oblicz_terminy(z_akt, dane, konf).termin_bazowy.data == date(2027, 5, 20)


def test_zmiana_stanowiska_przed_uplywem_pol_roku(terminy_config):
    qnt, konf = terminy_config
    dane = DaneTerminow(
        zmiana_stanowiska=ZmianaStanowiska(data=date(2025, 5, 13), istotna_zmiana_obowiazkow=True),
    )
    wynik = oblicz_terminy(qnt.pracownik("P-101"), dane, konf)

    assert wynik.ponowne_kryteria.data == date(2025, 6, 12)
    assert wynik.ponowne_kryteria.slad[0].regula.zrodlo.lokalizator == "§ 9 ust. 1"
    assert wynik.okno_zmiany_stanowiska is None
    assert wynik.termin_sporzadzenia_oceny.data == date(2026, 12, 2)


def test_zmiana_stanowiska_po_uplywie_pol_roku_wyznacza_okno(terminy_config):
    qnt, konf = terminy_config
    dane = DaneTerminow(
        zmiana_stanowiska=ZmianaStanowiska(data=date(2025, 7, 14), istotna_zmiana_obowiazkow=True),
    )
    wynik = oblicz_terminy(qnt.pracownik("P-101"), dane, konf)

    assert wynik.okno_zmiany_stanowiska.od.data == date(2025, 7, 7)
    assert wynik.okno_zmiany_stanowiska.do.data == date(2025, 8, 13)
    assert wynik.okno_zmiany_stanowiska.do.slad[0].regula.zrodlo.lokalizator == "§ 9 ust. 2"
    assert wynik.termin_sporzadzenia_oceny.data == date(2025, 8, 13)


def test_zmiana_oceniajacego_zachowuje_kryteria(terminy_config):
    qnt, konf = terminy_config
    wynik = oblicz_terminy(qnt.pracownik("P-103"), DaneTerminow(), konf)

    assert wynik.zachowaj_kryteria
    assert wynik.slad[0].regula.zrodlo.lokalizator == "§ 9 ust. 3"
    assert wynik.termin_sporzadzenia_oceny.data == date(2027, 6, 30)


def test_zawiadomienie_po_fakultatywnej_zmianie(terminy_config):
    qnt, konf = terminy_config
    dane = DaneTerminow(
        zmiana_terminu=ZmianaTerminu(
            nowy_termin=date(2026, 11, 30), data_zawiadomienia=date(2026, 11, 18),
            przyczyna="wniosek_ocenianego",
        ),
    )
    wynik = oblicz_terminy(qnt.pracownik("P-101"), dane, konf)

    assert wynik.termin_bazowy.data == date(2026, 12, 2)
    assert wynik.termin_sporzadzenia_oceny.data == date(2026, 11, 30)
    assert wynik.termin_sporzadzenia_oceny.slad[-1].regula.zrodlo == konf.zrodlo_zmiany


def test_fakultatywna_zmiana_wymaga_uplywu_wiecej_niz_6_miesiecy(terminy_config):
    qnt, konf = terminy_config
    dane = DaneTerminow(
        zmiana_terminu=ZmianaTerminu(
            nowy_termin=date(2026, 11, 30), data_zawiadomienia=date(2025, 6, 2),
            przyczyna="wniosek_ocenianego",
        ),
    )

    with pytest.raises(ValueError, match="więcej niż 6 miesięcy"):
        oblicz_terminy(qnt.pracownik("P-101"), dane, konf)
