"""Model kompetencji (Model_kompetencji.xlsx) odczytany z fragmentów korpusu MC.

Arkusz „Model kompetencji” ma instrukcję (A3–A6) i tabelę: Lp. | Kompetencja | Liczba
wskaźników. Każda kompetencja ma własny arkusz (nazwy arkuszy są skrócone do 31 znaków,
więc arkusz rozpoznajemy po tytule w A1). W arkuszu kompetencji wiersz 3 to nagłówki
poziomów, a od wiersza 4: A = wskaźnik behawioralny, B–F = opisy zachowań na 5 poziomach.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from kompas_core.zrodla import Fragment, Kategoria, SourceRef
from pydantic import BaseModel

from .korpus_mc import KorpusMC

DOC_ID = "model-kompetencji"
ARKUSZ_ZBIORCZY = "Model kompetencji"
POZIOMY = (1, 3, 5, 7, 9)
"""Wartości poziomów B–F (skala z metodyki #31 i #36)."""
KOLUMNY_POZIOMOW = "BCDEF"


class OpisPoziomu(BaseModel):
    poziom: int
    etykieta: str
    opis: str
    adnotacja: SourceRef


class Wskaznik(BaseModel):
    id: str
    nazwa: str
    poziomy: list[OpisPoziomu]
    adnotacja: SourceRef


class Kompetencja(BaseModel):
    id: str
    lp: int
    nazwa: str
    """Nazwa dosłownie jak w modelu (np. „ORGANIZACJA PRACY i ORIENTACJA NA OSIĄGANIE CELÓW”)."""
    wskazniki: list[Wskaznik]
    adnotacja: SourceRef


class Instrukcja(BaseModel):
    tekst: str
    adnotacja: SourceRef


class ModelKompetencji(BaseModel):
    podsumowanie: str
    instrukcja: list[Instrukcja]
    kompetencje: list[Kompetencja]

    def kompetencja(self, id_: str) -> Kompetencja | None:
        return next((k for k in self.kompetencje if k.id == id_), None)

    @property
    def liczba_wskaznikow(self) -> int:
        return sum(len(k.wskazniki) for k in self.kompetencje)


_KOMORKA = re.compile(r"^(.+)!([A-Z]+)(\d+)$")


def _czysty(tekst: str) -> str:
    return " ".join(tekst.split())


def slug(nazwa: str) -> str:
    """„ORGANIZACJA PRACY i ORIENTACJA…” → „organizacja-pracy-i-orientacja…”."""
    bez = unicodedata.normalize("NFKD", nazwa.lower().replace("ł", "l"))
    bez = "".join(z for z in bez if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9]+", "-", bez).strip("-")


def _adnotacja(f: Fragment) -> SourceRef:
    return SourceRef(
        doc_id=f.doc_id,
        doc_version=f.doc_version,
        lokalizator=f.lokalizator,
        cytat_doslowny=f.tekst.strip(),
        kategoria=Kategoria.OBJASNIENIE_MATERIALU,
    )


class BladModelu(ValueError):
    pass


def odczytaj(korpus: KorpusMC) -> ModelKompetencji:
    arkusze: dict[str, dict[tuple[str, int], Fragment]] = defaultdict(dict)
    for f in korpus.korpus.fragmenty:
        if f.doc_id != DOC_ID:
            continue
        m = _KOMORKA.match(f.lokalizator or "")
        if m:
            arkusze[m.group(1)][(m.group(2), int(m.group(3)))] = f

    zbiorczy = arkusze.pop(ARKUSZ_ZBIORCZY)
    po_tytule = {
        _czysty(kom[("A", 1)].tekst).upper(): kom for kom in arkusze.values() if ("A", 1) in kom
    }

    kompetencje: list[Kompetencja] = []
    wiersz = 9
    while ("B", wiersz) in zbiorczy:
        f_nazwa = zbiorczy[("B", wiersz)]
        nazwa = _czysty(f_nazwa.tekst)
        lp = int(zbiorczy[("A", wiersz)].tekst)
        deklarowana = int(zbiorczy[("C", wiersz)].tekst)
        kom = po_tytule.get(nazwa.upper())
        if kom is None:
            raise BladModelu(f"Brak arkusza kompetencji „{nazwa}”")
        etykiety = [_czysty(kom[(k, 3)].tekst) for k in KOLUMNY_POZIOMOW]
        wskazniki = []
        w = 4
        while ("A", w) in kom:
            fa = kom[("A", w)]
            wskazniki.append(
                Wskaznik(
                    id=f"{slug(nazwa)}.{len(wskazniki) + 1}",
                    nazwa=_czysty(fa.tekst),
                    poziomy=[
                        OpisPoziomu(
                            poziom=poz,
                            etykieta=etykieta,
                            opis=_czysty(kom[(kol, w)].tekst),
                            adnotacja=_adnotacja(kom[(kol, w)]),
                        )
                        for poz, kol, etykieta in zip(POZIOMY, KOLUMNY_POZIOMOW, etykiety, strict=True)
                    ],
                    adnotacja=_adnotacja(fa),
                )
            )
            w += 1
        if len(wskazniki) != deklarowana:
            raise BladModelu(
                f"„{nazwa}”: arkusz ma {len(wskazniki)} wskaźników, tabela zbiorcza {deklarowana}"
            )
        kompetencje.append(
            Kompetencja(
                id=slug(nazwa), lp=lp, nazwa=nazwa, wskazniki=wskazniki, adnotacja=_adnotacja(f_nazwa)
            )
        )
        wiersz += 1

    instrukcja = [
        Instrukcja(tekst=_czysty(zbiorczy[("A", r)].tekst), adnotacja=_adnotacja(zbiorczy[("A", r)]))
        for r in (4, 5, 6)
        if ("A", r) in zbiorczy
    ]
    return ModelKompetencji(
        podsumowanie=_czysty(zbiorczy[("A", 3)].tekst), instrukcja=instrukcja, kompetencje=kompetencje
    )
