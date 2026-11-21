"""Wynik pierwszej oceny według § 7, § 9 i § 10 rozporządzenia z 2015 r."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.skala import (
    KonfiguracjaSkali,
    RegulaWyniku,
    WarunekFaktu,
    WarunekLiczbyOcen,
    WarunekSredniej,
    WynikSkali,
    oblicz_wynik,
)
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, ConfigDict, model_validator

from .qnt import Pracownik
from .reguly import RegulaZAdnotacja

PrzeslankaEgzaminu = Literal["ksap_bez_wniosku", "zastepstwo", "wyzsze_stanowisko"]


class EgzaminPierwszej(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wynik: Literal["tak", "nie", "nie_dotyczy"]
    przeslanka: PrzeslankaEgzaminu | None = None

    @model_validator(mode="after")
    def _przeslanka(self) -> EgzaminPierwszej:
        if self.wynik == "nie_dotyczy" and self.przeslanka is None:
            raise ValueError("Wskaż przesłankę z § 10 ust. 3 dla „nie dotyczy”.")
        if self.wynik != "nie_dotyczy" and self.przeslanka is not None:
            raise ValueError("Przesłanka z § 10 ust. 3 dotyczy wyłącznie odpowiedzi „nie dotyczy”.")
        return self


def egzamin_z_qnt(p: Pracownik) -> EgzaminPierwszej | None:
    if not p.pierwsza_ocena:
        return None
    zapis = p.pierwsza_ocena.egzamin_sluzba_przygotowawcza
    if zapis == "zaliczony":
        return EgzaminPierwszej(wynik="tak")
    if zapis == "nie_dotyczy":
        if p.absolwent_ksap and p.wniosek_o_mianowanie is False:
            return EgzaminPierwszej(wynik="nie_dotyczy", przeslanka="ksap_bez_wniosku")
        if p.zastepstwo:
            return EgzaminPierwszej(wynik="nie_dotyczy", przeslanka="zastepstwo")
    return None


def sprawdz_podstawe_egzaminu(egzamin: EgzaminPierwszej, p: Pracownik) -> None:
    if egzamin.przeslanka == "ksap_bez_wniosku" and not (
        p.absolwent_ksap and p.wniosek_o_mianowanie is False
    ):
        raise ValueError("Dane kadrowe nie potwierdzają statusu absolwenta KSAP bez wniosku o mianowanie.")
    if egzamin.przeslanka == "zastepstwo" and not p.zastepstwo:
        raise ValueError("Dane kadrowe nie potwierdzają zatrudnienia na zastępstwo.")


class KonfiguracjaWynikuPierwszej(BaseModel):
    wersja: str
    minimum_sredniej: Decimal
    najmniejsza_ocena: int
    maksimum_najnizszych: int
    srednia: RegulaZAdnotacja
    pozytywna: RegulaZAdnotacja
    negatywna: RegulaZAdnotacja
    warunek_egzaminu: RegulaZAdnotacja
    warunek_sprawozdania: RegulaZAdnotacja
    warunek_najnizszych: RegulaZAdnotacja
    warunek_sredniej: RegulaZAdnotacja
    przeslanki: dict[PrzeslankaEgzaminu, RegulaZAdnotacja]
    uzasadnienie: RegulaZAdnotacja
    wnioski: RegulaZAdnotacja

    @classmethod
    def z_pliku(cls, plik: Path) -> KonfiguracjaWynikuPierwszej:
        return cls.model_validate(yaml.safe_load(plik.read_text(encoding="utf-8")))

    def skala_core(self, punkty: Sequence[int]) -> KonfiguracjaSkali:
        return KonfiguracjaSkali(
            tuple(punkty), self.srednia.do_core(), "negatywna", self.negatywna.do_core(),
            reguly_rozstrzygajace=(RegulaWyniku(
                self.pozytywna.do_core(),
                (
                    WarunekFaktu("egzamin", True),
                    WarunekFaktu("sprawozdanie", True),
                    WarunekLiczbyOcen(self.najmniejsza_ocena, "<=", self.maksimum_najnizszych),
                    WarunekSredniej(">=", self.minimum_sredniej),
                ),
                "pozytywna",
            ),),
        )


class WarunekPierwszej(BaseModel):
    id: str
    opis: str
    spelniony: bool
    zrodlo: SourceRef


def wynik_pierwszej(
    oceny: Sequence[int],
    skala: KonfiguracjaSkali,
    konf: KonfiguracjaWynikuPierwszej,
    egzamin: EgzaminPierwszej,
    sprawozdanie_w_terminie: bool,
) -> tuple[WynikSkali, list[WarunekPierwszej]]:
    egzamin_spelniony = egzamin.wynik != "nie"
    wynik = oblicz_wynik(oceny, skala, fakty={
        "egzamin": egzamin_spelniony, "sprawozdanie": sprawozdanie_w_terminie,
    })
    regula_egzaminu = konf.przeslanki[egzamin.przeslanka] if egzamin.przeslanka else konf.warunek_egzaminu
    liczba_niskich = oceny.count(konf.najmniejsza_ocena)
    warunki = [
        (regula_egzaminu, "Zaliczony egzamin lub zastosowanie przesłanki zwolnienia.", egzamin_spelniony),
        (konf.warunek_sprawozdania, "Sprawozdanie złożone w wyznaczonym terminie.", sprawozdanie_w_terminie),
        (
            konf.warunek_najnizszych, f"Liczba ocen cząstkowych po {konf.najmniejsza_ocena} pkt wynosi {liczba_niskich}.",
            liczba_niskich <= konf.maksimum_najnizszych,
        ),
        (
            konf.warunek_sredniej, f"Ocena łączna {wynik.srednia:g}. Próg {konf.minimum_sredniej:g} pkt.",
            wynik.srednia >= konf.minimum_sredniej,
        ),
    ]
    return wynik, [
        WarunekPierwszej(id=r.id, opis=opis, spelniony=spelniony, zrodlo=r.adnotacje[0])
        for r, opis, spelniony in warunki
    ]
