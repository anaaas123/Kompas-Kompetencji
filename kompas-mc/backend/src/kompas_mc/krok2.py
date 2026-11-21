"""Krok 2 (#30): kryteria obowiązkowe i dodatkowe, dobór wskaźników do zadań z OSP.

Czyste funkcje na modelu kompetencji, OSP i konfiguracji ``konfiguracja/krok2.yaml``.
System proponuje wskaźniki i kryteria dodatkowe; wybór zatwierdza przełożony.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import Fragment, Kategoria, SourceRef, cytat_w_tekscie
from pydantic import BaseModel, Field

from .kompetencje import Instrukcja, ModelKompetencji, Wskaznik
from .osp import OpisStanowiska

Sciezka = Literal["pierwsza", "okresowa"]
ArkuszProcesu = Literal["B", "C", "PIERWSZA"]
RodzajKryterium = Literal["OBOWIAZKOWE", "DODATKOWE_PROPONOWANE", "DODATKOWE_DOSTEPNE", "NIEDOSTEPNE"]

PUNKTY_MIEKKIE = 3
PUNKTY_DOMINUJACE = 2
PUNKTY_POZOSTALE = 1


# ---------------------------------------------------------------- konfiguracja


class _Lista(BaseModel):
    kompetencje: list[str]
    adnotacje: list[SourceRef]


class _Dodatkowe(BaseModel):
    limit: int
    adnotacje: list[SourceRef]


class Metodyka(BaseModel):
    id: str
    status: str
    opis: str
    adnotacje: list[SourceRef]


class KonfiguracjaKroku2(BaseModel):
    wersja: str
    obowiazkowe: dict[ArkuszProcesu, _Lista]
    dodatkowe: dict[Sciezka, _Dodatkowe]
    podstawa_wskaznikow: dict[Sciezka, str]
    metodyka: Metodyka
    slowa_kluczowe: dict[str, list[str]]

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaKroku2:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))

    def sprawdz(self, model: ModelKompetencji) -> None:
        """Każde id z konfiguracji istnieje w modelu, a każdy wskaźnik ma słowa kluczowe."""
        kompetencje = {k.id for k in model.kompetencje}
        wskazniki = {w.id for k in model.kompetencje for w in k.wskazniki}
        for arkusz, lista in self.obowiazkowe.items():
            if nieznane := set(lista.kompetencje) - kompetencje:
                raise ValueError(f"krok2.yaml, obowiązkowe {arkusz}: nieznane kompetencje {nieznane}")
        if nieznane := set(self.slowa_kluczowe) - wskazniki:
            raise ValueError(f"krok2.yaml: słowa kluczowe nieznanych wskaźników {nieznane}")
        if brak := wskazniki - set(self.slowa_kluczowe):
            raise ValueError(f"krok2.yaml: wskaźniki bez słów kluczowych {sorted(brak)}")


# ---------------------------------------------------------------- odpowiedź


class ZadanieWskaznika(BaseModel):
    nr: int
    rodzaj: Literal["DOMINUJACE", "POZOSTALE"]
    tekst: str
    slowa: list[str]
    adnotacja: SourceRef


class WskaznikKroku2(BaseModel):
    wskaznik_id: str
    nazwa: str
    proponowany: bool
    podstawa: SourceRef | None
    """Nazwa wskaźnika w zał. 1 rozporządzenia właściwego dla ścieżki."""
    zadania: list[ZadanieWskaznika]


class PropozycjaDodatkowego(BaseModel):
    punkty: int
    powody: list[str]
    adnotacje: list[SourceRef]


class KryteriumKroku2(BaseModel):
    kompetencja_id: str
    nazwa: str
    rodzaj: RodzajKryterium
    propozycja: PropozycjaDodatkowego | None = None
    wskazniki: list[WskaznikKroku2]


class WybranyWskaznik(BaseModel):
    id: str
    nazwa: str


class WybraneKryterium(BaseModel):
    kompetencja_id: str
    nazwa: str
    rodzaj: Literal["OBOWIAZKOWE", "DODATKOWE"]
    wskazniki: list[WybranyWskaznik]


class WyborKroku2(BaseModel):
    kryteria: list[WybraneKryterium]
    zapisal: str
    zapisano: datetime
    zapoznanie: date | None = None
    """Data rozmowy z § 5 ust. 1 i zapoznania ocenianego z kryteriami (§ 6 ust. 2): zakończenie części I.
    Nowy zapis kryteriów ją kasuje, bo część I trzeba wtedy podpisać od nowa."""


class ZapisZapoznania(BaseModel):
    data: date


class PropozycjaKroku2(BaseModel):
    proces_id: int
    sciezka: Sciezka
    arkusz: ArkuszProcesu
    limit_dodatkowych: int
    podstawa_obowiazkowych: list[SourceRef]
    podstawa_dodatkowych: list[SourceRef]
    metodyka: Metodyka
    instrukcja: list[Instrukcja]
    kryteria: list[KryteriumKroku2]
    wybor: WyborKroku2 | None = None


class ZapisKroku2(BaseModel):
    dodatkowe: list[str] = Field(default_factory=list)
    wskazniki: dict[str, list[str]]


# ---------------------------------------------------------------- logika


def _bez_ogonkow(tekst: str) -> str:
    return unicodedata.normalize("NFC", " ".join(tekst.lower().split()))


def _zadania_wskaznika(
    w: Wskaznik, osp: OpisStanowiska | None, konf: KonfiguracjaKroku2
) -> list[ZadanieWskaznika]:
    if osp is None:
        return []
    slowa = [_bez_ogonkow(s) for s in konf.slowa_kluczowe.get(w.id, [])]
    wynik = []
    for rodzaj, zadania in (("DOMINUJACE", osp.zadania_dominujace), ("POZOSTALE", osp.zadania_pozostale)):
        for z in zadania:
            tekst = _bez_ogonkow(z.tekst)
            trafione = [s for s in slowa if s in tekst]
            if trafione:
                wynik.append(
                    ZadanieWskaznika(
                        nr=z.nr, rodzaj=rodzaj, tekst=z.tekst, slowa=trafione, adnotacja=z.adnotacja
                    )
                )
    return wynik


def _podstawa(nazwa: str, fragmenty: list[Fragment]) -> SourceRef | None:
    f = next((f for f in fragmenty if cytat_w_tekscie(nazwa, f.tekst)), None)
    if f is None:
        return None
    return SourceRef(
        doc_id=f.doc_id,
        doc_version=f.doc_version,
        lokalizator=f.lokalizator,
        strona=f.strona,
        cytat_doslowny=nazwa,
        kategoria=Kategoria.PRZEPIS,
    )


def _miekkie(osp: OpisStanowiska | None) -> set[str]:
    if osp is None or osp.kompetencje_miekkie is None:
        return set()
    return {_bez_ogonkow(k) for k in osp.kompetencje_miekkie.lista}


def zaproponuj(
    proces_id: int,
    sciezka: Sciezka,
    arkusz: ArkuszProcesu,
    osp: OpisStanowiska | None,
    model: ModelKompetencji,
    fragmenty_zal1: list[Fragment],
    konf: KonfiguracjaKroku2,
    wybor: WyborKroku2 | None = None,
) -> PropozycjaKroku2:
    """Kryteria i wskaźniki dla procesu: obowiązkowe według arkusza, propozycje dodatkowych."""
    obow = konf.obowiazkowe[arkusz]
    dod = konf.dodatkowe[sciezka]
    miekkie = _miekkie(osp)

    kryteria: list[KryteriumKroku2] = []
    kandydaci: list[tuple[int, int, KryteriumKroku2]] = []
    for k in model.kompetencje:
        wskazniki = []
        for w in k.wskazniki:
            zadania = _zadania_wskaznika(w, osp, konf)
            wskazniki.append(
                WskaznikKroku2(
                    wskaznik_id=w.id,
                    nazwa=w.nazwa,
                    proponowany=bool(zadania),
                    podstawa=_podstawa(w.nazwa, fragmenty_zal1),
                    zadania=zadania,
                )
            )
        if k.id in obow.kompetencje:
            rodzaj: RodzajKryterium = "OBOWIAZKOWE"
        elif dod.limit == 0:
            rodzaj = "NIEDOSTEPNE"
        else:
            rodzaj = "DODATKOWE_DOSTEPNE"
        kryterium = KryteriumKroku2(kompetencja_id=k.id, nazwa=k.nazwa, rodzaj=rodzaj, wskazniki=wskazniki)
        kryteria.append(kryterium)

        if rodzaj == "DODATKOWE_DOSTEPNE":
            punkty, powody, adnotacje = 0, [], []
            if _bez_ogonkow(k.nazwa) in miekkie and osp and osp.kompetencje_miekkie:
                punkty += PUNKTY_MIEKKIE
                powody.append("kompetencja miękka wymagana w OSP")
                adnotacje.append(osp.kompetencje_miekkie.adnotacja)
            zadania: dict[int, ZadanieWskaznika] = {
                z.nr: z for w in wskazniki for z in w.zadania
            }
            for z in zadania.values():
                punkty += PUNKTY_DOMINUJACE if z.rodzaj == "DOMINUJACE" else PUNKTY_POZOSTALE
            if zadania:
                powody.append("zadania z OSP: " + ", ".join(str(n) for n in sorted(zadania)))
                adnotacje += [zadania[n].adnotacja for n in sorted(zadania)]
            if punkty > 0:
                kryterium.propozycja = PropozycjaDodatkowego(
                    punkty=punkty, powody=powody, adnotacje=[*adnotacje, *konf.metodyka.adnotacje]
                )
                kandydaci.append((punkty, -k.lp, kryterium))

    for _, _, kryterium in sorted(kandydaci, key=lambda x: (x[0], x[1]), reverse=True)[: dod.limit]:
        kryterium.rodzaj = "DODATKOWE_PROPONOWANE"
    for kryterium in kryteria:
        if kryterium.rodzaj != "DODATKOWE_PROPONOWANE":
            kryterium.propozycja = None

    kolejnosc = {"OBOWIAZKOWE": 0, "DODATKOWE_PROPONOWANE": 1, "DODATKOWE_DOSTEPNE": 2, "NIEDOSTEPNE": 3}
    lp = {k.id: k.lp for k in model.kompetencje}

    def klucz(k: KryteriumKroku2) -> tuple[int, int, int]:
        poz = obow.kompetencje.index(k.kompetencja_id) if k.rodzaj == "OBOWIAZKOWE" else 0
        pkt = -(k.propozycja.punkty if k.propozycja else 0)
        return (kolejnosc[k.rodzaj], poz or pkt, lp[k.kompetencja_id])

    kryteria.sort(key=klucz)
    return PropozycjaKroku2(
        proces_id=proces_id,
        sciezka=sciezka,
        arkusz=arkusz,
        limit_dodatkowych=dod.limit,
        podstawa_obowiazkowych=obow.adnotacje,
        podstawa_dodatkowych=dod.adnotacje,
        metodyka=konf.metodyka,
        instrukcja=model.instrukcja,
        kryteria=kryteria,
        wybor=wybor,
    )


class BladWyboru(ValueError):
    pass


def zatwierdz(
    zapis: ZapisKroku2,
    sciezka: Sciezka,
    arkusz: ArkuszProcesu,
    model: ModelKompetencji,
    konf: KonfiguracjaKroku2,
    zapisal: str,
    zapisano: datetime,
) -> WyborKroku2:
    """Sprawdza wybór przełożonego. ``BladWyboru`` z listą problemów przy błędach."""
    obow = konf.obowiazkowe[arkusz].kompetencje
    limit = konf.dodatkowe[sciezka].limit
    bledy: list[str] = []

    dodatkowe = list(dict.fromkeys(zapis.dodatkowe))
    if limit == 0 and dodatkowe:
        bledy.append("Pierwsza ocena nie przewiduje kryteriów dodatkowych (§ 2 rozp. 2015).")
    elif len(dodatkowe) > limit:
        bledy.append(f"Najwyżej {limit} kryteria dodatkowe (§ 5 ust. 2 rozp. 2016); podano {len(dodatkowe)}.")
    for d in dodatkowe:
        if model.kompetencja(d) is None:
            bledy.append(f"Nieznane kryterium „{d}”.")
        elif d in obow:
            bledy.append(f"„{d}” jest kryterium obowiązkowym, nie dodatkowym.")

    wybrane = list(obow) + [d for d in dodatkowe if d not in obow]
    for k_id in zapis.wskazniki:
        if k_id not in wybrane:
            bledy.append(f"Wskaźniki podane dla kryterium „{k_id}”, które nie jest wybrane.")

    kryteria: list[WybraneKryterium] = []
    for k_id in wybrane:
        k = model.kompetencja(k_id)
        if k is None:
            continue
        po_id = {w.id: w for w in k.wskazniki}
        ids = list(dict.fromkeys(zapis.wskazniki.get(k_id, [])))
        if not ids:
            bledy.append(f"Kryterium „{k.nazwa}” nie ma żadnego wskaźnika.")
        obce = [i for i in ids if i not in po_id]
        if obce:
            bledy.append(f"Wskaźniki {obce} nie należą do kryterium „{k.nazwa}”.")
        kryteria.append(
            WybraneKryterium(
                kompetencja_id=k.id,
                nazwa=k.nazwa,
                rodzaj="OBOWIAZKOWE" if k_id in obow else "DODATKOWE",
                wskazniki=[WybranyWskaznik(id=i, nazwa=po_id[i].nazwa) for i in ids if i in po_id],
            )
        )
    if bledy:
        raise BladWyboru(bledy)
    return WyborKroku2(kryteria=kryteria, zapisal=zapisal, zapisano=zapisano)


__all__ = [
    "BladWyboru",
    "KonfiguracjaKroku2",
    "PropozycjaKroku2",
    "WyborKroku2",
    "ZapisKroku2",
    "zaproponuj",
    "zatwierdz",
]
