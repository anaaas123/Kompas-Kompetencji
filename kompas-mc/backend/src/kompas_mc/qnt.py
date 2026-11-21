"""Mock systemu kadrowego QNT: fikcyjni pracownicy z ``konfiguracja/qnt.yaml``.

Zakres danych osobowych jest minimalny: imię, nazwisko, stanowisko, komórka, przełożony
oraz fakty kadrowe potrzebne do wyboru ścieżki oceny i terminów. Bez PESEL, adresów
i danych wrażliwych.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OstatniaOcenaOkresowa(_Model):
    data: date
    wynik: Literal["pozytywna", "negatywna"]


class ZmianaOceniajacego(_Model):
    data: date
    poprzedni_przelozony: str


class PierwszaOcena(_Model):
    egzamin_sluzba_przygotowawcza: Literal["zaliczony", "nie_dotyczy", "brak"]
    rozmowa_wstepna: date | None = None
    uzgodnienie_zastepstwa: date | None = None


class Nieobecnosc(_Model):
    od: date
    do: date
    rodzaj: str


class Pracownik(_Model):
    osoba_id: str
    imie: str
    nazwisko: str
    stanowisko: str
    symbol_osp: str | None = None
    komorka: str
    przelozony_id: str
    kieruje_pracownikami: bool
    korpus: Literal["urzednik_sc", "pracownik_sc"]
    data_zatrudnienia: date
    data_konca_zatrudnienia: date | None = None
    rodzaj_umowy: Literal["nieokreslony", "okreslony"]
    ostatnia_ocena_okresowa: OstatniaOcenaOkresowa | None = None
    zmiana_oceniajacego: ZmianaOceniajacego | None = None
    pierwsza_ocena: PierwszaOcena | None = None
    absolwent_ksap: bool = False
    wniosek_o_mianowanie: bool | None = None
    zastepstwo: bool = False
    nieobecnosci: list[Nieobecnosc] = []
    oczekiwany_arkusz: Literal["A", "B", "C"] | None = Field(default=None, exclude=True)
    """Tylko do testów; arkusz wylicza reguła § 3 rozp. 2016."""
    scenariusz: str | None = Field(default=None, exclude=True)
    """Opis, co rekord pokazuje na demo; nie jest daną kadrową."""


class MockQnt:
    def __init__(self, pracownicy: list[Pracownik], dzis_demo: date) -> None:
        self.pracownicy = pracownicy
        self.dzis_demo = dzis_demo
        self._po_id = {p.osoba_id: p for p in pracownicy}

    @classmethod
    def z_pliku(cls, plik: str | Path) -> MockQnt:
        dane = yaml.safe_load(Path(plik).read_text(encoding="utf-8"))
        return cls([Pracownik.model_validate(p) for p in dane["pracownicy"]], dane["dzis_demo"])

    def pracownik(self, osoba_id: str) -> Pracownik | None:
        return self._po_id.get(osoba_id)
