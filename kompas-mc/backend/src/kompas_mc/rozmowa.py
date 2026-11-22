"""Asystent rozmowy (#35, krok 6): plan rozmowy oceniającej jako SUGESTIA do edycji.

Czysta funkcja ``przygotuj(stan, osp, kontekst, konf)``: stan kroków 3–5 (#31) i opis
stanowiska z kroku 1 (#29) → zakres rozmowy z przepisu, pytania z powiązaniem
i uzasadnieniem, argumenty (zachowanie z modelu – przykład – rezultat), szkic informacji
zwrotnej i kwestie do omówienia. Szablony są deterministyczne (konfiguracja/rozmowa.yaml),
bez modelu językowego, więc dane osobowe nigdzie nie wychodzą. Wynik niczego nie zapisuje
i nie zmienia ocen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field

from .kompetencje import ModelKompetencji
from .ocena import KryteriumOceny, Przyklad, StanOceny, WskaznikOceny
from .osp import OpisStanowiska

Sciezka = Literal["pierwsza", "okresowa"]
TypPowiazania = Literal["wskaznik", "przyklad", "zadanie_osp", "przepis"]

# --- konfiguracja -------------------------------------------------------------------


class PunktZakresu(BaseModel):
    id: str
    punkt: str
    warunek: str | None = None
    adnotacje: list[SourceRef]


class SzablonPytania(BaseModel):
    id: str
    powiazanie: TypPowiazania
    tresc: str
    uzasadnienie: str
    sciezka: Sciezka | None = None
    warunek: str | None = None
    adnotacje: list[SourceRef]


class SzablonKwestii(BaseModel):
    id: str
    warunek: str
    tresc: str
    sciezka: Sciezka | None = None
    prog_poziomow: int | None = None
    adnotacje: list[SourceRef]


class KonfiguracjaRozmowy(BaseModel):
    wersja: str
    oznaczenie_sugestii: str
    zakres_rozmowy: dict[Sciezka, list[PunktZakresu]]
    szablony_pytan: list[SzablonPytania]
    struktura_argumentu: dict
    informacja_zwrotna: dict
    kwestie_do_omowienia: list[SzablonKwestii]
    dane_dla_modelu: dict
    limit_zadan_osp: int = 3

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaRozmowy:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))

    def szablon(self, id_: str) -> SzablonPytania:
        return next(s for s in self.szablony_pytan if s.id == id_)

    def kwestia(self, id_: str) -> SzablonKwestii:
        return next(k for k in self.kwestie_do_omowienia if k.id == id_)


# --- wejście i wyjście --------------------------------------------------------------


class KontekstRozmowy(BaseModel):
    """Dane spoza kroków 3–5, które podaje przełożony (wszystkie opcjonalne)."""

    cele: list[str] = Field(default_factory=list, max_length=20)
    """Cele wyznaczone na okres oceny (ocena okresowa, § 10 pkt 2 rozp. 2016)."""
    sprawozdanie_zlozone_w_terminie: bool | None = None
    """Pierwsza ocena: None = jeszcze nie wiadomo."""
    egzamin_obowiazkowy: bool | None = None
    fragment_sprawozdania: str | None = Field(default=None, max_length=2000)


class Powiazanie(BaseModel):
    typ: TypPowiazania
    kompetencja: str | None = None
    wskaznik_id: str | None = None
    wskaznik: str | None = None
    zadanie_osp: int | None = None
    przyklad: int | None = None
    """Indeks przykładu przy wskaźniku (od 0)."""


class Pytanie(BaseModel):
    id: str
    szablon: str
    tresc: str
    uzasadnienie: str
    powiazanie: Powiazanie
    adnotacje: list[SourceRef]


class Argument(BaseModel):
    kompetencja: str
    wskaznik_id: str
    wskaznik: str
    poziom: int
    etykieta: str
    zachowanie: str
    """Opis zachowania z modelu dla wybranego poziomu (dosłownie)."""
    zachowanie_zrodlo: SourceRef
    przyklad: str | None
    rezultat: str | None
    uwaga: str | None = None


class InformacjaZwrotna(BaseModel):
    mocne_strony: list[str]
    obszary_rozwoju: list[str]


class Kwestia(BaseModel):
    id: str
    tresc: str
    kompetencja: str | None = None
    wskaznik_id: str | None = None
    adnotacje: list[SourceRef]


class PlanRozmowy(BaseModel):
    proces_id: int
    sciezka: Sciezka
    wersja: str
    status: Literal["SUGESTIA — do edycji przez przełożonego"] = (
        "SUGESTIA — do edycji przez przełożonego"
    )
    oznaczenie: str
    zakres: list[PunktZakresu]
    pytania: list[Pytanie]
    argumenty: list[Argument]
    informacja_zwrotna: InformacjaZwrotna
    kwestie: list[Kwestia]
    tryb: Literal["SZABLONY"] = "SZABLONY"
    """Domyślnie bez modelu językowego; dane osobowe nie opuszczają aplikacji."""


# --- logika -------------------------------------------------------------------------


def _skrot(p: Przyklad | str, n: int = 220) -> str:
    t = p if isinstance(p, str) else f"{p.sytuacja} – {p.dzialanie} – {p.rezultat}"
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _w_zdaniu(tekst: str) -> str:
    """Nazwa wskaźnika lub opis wstawiany w zdanie: bez końcowej kropki."""
    return tekst.strip().rstrip(".").rstrip()


def _opis_poziomu(w: WskaznikOceny, poziom: int) -> str | None:
    return next((p.opis for p in w.poziomy if p.poziom == poziom), None)


def _warunek_spelniony(warunek: str | None, k: KontekstRozmowy) -> bool:
    if warunek is None:
        return True
    if warunek == "cele_wyznaczone":
        return bool(k.cele)
    if warunek == "egzamin_obowiazkowy":
        return k.egzamin_obowiazkowy is not False
    return True


def _dla_sciezki(s: SzablonPytania | SzablonKwestii, sciezka: Sciezka) -> bool:
    return s.sciezka is None or s.sciezka == sciezka


def przygotuj(
    stan: StanOceny,
    osp: OpisStanowiska | None,
    kontekst: KontekstRozmowy,
    konf: KonfiguracjaRozmowy,
    model: ModelKompetencji,
) -> PlanRozmowy:
    """``model``: model kompetencji (#30) – źródło opisów zachowań w argumentach."""
    zrodla_poziomow = {
        (w.id, p.poziom): p.adnotacja
        for k in model.kompetencje for w in k.wskazniki for p in w.poziomy
    }
    sciezka = stan.sciezka
    zakres = [p for p in konf.zakres_rozmowy[sciezka] if _warunek_spelniony(p.warunek, kontekst)]
    pytania: list[Pytanie] = []
    argumenty: list[Argument] = []
    mocne: list[str] = []
    obszary: list[str] = []
    kwestie: list[Kwestia] = []
    oczekiwany = 5  # „na poziomie oczekiwań” w skali modelu (1-3-5-7-9)
    etykiety = stan.skala.etykiety

    def dodaj(szablon_id: str, tresc: str, powiazanie: Powiazanie) -> None:
        s = konf.szablon(szablon_id)
        if powiazanie.typ == "przyklad" and any(p.tresc == tresc for p in pytania):
            return  # ten sam przykład przy kilku wskaźnikach – pytamy raz; pytania o wskaźniki zostają wszystkie
        pytania.append(
            Pytanie(
                id=f"{szablon_id}#{len(pytania) + 1}",
                szablon=s.id,
                tresc=tresc,
                uzasadnienie=s.uzasadnienie,
                powiazanie=powiazanie,
                adnotacje=s.adnotacje,
            )
        )

    fz = konf.informacja_zwrotna
    for kr in stan.kryteria:
        for w in kr.wskazniki:
            ocena = w.ocena
            baza = Powiazanie(typ="wskaznik", kompetencja=kr.nazwa, wskaznik_id=w.wskaznik_id, wskaznik=w.nazwa)
            standard = _w_zdaniu(_opis_poziomu(w, oczekiwany) or "")
            nazwa = _w_zdaniu(w.nazwa)

            if ocena is not None and ocena.brak_podstaw:
                k = konf.kwestia("kwestia.brak-podstaw")
                kwestie.append(
                    Kwestia(
                        id=k.id, tresc=k.tresc.format(wskaznik=nazwa), kompetencja=kr.nazwa,
                        wskaznik_id=w.wskaznik_id, adnotacje=k.adnotacje,
                    )
                )
                continue

            if ocena is None or ocena.poziom is None:
                # Jeszcze nie oceniony: pytanie otwierające o przykład.
                dodaj("pyt.wskaznik.przyklad", konf.szablon("pyt.wskaznik.przyklad").tresc.format(wskaznik=nazwa), baza)
                continue

            poziom = ocena.poziom
            przyklady = ocena.przyklady
            # Pole „Przykład z okresu” zapisuje uwagi (#46); bez pełnych przykładów one są przykładem.
            uwagi = (ocena.uwagi or "").strip()
            teksty = [_skrot(p) for p in przyklady] or ([_skrot(uwagi)] if uwagi else [])
            if teksty:
                for i, t in enumerate(teksty[:2]):
                    dodaj(
                        "pyt.wskaznik.powtarzalnosc",
                        konf.szablon("pyt.wskaznik.powtarzalnosc").tresc.format(przyklad=t),
                        baza.model_copy(update={"typ": "przyklad", "przyklad": i}),
                    )
            else:
                dodaj("pyt.wskaznik.przyklad", konf.szablon("pyt.wskaznik.przyklad").tresc.format(wskaznik=nazwa), baza)
            if poziom != oczekiwany and standard:
                dodaj(
                    "pyt.wskaznik.standard",
                    konf.szablon("pyt.wskaznik.standard").tresc.format(
                        wskaznik=nazwa, opis_na_poziomie_oczekiwan=standard
                    ),
                    baza,
                )

            opis = next((p for p in w.poziomy if p.poziom == poziom), None)
            pierwszy = przyklady[0] if przyklady else None
            zrodlo = zrodla_poziomow.get((w.wskaznik_id, poziom))
            if opis is not None and zrodlo is not None:
                argumenty.append(
                    Argument(
                        kompetencja=kr.nazwa,
                        wskaznik_id=w.wskaznik_id,
                        wskaznik=w.nazwa,
                        poziom=poziom,
                        etykieta=opis.etykieta,
                        zachowanie=opis.opis,
                        zachowanie_zrodlo=zrodlo,
                        przyklad=f"{pierwszy.sytuacja} – {pierwszy.dzialanie}" if pierwszy else (uwagi or None),
                        rezultat=pierwszy.rezultat if pierwszy else None,
                        uwaga=None if teksty else "Brak przykładu: dopisz sytuację, działanie i rezultat.",
                    )
                )

            if poziom > oczekiwany:
                mocne.append(
                    fz["szablon_mocnej_strony"].format(
                        wskaznik=nazwa, przyklad=_w_zdaniu(teksty[0]) if teksty else "(dopisz przykład)"
                    )
                )
            elif poziom < oczekiwany:
                obszary.append(
                    fz["szablon_obszaru_rozwoju"].format(wskaznik=nazwa, opis_na_poziomie_oczekiwan=standard)
                )

        kwestie.extend(_kwestie_kryterium(kr, sciezka, etykiety, konf))

    kwestie.extend(_kwestie_procesu(stan, sciezka, kontekst, konf))

    # Pytania spoza wskaźników: zadania z OSP, cele, sprawozdanie, rozwój.
    if sciezka == "okresowa" and osp is not None:
        for z in osp.zadania_dominujace[: konf.limit_zadan_osp]:
            dodaj(
                "pyt.osp.zadanie",
                konf.szablon("pyt.osp.zadanie").tresc.format(zadanie_osp=_w_zdaniu(z.tekst)),
                Powiazanie(typ="zadanie_osp", zadanie_osp=z.nr),
            )
    if sciezka == "okresowa":
        for cel in kontekst.cele:
            dodaj("pyt.cele", konf.szablon("pyt.cele").tresc.format(cel=cel), Powiazanie(typ="przepis"))
        dodaj("pyt.rozwoj.okresowa", konf.szablon("pyt.rozwoj.okresowa").tresc, Powiazanie(typ="przepis"))
    else:
        if kontekst.fragment_sprawozdania:
            dodaj(
                "pyt.sprawozdanie",
                konf.szablon("pyt.sprawozdanie").tresc.format(fragment_sprawozdania=kontekst.fragment_sprawozdania),
                Powiazanie(typ="przepis"),
            )
        dodaj("pyt.rozwoj.pierwsza", konf.szablon("pyt.rozwoj.pierwsza").tresc, Powiazanie(typ="przepis"))

    return PlanRozmowy(
        proces_id=stan.proces_id,
        sciezka=sciezka,
        wersja=konf.wersja,
        oznaczenie=konf.oznaczenie_sugestii,
        zakres=zakres,
        pytania=pytania,
        argumenty=argumenty,
        informacja_zwrotna=InformacjaZwrotna(mocne_strony=mocne, obszary_rozwoju=obszary),
        kwestie=kwestie,
    )


def _kwestie_kryterium(
    kr: KryteriumOceny, sciezka: Sciezka, etykiety: dict[int, str], konf: KonfiguracjaRozmowy
) -> list[Kwestia]:
    wynik: list[Kwestia] = []
    d, s = kr.decyzja, kr.sugestia
    if d is None:
        return wynik
    k = konf.kwestia("kwestia.odchylenie-od-sugestii")
    if s.punkty is not None and k.prog_poziomow is not None:
        roznica = abs(d.punkty - s.punkty) // 2  # skale mają krok 2 punkty (1-3-5-7-9, 3-5-7)
        if roznica >= k.prog_poziomow:
            wynik.append(
                Kwestia(
                    id=k.id,
                    tresc=k.tresc.format(
                        wybrany=etykiety.get(d.punkty, d.punkty),
                        sugerowany=etykiety.get(s.punkty, s.punkty),
                        roznica=roznica,
                    ) + f" (kryterium: {kr.nazwa})",
                    kompetencja=kr.nazwa,
                    adnotacje=k.adnotacje,
                )
            )
    k = konf.kwestia("kwestia.znacznie-ponizej")
    if _dla_sciezki(k, sciezka) and d.punkty == 1:
        wynik.append(
            Kwestia(id=k.id, tresc=k.tresc.format(kryterium=kr.nazwa), kompetencja=kr.nazwa, adnotacje=k.adnotacje)
        )
    return wynik


def _kwestie_procesu(
    stan: StanOceny, sciezka: Sciezka, kontekst: KontekstRozmowy, konf: KonfiguracjaRozmowy
) -> list[Kwestia]:
    wynik: list[Kwestia] = []
    if sciezka != "pierwsza":
        return wynik
    k = konf.kwestia("kwestia.sprawozdanie-niezlozone")
    if kontekst.sprawozdanie_zlozone_w_terminie is False:
        wynik.append(Kwestia(id=k.id, tresc=k.tresc, adnotacje=k.adnotacje))
    k = konf.kwestia("kwestia.dwie-oceny-3pkt")
    trojki = [kr.nazwa for kr in stan.kryteria if kr.decyzja is not None and kr.decyzja.punkty == 3]
    if len(trojki) > 1:
        wynik.append(Kwestia(id=k.id, tresc=k.tresc + f" ({', '.join(trojki)})", adnotacje=k.adnotacje))
    return wynik
