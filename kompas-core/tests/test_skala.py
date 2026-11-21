from decimal import Decimal

import pytest

from kompas_core.skala import (
    KonfiguracjaSkali,
    ProgPoziomu,
    RegulaWyniku,
    WarunekFaktu,
    WarunekLiczbyOcen,
    WarunekSredniej,
    oblicz_wynik,
)
from kompas_core.slad import Regula
from kompas_core.zrodla import Kategoria, SourceRef


def _regula(identyfikator: str) -> Regula:
    return Regula(
        id=identyfikator,
        zrodlo=SourceRef(
            kategoria=Kategoria.PRZEPIS,
            doc_id="dokument-syntetyczny",
            lokalizator=identyfikator,
            cytat_doslowny=f"Przykładowa reguła {identyfikator}.",
        ),
    )


def _dwa_progi(granica: Decimal, granica_w_gornym_progu: bool) -> tuple[ProgPoziomu, ...]:
    return (
        ProgPoziomu(
            "niski", _regula("prog-niski"), maksimum=granica,
            domkniety_od_gory=not granica_w_gornym_progu,
        ),
        ProgPoziomu(
            "wysoki", _regula("prog-wysoki"), minimum=granica,
            domkniety_od_dolu=granica_w_gornym_progu,
        ),
    )


@pytest.mark.parametrize(
    ("oceny", "granica", "domkniecie_gornego_progu", "poziom"),
    [
        ((2,), Decimal("2.5"), True, "niski"),
        ((2, 3), Decimal("2.5"), True, "wysoki"),
        ((2, 3), Decimal("2.5"), False, "niski"),
        ((3,), Decimal("2.5"), False, "wysoki"),
        ((2, 2, 3), Decimal("2.33"), False, "wysoki"),
    ],
    ids=["ponizej", "domkniety", "otwarty", "powyzej", "przed-zaokragleniem"],
)
def test_progi_klasyfikuja_srednia_przed_zaokragleniem(
    oceny, granica, domkniecie_gornego_progu, poziom
):
    konfiguracja = KonfiguracjaSkali(
        dozwolone_oceny=(2, 3),
        regula_sredniej=_regula("srednia"),
        wynik_domyslny="ok",
        regula_domyslna=_regula("domyslna"),
        progi=_dwa_progi(granica, domkniecie_gornego_progu),
    )

    assert oblicz_wynik(oceny, konfiguracja).poziom == poziom


def test_niska_ocena_przesadza_o_wyniku_mimo_sredniej_6_6():
    regula_sredniej = _regula("srednia")
    regula_jedynki = _regula("ocena-1")
    progi = _dwa_progi(Decimal("6"), granica_w_gornym_progu=False)
    konfiguracja = KonfiguracjaSkali(
        dozwolone_oceny=(1, 3, 5, 7, 9),
        regula_sredniej=regula_sredniej,
        wynik_domyslny="pozytywna",
        regula_domyslna=_regula("domyslna"),
        progi=progi,
        reguly_rozstrzygajace=(
            RegulaWyniku(regula_jedynki, (WarunekLiczbyOcen(1, ">=", 1),), "negatywna"),
        ),
    )

    wynik = oblicz_wynik([1, 5, 9, 9, 9], konfiguracja)

    assert wynik.srednia == Decimal("6.6")
    assert wynik.poziom == "wysoki"
    assert wynik.wynik == "negatywna"
    assert wynik.regula_rozstrzygajaca.id == "ocena-1"
    zrodla_w_sladzie = {krok.regula.id: krok.regula.zrodlo for krok in wynik.slad}
    for regula in (regula_sredniej, progi[1].regula, regula_jedynki):
        assert zrodla_w_sladzie[regula.id] == regula.zrodlo


@pytest.fixture
def skala_trzystopniowa():
    return KonfiguracjaSkali(
        dozwolone_oceny=(3, 5, 7),
        regula_sredniej=_regula("srednia"),
        wynik_domyslny="pozytywna",
        regula_domyslna=_regula("domyslna"),
        reguly_rozstrzygajace=(
            RegulaWyniku(
                _regula("sprawozdanie"), (WarunekFaktu("sprawozdanie_na_czas", False),),
                "negatywna",
            ),
            RegulaWyniku(
                _regula("egzamin"),
                (WarunekFaktu("egzamin_zdany", False), WarunekFaktu("zwolnienie", False)),
                "negatywna",
            ),
            RegulaWyniku(
                _regula("liczba-trojek"), (WarunekLiczbyOcen(3, ">", 1),), "negatywna",
            ),
            RegulaWyniku(
                _regula("prog-sredniej"), (WarunekSredniej("<", Decimal("5")),), "negatywna",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("oceny", "sprawozdanie_na_czas", "egzamin_zdany", "zwolnienie", "srednia", "wynik", "regula"),
    [
        ((3, 3, 5, 7, 7), True, True, False, Decimal("5.0"), "negatywna", "liczba-trojek"),
        ((5, 7), False, False, False, Decimal("6"), "negatywna", "sprawozdanie"),
        ((5, 7), True, False, False, Decimal("6"), "negatywna", "egzamin"),
        ((3, 5), True, True, False, Decimal("4"), "negatywna", "prog-sredniej"),
        ((3, 5, 5, 5, 7), True, False, True, Decimal("5"), "pozytywna", "domyslna"),
    ],
    ids=["dwie-trojki", "pierwsza-pasujaca-regula", "egzamin", "srednia-ponizej-5", "zwolnienie"],
)
def test_skala_trzystopniowa_korzysta_z_konfiguracji_i_faktow(
    skala_trzystopniowa, oceny, sprawozdanie_na_czas, egzamin_zdany, zwolnienie,
    srednia, wynik, regula,
):
    rezultat = oblicz_wynik(
        oceny,
        skala_trzystopniowa,
        fakty={
            "sprawozdanie_na_czas": sprawozdanie_na_czas,
            "egzamin_zdany": egzamin_zdany,
            "zwolnienie": zwolnienie,
        },
    )

    assert rezultat.srednia == srednia
    assert rezultat.poziom is None
    assert rezultat.wynik == wynik
    assert rezultat.regula_rozstrzygajaca.id == regula


@pytest.mark.parametrize("oceny", [(), (3, 4)], ids=["pusta-lista", "ocena-spoza-skali"])
def test_skala_odrzuca_nieprawidlowe_oceny(skala_trzystopniowa, oceny):
    fakty = {"sprawozdanie_na_czas": True, "egzamin_zdany": True, "zwolnienie": False}
    with pytest.raises(ValueError):
        oblicz_wynik(oceny, skala_trzystopniowa, fakty=fakty)


def test_skala_wymaga_faktow_z_konfiguracji(skala_trzystopniowa):
    with pytest.raises(ValueError):
        oblicz_wynik(
            (5, 7), skala_trzystopniowa,
            fakty={"sprawozdanie_na_czas": True, "egzamin_zdany": False},
        )
