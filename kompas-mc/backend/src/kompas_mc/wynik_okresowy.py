"""Konfiguracja i obliczenie wyniku oceny okresowej (krok 6)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from kompas_core.skala import (
    KonfiguracjaSkali,
    ProgPoziomu,
    RegulaWyniku,
    WarunekLiczbyOcen,
    WarunekSredniej,
)
from pydantic import BaseModel, Field

from .reguly import RegulaZAdnotacja


class ProgOkresowy(RegulaZAdnotacja):
    poziom: str
    minimum: Decimal
    maksimum: Decimal
    minimum_domkniete: bool = False


class KonfiguracjaWynikuOkresowego(BaseModel):
    wersja: str
    srednia: RegulaZAdnotacja
    progi: list[ProgOkresowy] = Field(min_length=1)
    ocena_czastkowa_negatywna: int
    granica_negatywna: Decimal
    negatywna_ocena_czastkowa: RegulaZAdnotacja
    niski_poziom: RegulaZAdnotacja
    pozytywna: RegulaZAdnotacja
    uzasadnienie: RegulaZAdnotacja
    czesc_iii: RegulaZAdnotacja

    @classmethod
    def z_pliku(cls, plik: Path) -> KonfiguracjaWynikuOkresowego:
        return cls.model_validate(yaml.safe_load(plik.read_text(encoding="utf-8")))

    def skala_core(self, punkty: list[int]) -> KonfiguracjaSkali:
        return KonfiguracjaSkali(
            dozwolone_oceny=tuple(punkty),
            regula_sredniej=self.srednia.do_core(),
            wynik_domyslny="pozytywna",
            regula_domyslna=self.pozytywna.do_core(),
            progi=tuple(
                ProgPoziomu(
                    p.poziom, p.do_core(), p.minimum, p.maksimum,
                    domkniety_od_dolu=p.minimum_domkniete,
                )
                for p in self.progi
            ),
            reguly_rozstrzygajace=(
                RegulaWyniku(
                    self.negatywna_ocena_czastkowa.do_core(),
                    (WarunekLiczbyOcen(self.ocena_czastkowa_negatywna, ">=", 1),),
                    "negatywna",
                ),
                RegulaWyniku(
                    self.niski_poziom.do_core(),
                    (WarunekSredniej("<=", self.granica_negatywna),),
                    "negatywna",
                ),
            ),
        )
