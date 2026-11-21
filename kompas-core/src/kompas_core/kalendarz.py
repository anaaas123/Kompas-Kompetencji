"""Liczenie terminów i ciągłości nieobecności według konfiguracji wersji."""

from calendar import monthrange
from collections.abc import Iterable, Set
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from .slad import KrokObliczenia, Regula


@dataclass(frozen=True, slots=True)
class Okres:
    """Okres z włączonym dniem początku i końca."""

    od: date
    do: date


@dataclass(frozen=True, slots=True)
class RegulaTerminu:
    """Przesunięcie w dniach lub miesiącach, także wstecz."""

    liczba: int
    jednostka: Literal["dni", "miesiace"]
    regula: Regula
    przesuniecie_dnia_wolnego: Regula | None = None


@dataclass(frozen=True, slots=True)
class WynikTerminu:
    data: date
    slad: tuple[KrokObliczenia, ...]


@dataclass(frozen=True, slots=True)
class WynikPolaczeniaNieobecnosci:
    okresy: tuple[Okres, ...]
    slad: tuple[KrokObliczenia, ...]


def wyznacz_termin(
    data_zdarzenia: date,
    konfiguracja: RegulaTerminu,
    *,
    dni_wolne: Set[date] = frozenset(),
) -> WynikTerminu:
    """Policz odstęp od daty zdarzenia i zwróć zastosowane kroki.

    Przy odstępie w dniach dzień zdarzenia ma numer zero. W miesiącach
    zachowaj dzień miesiąca lub użyj ostatniego dnia miesiąca docelowego.
    Gdy skonfigurowano przesunięcie na dzień roboczy, pomiń soboty, niedziele
    i podane dni wolne, zapisując przesunięcie jako osobny krok.
    """
    if konfiguracja.jednostka == "dni":
        termin = data_zdarzenia + timedelta(days=konfiguracja.liczba)
        jednostka = "dni"
    elif konfiguracja.jednostka == "miesiace":
        miesiac = data_zdarzenia.year * 12 + data_zdarzenia.month - 1
        rok, miesiac = divmod(miesiac + konfiguracja.liczba, 12)
        miesiac += 1
        dzien = min(data_zdarzenia.day, monthrange(rok, miesiac)[1])
        termin = date(rok, miesiac, dzien)
        jednostka = "miesięcy"
    else:
        raise ValueError(f"Nieznana jednostka terminu {konfiguracja.jednostka!r}.")

    slad = [KrokObliczenia(
        konfiguracja.regula,
        f"Przesunięcie daty {data_zdarzenia} o {konfiguracja.liczba} {jednostka} daje {termin}.",
    )]
    przesuniecie = konfiguracja.przesuniecie_dnia_wolnego
    if przesuniecie is not None and _dzien_wolny(termin, dni_wolne):
        przed = termin
        while _dzien_wolny(termin, dni_wolne):
            termin += timedelta(days=1)
        slad.append(KrokObliczenia(
            przesuniecie,
            f"Przesunięto termin z dnia wolnego {przed} na dzień roboczy {termin}.",
        ))
    return WynikTerminu(termin, tuple(slad))


def polacz_nieobecnosci(
    okresy: Iterable[Okres],
    *,
    regula: Regula,
    dni_wolne: Set[date] = frozenset(),
) -> WynikPolaczeniaNieobecnosci:
    """Połącz okresy nakładające się, stykające lub rozdzielone dniami wolnymi.

    Soboty, niedziele i podane dni wolne mogą należeć do przerwy. Zwróć okresy
    w kolejności chronologicznej i opisz połączenia w śladzie.
    """
    uporzadkowane = sorted(okresy, key=lambda okres: (okres.od, okres.do))
    polaczone: list[Okres] = []
    slad: list[KrokObliczenia] = []

    for okres in uporzadkowane:
        if okres.od > okres.do:
            raise ValueError(f"Początek okresu {okres.od} przypada po jego końcu {okres.do}.")
        if not polaczone:
            polaczone.append(okres)
            continue

        poprzedni = polaczone[-1]
        przerwa = (okres.od - poprzedni.do).days
        if any(
            not _dzien_wolny(poprzedni.do + timedelta(days=dzien), dni_wolne)
            for dzien in range(1, przerwa)
        ):
            polaczone.append(okres)
            continue

        wspolny = Okres(poprzedni.od, max(poprzedni.do, okres.do))
        polaczone[-1] = wspolny
        slad.append(KrokObliczenia(
            regula,
            f"Połączono okres {poprzedni.od}–{poprzedni.do} z okresem {okres.od}–{okres.do} "
            f"w okres {wspolny.od}–{wspolny.do}.",
        ))

    if not slad:
        slad.append(KrokObliczenia(regula, f"Brak okresów do połączenia spośród {len(uporzadkowane)} podanych."))
    return WynikPolaczeniaNieobecnosci(tuple(polaczone), tuple(slad))


def _dzien_wolny(dzien: date, dni_wolne: Set[date]) -> bool:
    return dzien.weekday() >= 5 or dzien in dni_wolne
