"""Wnioski rozwojowe (#36): propozycje obszarów i form rozwoju.

Czysta funkcja: dane oceny wskaźników → propozycje powiązane ze wskaźnikiem i przykładem.
Asystent nie pisze treści wniosków: pole na treść zostaje puste, wypełnia je przełożony.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field

Sciezka = Literal["pierwsza", "okresowa"]
TypPropozycji = Literal["OBSZAR_ROZWOJOWY", "MOCNA_STRONA"]
Poziom = Literal[1, 3, 5, 7, 9]


# --- konfiguracja -------------------------------------------------------------------


class Regula(BaseModel):
    id: str
    opis: str
    adnotacje: list[SourceRef]


class Forma(BaseModel):
    id: str
    nazwa: str
    dla: list[Literal["obszar", "mocna"]]
    kompetencje: list[str] | None = None
    adnotacje: list[SourceRef]


class KonfiguracjaRozwoju(BaseModel):
    wersja: str
    poziom_oczekiwan: int
    reguly: dict[str, Regula]
    formy: list[Forma]

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaRozwoju:
        d = yaml.safe_load(Path(plik).read_text(encoding="utf-8"))
        return cls(
            wersja=d["wersja"],
            poziom_oczekiwan=d["poziom_oczekiwan"],
            reguly={r["id"]: Regula.model_validate(r) for r in d["reguly"]},
            formy=[Forma.model_validate(f) for f in d["formy"]],
        )


# --- wejście i wyjście --------------------------------------------------------------


class OcenaWskaznika(BaseModel):
    """Ocena jednego wskaźnika z kroków 3–5 (#31). ``poziom=None`` = brak podstaw."""

    kompetencja: str
    wskaznik: str
    wskaznik_id: str | None = None
    poziom: Poziom | None
    przyklady: list[str] = Field(default_factory=list)


class DaneRozwoju(BaseModel):
    sciezka: Sciezka
    wynik_pozytywny: bool | None = None
    """Pierwsza ocena: wnioski tylko przy pozytywnej. None = wynik jeszcze nieznany."""
    wskazniki: list[OcenaWskaznika]


class PropozycjaFormy(BaseModel):
    id: str
    nazwa: str
    adnotacje: list[SourceRef]


class Propozycja(BaseModel):
    typ: TypPropozycji
    kompetencja: str
    wskaznik: str
    wskaznik_id: str | None
    poziom: int
    przyklady: list[str]
    formy: list[PropozycjaFormy]
    regula: str
    uwagi: list[str] = Field(default_factory=list)


class Pominiety(BaseModel):
    kompetencja: str
    wskaznik: str
    powod: str


class WynikRozwoju(BaseModel):
    wersja_metodyki: str
    dostepne: bool
    komunikat: str | None = None
    propozycje: list[Propozycja] = Field(default_factory=list)
    pominiete: list[Pominiety] = Field(default_factory=list)
    struktura_wnioskow: list[str]
    """Nagłówki podpowiadane przełożonemu (bez treści)."""
    tresc_wnioskow: None = None
    """Zawsze None: treść pisze przełożony."""
    reguly: list[Regula]
    status: Literal["PROPOZYCJA — wymaga decyzji przełożonego"] = (
        "PROPOZYCJA — wymaga decyzji przełożonego"
    )


STRUKTURA = [
    "Obszary wiedzy do poszerzenia",
    "Umiejętności wymagające doskonalenia",
    "Proponowane formy i metody rozwoju",
]


def zaproponuj(dane: DaneRozwoju, konf: KonfiguracjaRozwoju) -> WynikRozwoju:
    reguly_bazowe = [konf.reguly["rozwoj.zakres-wnioskow"], konf.reguly["rozwoj.tresc-pisze-przelozony"]]

    if dane.sciezka == "pierwsza" and dane.wynik_pozytywny is False:
        warunek = konf.reguly["rozwoj.pierwsza-tylko-pozytywna"]
        return WynikRozwoju(
            wersja_metodyki=konf.wersja,
            dostepne=False,
            komunikat="Wnioski rozwojowe w pierwszej ocenie sporządza się tylko przy ocenie pozytywnej.",
            struktura_wnioskow=STRUKTURA,
            reguly=[warunek],
        )

    propozycje: list[Propozycja] = []
    pominiete: list[Pominiety] = []
    for w in dane.wskazniki:
        if w.poziom is None:
            pominiete.append(
                Pominiety(kompetencja=w.kompetencja, wskaznik=w.wskaznik, powod="brak podstaw do oceny")
            )
            continue
        if w.poziom < konf.poziom_oczekiwan:
            typ, dla, regula = "OBSZAR_ROZWOJOWY", "obszar", "rozwoj.obszar-ponizej-oczekiwan"
        elif w.poziom > konf.poziom_oczekiwan:
            typ, dla, regula = "MOCNA_STRONA", "mocna", "rozwoj.mocna-strona"
        else:
            pominiete.append(
                Pominiety(kompetencja=w.kompetencja, wskaznik=w.wskaznik, powod="na poziomie oczekiwań")
            )
            continue
        formy = [
            PropozycjaFormy(id=f.id, nazwa=f.nazwa, adnotacje=f.adnotacje)
            for f in konf.formy
            if dla in f.dla and (f.kompetencje is None or w.kompetencja in f.kompetencje)
        ]
        uwagi = []
        if not w.przyklady:
            uwagi.append("Brak przykładu: dopisz sytuację, działanie i rezultat, zanim użyjesz propozycji.")
        propozycje.append(
            Propozycja(
                typ=typ,
                kompetencja=w.kompetencja,
                wskaznik=w.wskaznik,
                wskaznik_id=w.wskaznik_id,
                poziom=w.poziom,
                przyklady=w.przyklady,
                formy=formy,
                regula=regula,
                uwagi=uwagi,
            )
        )

    # Najpierw obszary rozwojowe od najniższego poziomu, potem mocne strony.
    propozycje.sort(key=lambda p: (p.typ != "OBSZAR_ROZWOJOWY", p.poziom if p.typ == "OBSZAR_ROZWOJOWY" else -p.poziom))
    uzyte = {p.regula for p in propozycje}
    komunikat = None
    if dane.sciezka == "pierwsza" and dane.wynik_pozytywny is None:
        komunikat = "Wnioski w pierwszej ocenie będą dostępne tylko przy ocenie pozytywnej."
        uzyte.add("rozwoj.pierwsza-tylko-pozytywna")
    return WynikRozwoju(
        wersja_metodyki=konf.wersja,
        dostepne=True,
        komunikat=komunikat,
        propozycje=propozycje,
        pominiete=pominiete,
        struktura_wnioskow=STRUKTURA,
        reguly=reguly_bazowe + [konf.reguly[r] for r in sorted(uzyte)],
    )
