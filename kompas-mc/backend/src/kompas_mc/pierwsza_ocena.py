"""Dane sprawozdania i arkusza pierwszej oceny."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated

from kompas_core.skala import WynikSkali
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .arkusze import BrakArkusza, DANE_OSOBY, SekcjaArkusza, WzorArkusza, pola_arkusza
from .qnt import Pracownik
from .terminy_pierwszej import DaneTerminowPierwszej, TerminyPierwszej
from .wynik_pierwszej import EgzaminPierwszej

Tresc = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class SprawozdaniePierwszej(BaseModel):
    """Cztery elementy sprawozdania zgodnie z § 6 ust. 2."""

    model_config = ConfigDict(extra="forbid")
    zadania: Tresc
    problemy_i_rozwiazania: Tresc
    nowe_umiejetnosci_i_wiedza: Tresc
    propozycje_usprawnien: Tresc


class DanePierwszejOceny(DaneTerminowPierwszej):
    model_config = ConfigDict(extra="forbid")
    sprawozdanie: SprawozdaniePierwszej | None = None
    egzamin: EgzaminPierwszej | None = None
    uzasadnienie: str | None = Field(default=None, max_length=4000)
    wnioski_rozwojowe: str | None = Field(default=None, max_length=4000)
    pola: dict[str, str | None] = Field(
        default_factory=dict, description="Uzupełnienia edytowalnych pól arkusza. Daty w RRRR-MM-DD.",
    )

    @field_validator("uzasadnienie", "wnioski_rozwojowe")
    @classmethod
    def _pomin_puste(cls, wartosc: str | None) -> str | None:
        return (wartosc or "").strip() or None


class ZapisDanychPierwszej(BaseModel):
    dane: DanePierwszejOceny = Field(default_factory=DanePierwszejOceny)
    zatwierdzony_odcisk: str | None = None
    podstawa_decyzji: str | None = None

    @classmethod
    def wczytaj(cls, zapis: str | None) -> ZapisDanychPierwszej:
        return cls.model_validate_json(zapis) if zapis else cls()


def uzupelnij_z_kadr(dane: DanePierwszejOceny, pracownik: Pracownik) -> DanePierwszejOceny:
    pierwsza = pracownik.pierwsza_ocena
    data_uzgodnienia = pierwsza.uzgodnienie_zastepstwa if pierwsza else None
    return dane.model_copy(update={
        "data_konca_zatrudnienia": dane.data_konca_zatrudnienia or pracownik.data_konca_zatrudnienia,
        "data_ustalenia_oceny_zastepstwa": dane.data_ustalenia_oceny_zastepstwa or data_uzgodnienia,
    })


_UZUPELNIENIA_ARKUSZA = {
    "nazwa_urzedu",
    "potwierdzenie_rozmowy_wstepnej.przelozony.miejscowosc",
    "potwierdzenie_rozmowy_wstepnej.oceniany.miejscowosc",
    "potwierdzenie_rozmowy_oceniajacej.przelozony.miejscowosc",
    "potwierdzenie_rozmowy_oceniajacej.oceniany.miejscowosc",
    "dokonanie_oceny.przelozony.miejscowosc",
    "dokonanie_oceny.kierujacy.miejscowosc",
    "dokonanie_oceny.kierujacy.data",
    "zapoznanie.oceniany.miejscowosc",
}


def wypelnij_pierwsza(
    wzor: WzorArkusza,
    dane: DanePierwszejOceny,
    terminy: TerminyPierwszej,
    *,
    nazwa_urzedu: str,
    pracownik: Pracownik,
    przelozony: Pracownik | None,
    kierujacy: Pracownik | None,
    punkty: Mapping[str, int],
    kolejnosc_kryteriow: list[str],
    egzamin: EgzaminPierwszej | None,
    obliczenie: WynikSkali | None,
) -> tuple[list[SekcjaArkusza], list[BrakArkusza]]:
    rozmowa_wstepna = _data(terminy.data_rozmowy_wstepnej)
    rozmowa_oceniajaca = _data(dane.data_rozmowy_oceniajacej)
    data_sporzadzenia = _data(dane.data_sporzadzenia_oceny)
    wartosci = {
        "nazwa_urzedu": nazwa_urzedu,
        "oceniany.data_nawiazania_stosunku_pracy": _data(
            dane.data_ustalenia_oceny_zastepstwa if pracownik.zastepstwo else pracownik.data_zatrudnienia
        ),
        "rozmowa_wstepna.data": rozmowa_wstepna,
        "termin_sprawozdania.od": _data(terminy.termin_sprawozdania_od.data) if terminy.termin_sprawozdania_od else None,
        "termin_sprawozdania.do": _data(terminy.termin_sprawozdania_do.data) if terminy.termin_sprawozdania_do else None,
        "okres_pierwszej_oceny.od": _data(terminy.pierwsza_ocena_od.data) if terminy.pierwsza_ocena_od else None,
        "okres_pierwszej_oceny.do": _data(terminy.pierwsza_ocena_do.data) if terminy.pierwsza_ocena_do else None,
        "potwierdzenie_rozmowy_wstepnej.przelozony.data": rozmowa_wstepna,
        "potwierdzenie_rozmowy_wstepnej.oceniany.data": rozmowa_wstepna,
        "rozmowa_oceniajaca.data": rozmowa_oceniajaca,
        "potwierdzenie_rozmowy_oceniajacej.przelozony.data": rozmowa_oceniajaca,
        "potwierdzenie_rozmowy_oceniajacej.oceniany.data": rozmowa_oceniajaca,
        "ocena_laczna": f"{obliczenie.srednia:.2f}".replace(".", ",") if obliczenie else None,
        "egzamin": egzamin.wynik.replace("_", " ").upper() if egzamin else None,
        "sprawozdanie_w_terminie": _tak_nie(terminy.sprawozdanie_w_terminie),
        "wynik": obliczenie.wynik.upper() if obliczenie else None,
        "uzasadnienie": dane.uzasadnienie,
        "wnioski_rozwojowe": dane.wnioski_rozwojowe,
        "dokonanie_oceny.przelozony.data": data_sporzadzenia,
        "dokonanie_oceny.kierujacy.data": data_sporzadzenia,
        "zapoznanie.oceniany.data": _data(dane.data_zapoznania_z_ocena),
    }
    edytowalne = set(_UZUPELNIENIA_ARKUSZA)
    for prefiks, osoba in {
        "oceniany": pracownik, "bezposredni_przelozony": przelozony, "kierujacy_komorka": kierujacy,
    }.items():
        for pole, atrybut in DANE_OSOBY.items():
            klucz = f"{prefiks}.{pole}"
            wartosc = getattr(osoba, atrybut, None)
            wartosci[klucz] = wartosc
            if not wartosc:
                edytowalne.add(klucz)
    wartosci.update({klucz: wartosc for klucz, wartosc in dane.pola.items() if klucz in edytowalne})

    powtorzone_dane = {
        "potwierdzenie_rozmowy_oceniajacej.przelozony": "bezposredni_przelozony",
        "potwierdzenie_rozmowy_oceniajacej.oceniany": "oceniany",
        "dokonanie_oceny.przelozony": "bezposredni_przelozony",
        "dokonanie_oceny.kierujacy": "kierujacy_komorka",
        "zapoznanie.oceniany": "oceniany",
    }
    for prefiks, dane_osoby in powtorzone_dane.items():
        imie = wartosci[f"{dane_osoby}.imie"]
        nazwisko = wartosci[f"{dane_osoby}.nazwisko"]
        wartosci[f"{prefiks}.imie_nazwisko_lub_pieczatka"] = f"{imie} {nazwisko}" if imie and nazwisko else None
    for numer, kryterium in enumerate(kolejnosc_kryteriow, 1):
        wartosci[f"ocena_czastkowa.{numer}"] = str(punkty[kryterium]) if kryterium in punkty else None

    warunki = {
        "ocena_pozytywna": bool(obliczenie and obliczenie.wynik == "pozytywna"),
        "ocena_negatywna": bool(obliczenie and obliczenie.wynik == "negatywna"),
    }
    return pola_arkusza(
        wzor, wartosci, warunki, edytowalne=edytowalne,
        opcjonalne={"zapoznanie.oceniany.data", "zapoznanie.oceniany.miejscowosc", "wnioski_rozwojowe"},
    )


def _data(dzien: date | None) -> str | None:
    return dzien.isoformat() if dzien else None


def _tak_nie(wartosc: bool | None) -> str | None:
    if wartosc is None:
        return None
    return "TAK" if wartosc else "NIE"
