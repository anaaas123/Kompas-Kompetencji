"""Obliczanie poziomu i wyniku według konfiguracji wersji."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from operator import eq, ge, gt, le, lt, ne
from typing import Literal

from .slad import KrokObliczenia, Regula

OperatorPorownania = Literal["<", "<=", "==", "!=", ">=", ">"]
_OPERATORY = {"<": lt, "<=": le, "==": eq, "!=": ne, ">=": ge, ">": gt}


@dataclass(frozen=True, slots=True)
class ProgPoziomu:
    """Przedział średniej przypisany do poziomu skali."""

    poziom: str
    regula: Regula
    minimum: Decimal | None = None
    maksimum: Decimal | None = None
    domkniety_od_dolu: bool = True
    domkniety_od_gory: bool = True


@dataclass(frozen=True, slots=True)
class WarunekLiczbyOcen:
    ocena: int
    operator: OperatorPorownania
    liczba: int


@dataclass(frozen=True, slots=True)
class WarunekSredniej:
    operator: OperatorPorownania
    wartosc: Decimal


@dataclass(frozen=True, slots=True)
class WarunekFaktu:
    nazwa: str
    wartosc: bool


Warunek = WarunekLiczbyOcen | WarunekSredniej | WarunekFaktu


@dataclass(frozen=True, slots=True)
class RegulaWyniku:
    """Reguła pasuje, gdy wszystkie jej warunki są spełnione."""

    regula: Regula
    warunki: tuple[Warunek, ...]
    wynik: str


@dataclass(frozen=True, slots=True)
class KonfiguracjaSkali:
    dozwolone_oceny: tuple[int, ...]
    regula_sredniej: Regula
    wynik_domyslny: str
    regula_domyslna: Regula
    progi: tuple[ProgPoziomu, ...] = ()
    reguly_rozstrzygajace: tuple[RegulaWyniku, ...] = ()


@dataclass(frozen=True, slots=True)
class WynikSkali:
    srednia: Decimal
    poziom: str | None
    wynik: str
    regula_rozstrzygajaca: Regula
    slad: tuple[KrokObliczenia, ...]


def oblicz_wynik(
    oceny: Sequence[int],
    konfiguracja: KonfiguracjaSkali,
    *,
    fakty: Mapping[str, bool] | None = None,
) -> WynikSkali:
    """Oblicz średnią, poziom i wynik oraz zwróć regułę rozstrzygającą.

    Progi i warunki korzystają ze średniej przed zaokrągleniem do prezentacji.
    Poziom jest opcjonalny, jeśli konfiguracja nie definiuje progów. Wynik
    określa pierwsza pasująca reguła w kolejności konfiguracji, a gdy brak
    dopasowania, reguła domyślna. Alternatywne warunki o tym samym wyniku można
    zapisać jako osobne reguły. Puste lub niedozwolone oceny i brak wymaganych
    faktów zgłaszają ``ValueError``.
    """
    if not oceny:
        raise ValueError("Podaj co najmniej jedną ocenę cząstkową.")
    for ocena in oceny:
        if type(ocena) is not int or ocena not in konfiguracja.dozwolone_oceny:
            raise ValueError(f"Niedozwolona ocena cząstkowa {ocena!r}.")

    suma = sum(oceny)
    liczba = len(oceny)
    srednia_dokladna = Fraction(suma, liczba)
    with localcontext(Context(prec=28)):
        srednia = Decimal(suma) / Decimal(liczba)
    slad = [KrokObliczenia(
        konfiguracja.regula_sredniej,
        f"Średnia z {liczba} ocen to {suma}/{liczba} = {srednia}.",
    )]

    poziom = None
    if konfiguracja.progi:
        dopasowane = [prog for prog in konfiguracja.progi if _w_przedziale(srednia_dokladna, prog)]
        if len(dopasowane) != 1:
            raise ValueError(f"Średnia {srednia} pasuje do {len(dopasowane)} progów poziomu. Wymagany jest jeden.")
        prog = dopasowane[0]
        poziom = prog.poziom
        slad.append(KrokObliczenia(prog.regula, f"Średnia mieści się w progu poziomu „{poziom}”."))

    liczebnosci = Counter(oceny)
    znane_fakty = {} if fakty is None else fakty
    for regula in konfiguracja.reguly_rozstrzygajace:
        warunki = []
        for warunek in regula.warunki:
            spelniony, opis = _sprawdz_warunek(warunek, liczebnosci, srednia_dokladna, znane_fakty)
            if not spelniony:
                slad.append(KrokObliczenia(regula.regula, f"Warunek niespełniony ({opis})."))
                break
            warunki.append(opis)
        else:
            uzasadnienie = ", ".join(warunki) or "reguła bez warunków"
            slad.append(KrokObliczenia(regula.regula, f"Ustalono wynik „{regula.wynik}” ({uzasadnienie})."))
            return WynikSkali(srednia, poziom, regula.wynik, regula.regula, tuple(slad))

    domyslny = konfiguracja.wynik_domyslny
    regula_domyslna = konfiguracja.regula_domyslna
    slad.append(KrokObliczenia(regula_domyslna, f"Zastosowano wynik domyślny „{domyslny}”."))
    return WynikSkali(srednia, poziom, domyslny, regula_domyslna, tuple(slad))


def _w_przedziale(srednia: Fraction, prog: ProgPoziomu) -> bool:
    if prog.minimum is not None:
        minimum = Fraction(prog.minimum)
        if srednia < minimum or (srednia == minimum and not prog.domkniety_od_dolu):
            return False
    if prog.maksimum is not None:
        maksimum = Fraction(prog.maksimum)
        if srednia > maksimum or (srednia == maksimum and not prog.domkniety_od_gory):
            return False
    return True


def _sprawdz_warunek(
    warunek: Warunek,
    liczebnosci: Counter[int],
    srednia: Fraction,
    fakty: Mapping[str, bool],
) -> tuple[bool, str]:
    if isinstance(warunek, WarunekFaktu):
        if warunek.nazwa not in fakty:
            raise ValueError(f"Brak wymaganego faktu {warunek.nazwa!r}.")
        wartosc = fakty[warunek.nazwa]
        if not isinstance(wartosc, bool):
            raise ValueError(f"Fakt {warunek.nazwa!r} musi mieć wartość logiczną.")
        return wartosc == warunek.wartosc, f"{warunek.nazwa} = {wartosc}, oczekiwano {warunek.wartosc}"

    porownaj = _OPERATORY.get(warunek.operator)
    if porownaj is None:
        raise ValueError(f"Nieznany operator {warunek.operator!r}.")
    if isinstance(warunek, WarunekLiczbyOcen):
        liczba = liczebnosci[warunek.ocena]
        opis = f"liczba ocen {warunek.ocena} pkt wynosi {liczba}, warunek {warunek.operator} {warunek.liczba}"
        return porownaj(liczba, warunek.liczba), opis

    opis = f"średnia {srednia} wobec warunku {warunek.operator} {warunek.wartosc}"
    return porownaj(srednia, Fraction(warunek.wartosc)), opis
