"""Samoocena pracownika (#8, spec #2): poziom 1/3/5/7/9 albo „brak zdania” przy wskaźnikach z kroku 2.

Samoocena jest materiałem do rozmowy i nie wchodzi do sugestii ani do oceny (reguła
``samoocena.poza-sugestia`` w ``konfiguracja/samoocena.yaml``, DECYZJA_PROJEKTOWA). Pracownik
zapisuje szkic i przekazuje go; po przekazaniu nie zmienia, a przełożony dopiero wtedy widzi treść.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, model_validator

from .kompetencje import ModelKompetencji
from .krok2 import WyborKroku2
from .ocena import OcenaWskaznika, OpisPoziomuWidok, Przyklad

Status = Literal["brak", "szkic", "przekazana"]


class _Regula(BaseModel):
    id: str
    opis: str
    adnotacje: list[SourceRef]


class KonfiguracjaSamooceny(BaseModel):
    poziomy: list[int]
    prog_rozbieznosci: int
    regula: _Regula

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaSamooceny:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))


class PozycjaSamooceny(BaseModel):
    poziom: Literal[1, 3, 5, 7, 9] | None = None
    brak_zdania: bool = False
    przyklad: Przyklad | None = None

    @model_validator(mode="after")
    def _wykluczanie(self) -> PozycjaSamooceny:
        if (self.poziom is None) == (not self.brak_zdania):
            raise ValueError("Podaj poziom albo „brak zdania” (null usuwa pozycję).")
        return self


class ZapisSamooceny(BaseModel):
    """Szkic: scala z zapisanym; ``null`` usuwa pozycję wskaźnika."""

    wskazniki: dict[str, PozycjaSamooceny | None]


class WskaznikSamooceny(BaseModel):
    wskaznik_id: str
    nazwa: str
    kompetencja_id: str
    kryterium: str
    poziomy: list[OpisPoziomuWidok]
    pozycja: PozycjaSamooceny | None


class Samoocena(BaseModel):
    proces_id: int
    status: Status
    przekazano: datetime | None
    tresc_widoczna: bool
    """False dla przełożonego przed przekazaniem: widzi tylko status."""
    wskazniki: list[WskaznikSamooceny]
    wypelniono: int
    wybrano: int
    regula: _Regula


class BladSamooceny(Exception):
    """Lista komunikatów walidacji zapisu (422)."""


# ---------------------------------------------------------------- baza


def wczytaj(baza: sqlite3.Connection, proces_id: int) -> tuple[Status, datetime | None, dict[str, PozycjaSamooceny]]:
    w = baza.execute("SELECT status, przekazano FROM samoocena WHERE proces_id = ?", (proces_id,)).fetchone()
    status: Status = w[0] if w else "brak"
    przekazano = datetime.fromisoformat(w[1]) if w and w[1] else None
    pozycje = {
        wid: PozycjaSamooceny(
            poziom=poziom, brak_zdania=bool(brak), przyklad=Przyklad.model_validate_json(p) if p else None
        )
        for wid, poziom, brak, p in baza.execute(
            "SELECT wskaznik_id, poziom, brak_zdania, przyklad FROM samoocena_pozycje WHERE proces_id = ?",
            (proces_id,),
        )
    }
    return status, przekazano, pozycje


def zapisz_szkic(
    baza: sqlite3.Connection, proces_id: int, zapis: ZapisSamooceny, wybor: WyborKroku2, teraz: datetime
) -> None:
    dozwolone = {w.id for k in wybor.kryteria for w in k.wskazniki}
    obce = sorted(set(zapis.wskazniki) - dozwolone)
    if obce:
        raise BladSamooceny([f"Wskaźnik spoza kroku 2: {w}" for w in obce])
    with baza:
        baza.execute(
            "INSERT INTO samoocena (proces_id, status, zmieniono) VALUES (?, 'szkic', ?)"
            " ON CONFLICT(proces_id) DO UPDATE SET zmieniono = excluded.zmieniono",
            (proces_id, teraz.isoformat()),
        )
        for wid, p in zapis.wskazniki.items():
            if p is None:
                baza.execute("DELETE FROM samoocena_pozycje WHERE proces_id = ? AND wskaznik_id = ?", (proces_id, wid))
                continue
            baza.execute(
                "INSERT INTO samoocena_pozycje (proces_id, wskaznik_id, poziom, brak_zdania, przyklad)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT(proces_id, wskaznik_id) DO UPDATE SET"
                " poziom = excluded.poziom, brak_zdania = excluded.brak_zdania, przyklad = excluded.przyklad",
                (proces_id, wid, p.poziom, int(p.brak_zdania), p.przyklad.model_dump_json() if p.przyklad else None),
            )


def przekaz(baza: sqlite3.Connection, proces_id: int, wybor: WyborKroku2, teraz: datetime) -> None:
    """Przekazanie wymaga pozycji przy każdym wskaźniku z kroku 2 (poziom albo „brak zdania”)."""
    _, _, pozycje = wczytaj(baza, proces_id)
    brakuje = [w.nazwa for k in wybor.kryteria for w in k.wskazniki if w.id not in pozycje]
    if brakuje:
        raise BladSamooceny([f"Brak odpowiedzi: {n}" for n in brakuje])
    with baza:
        baza.execute(
            "UPDATE samoocena SET status = 'przekazana', przekazano = ?, zmieniono = ? WHERE proces_id = ?",
            (teraz.isoformat(), teraz.isoformat(), proces_id),
        )


# ---------------------------------------------------------------- widok


def zbuduj(
    proces_id: int,
    wybor: WyborKroku2,
    model: ModelKompetencji,
    status: Status,
    przekazano: datetime | None,
    pozycje: dict[str, PozycjaSamooceny],
    konf: KonfiguracjaSamooceny,
    tresc_widoczna: bool,
) -> Samoocena:
    wskazniki = []
    for k in wybor.kryteria:
        komp = model.kompetencja(k.kompetencja_id)
        po_id = {w.id: w for w in komp.wskazniki} if komp else {}
        for w in k.wskazniki:
            mw = po_id.get(w.id)
            wskazniki.append(
                WskaznikSamooceny(
                    wskaznik_id=w.id,
                    nazwa=w.nazwa,
                    kompetencja_id=k.kompetencja_id,
                    kryterium=k.nazwa,
                    poziomy=[
                        OpisPoziomuWidok(poziom=p.poziom, etykieta=p.etykieta, opis=p.opis)
                        for p in (mw.poziomy if mw else [])
                    ],
                    pozycja=pozycje.get(w.id) if tresc_widoczna else None,
                )
            )
    return Samoocena(
        proces_id=proces_id,
        status=status,
        przekazano=przekazano,
        tresc_widoczna=tresc_widoczna,
        wskazniki=wskazniki,
        wypelniono=sum(1 for w in wskazniki if w.pozycja is not None),
        wybrano=len(wskazniki),
        regula=konf.regula,
    )


def rozbieznosc(samo: PozycjaSamooceny | None, ocena: OcenaWskaznika | None, prog: int) -> bool | None:
    """True, gdy oba poziomy są podane i różnią się o co najmniej ``prog``; None, gdy nie ma czego porównać."""
    if samo is None or ocena is None or samo.poziom is None or ocena.poziom is None:
        return None
    return abs(samo.poziom - ocena.poziom) >= prog


def zrzut(pozycje: dict[str, PozycjaSamooceny]) -> dict:
    """Postać do dziennika zmian."""
    return {k: json.loads(v.model_dump_json()) for k, v in pozycje.items()}


KOMUNIKAT_PRZED_PRZEKAZANIEM = "Ocena przełożonego będzie widoczna po przekazaniu samooceny."


def ukryj_przed_przekazaniem(auth, uz, rekord: dict, baza: sqlite3.Connection, proces) -> None:
    """Pracownik (samoocena.zapisz) zobaczy treść oceny przełożonego dopiero po przekazaniu samooceny (#9),
    żeby jej nie przepisywał; dotyczy każdego odczytu treści (ocena, wynik, arkusz, PDF), nie tylko kroku 3.
    Po zakończeniu oceny (§ 12) pracownik zawsze widzi ocenę i dostaje kopię arkusza."""
    from fastapi import HTTPException

    if proces.status == "W_TOKU" and auth.moze(uz, "pracownik", rekord, "samoocena.zapisz"):
        # Pierwsza ocena nie ma samooceny: oceniany widzi punkty tylko przez ścieżkę pierwszej oceny, po sporządzeniu
        # oceny na piśmie (pierwsza_ocena_api), więc przekazanie samooceny nie odsłania tu ocen przełożonego.
        if proces.sciezka == "pierwsza":
            raise HTTPException(403, "Pierwszą ocenę zobaczysz po jej sporządzeniu na piśmie przez przełożonego.")
        if wczytaj(baza, proces.id)[0] != "przekazana":
            raise HTTPException(403, KOMUNIKAT_PRZED_PRZEKAZANIEM)
