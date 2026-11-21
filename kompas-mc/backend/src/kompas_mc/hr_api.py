"""API panelu HR (#38): lista procesów z terminami, zagrożone, przypomnienia, skrzynka."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik

from .hr import (
    NowePrzypomnienie,
    PropozycjaPrzypomnienia,
    Przypomnienie,
    WierszPanelu,
    propozycja,
    skrzynka,
    wiersz,
    wyslij,
)
from .procesy import _KOLUMNY, _z_wiersza, wczytaj_proces
from .qnt import MockQnt


def router(auth: Autoryzacja, qnt: MockQnt) -> APIRouter:
    """Źródło terminów: ``app.state.terminy`` (domyślnie puste do #32/#34);
    dzień odniesienia: ``app.state.dzis`` (funkcja, domyślnie dzisiejsza data)."""
    r = APIRouter(prefix="/api/hr", tags=["panel HR"])

    def dzis(request: Request) -> date:
        f = getattr(request.app.state, "dzis", None)
        return f() if f else date.today()

    def wiersze(request: Request) -> list[WierszPanelu]:
        terminy = request.app.state.terminy
        d = dzis(request)
        wynik = []
        for w in request.app.state.baza.execute(f"SELECT {_KOLUMNY} FROM procesy ORDER BY id").fetchall():
            proces = _z_wiersza(w)
            p = qnt.pracownik(proces.osoba_id)
            if p is not None:
                wynik.append(wiersz(proces, p, terminy(proces, p, d), d))
        return wynik

    @r.get("/procesy")
    def lista(
        request: Request, zagrozone: bool = False, uz: Uzytkownik = auth.wymagaj("hr.panel")
    ) -> list[WierszPanelu]:
        """Procesy: ścieżka, arkusz, krok, status, najbliższy termin. ``zagrozone=true``:
        tylko procesy w toku z terminem w ciągu 7 dni lub po terminie. Bez treści ocen."""
        w = wiersze(request)
        return [x for x in w if x.zagrozony] if zagrozone else w

    @r.get("/przypomnienia/propozycje")
    def propozycje(
        request: Request, uz: Uzytkownik = auth.wymagaj("hr.panel")
    ) -> list[PropozycjaPrzypomnienia]:
        """Przypomnienia proponowane przez system dla procesów zagrożonych."""
        return [p for p in (propozycja(w) for w in wiersze(request)) if p is not None]

    @r.post("/przypomnienia", status_code=201)
    def wyslij_przypomnienie(
        request: Request, body: NowePrzypomnienie, uz: Uzytkownik = auth.wymagaj("hr.przypomnienia")
    ) -> Przypomnienie:
        """Wysłanie do mockowanej skrzynki nadawczej i wpis w historii procesu."""
        baza = request.app.state.baza
        if wczytaj_proces(baza, body.proces_id) is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        wyslane = wyslij(baza, body, uz.login, datetime.now(UTC))
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(
            uz.login, "proces", str(body.proces_id), {},
            {"przypomnienie": {"id": wyslane.id, "adresat": body.adresat, "tresc": body.tresc}},
            "hr-1",
        )
        return wyslane

    @r.get("/skrzynka")
    def skrzynka_nadawcza(
        request: Request, proces_id: int | None = None, uz: Uzytkownik = auth.wymagaj("hr.panel")
    ) -> list[Przypomnienie]:
        return skrzynka(request.app.state.baza, proces_id)

    return r


def router_terminow(auth: Autoryzacja, qnt: MockQnt) -> APIRouter:
    """Najbliższy termin każdego procesu, który użytkownik widzi: przełożony podwładnych, HR wszystkich,
    oceniany siebie. Te same wiersze co w panelu HR (bez treści ocen); z nich pulpit liczy KPI terminów."""
    r = APIRouter(prefix="/api", tags=["panel HR"])

    @r.get("/terminy")
    def terminy(request: Request, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> list[WierszPanelu]:
        zrodlo = request.app.state.terminy
        f = getattr(request.app.state, "dzis", None)
        d = f() if f else date.today()
        wynik = []
        for w in request.app.state.baza.execute(f"SELECT {_KOLUMNY} FROM procesy ORDER BY id").fetchall():
            proces = _z_wiersza(w)
            p = qnt.pracownik(proces.osoba_id)
            if p is not None and auth.moze(uz, "pracownik", p.model_dump(), "ocena.czytaj"):
                wynik.append(wiersz(proces, p, zrodlo(proces, p, d), d))
        return wynik

    return r
