"""API kroków 3–5 (#31): oceny wskaźników z przykładami, sugestia poziomu, decyzja przełożonego."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from pydantic import TypeAdapter

from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import (
    BladOceny,
    Decyzja,
    KonfiguracjaOceny,
    OcenaWskaznika,
    StanOceny,
    ZapisDecyzji,
    ZapisWskaznikow,
    scal_decyzje,
    scal_oceny,
    zbuduj_stan,
)
from .procesy import ProcesOceny, wczytaj_proces
from .qnt import MockQnt

_OCENY = TypeAdapter(dict[str, OcenaWskaznika])
_DECYZJE = TypeAdapter(dict[str, Decyzja])


def _wczytaj_dane(baza, proces_id: int) -> tuple[dict[str, OcenaWskaznika], dict[str, Decyzja]]:
    o, d = baza.execute(
        "SELECT oceny_wskaznikow, decyzje FROM procesy WHERE id = ?", (proces_id,)
    ).fetchone()
    return (_OCENY.validate_json(o) if o else {}), (_DECYZJE.validate_json(d) if d else {})


def router(auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2) -> APIRouter:
    """Konfiguracja kroków 3–5 pochodzi z rejestru metodyk (``app.state.metodyki``, #39)."""
    r = APIRouter(prefix="/api", tags=["kroki 3–5: zachowania, sugestia, decyzja"])

    def proces_dostepny(request: Request, proces_id: int, uz: Uzytkownik, akcja: str) -> ProcesOceny:
        proces = wczytaj_proces(request.app.state.baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        p = qnt.pracownik(proces.osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), akcja)
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")
        return proces

    def rejestr(request: Request) -> RejestrMetodyk:
        return request.app.state.metodyki

    def konf_procesu(request: Request, proces: ProcesOceny) -> KonfiguracjaOceny:
        """Wersja metodyki przypięta do procesu (#39), a przed pierwszym zapisem – aktywna."""
        r = rejestr(request)
        return r.konfiguracja(r.dla_procesu(proces.id))

    def stan(request: Request, proces: ProcesOceny) -> StanOceny:
        oceny, decyzje = _wczytaj_dane(request.app.state.baza, proces.id)
        return zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model,
            konf_procesu(request, proces),
        )

    def zapisz(
        request: Request, uz: Uzytkownik, proces: ProcesOceny, kolumna: str, wartosc: str, przed, po
    ) -> StanOceny:
        baza = request.app.state.baza
        metodyka = rejestr(request).przypnij(proces.id)
        with baza:
            baza.execute(f"UPDATE procesy SET {kolumna} = ? WHERE id = ?", (wartosc, proces.id))
        nowy = stan(request, proces)
        krok = max(proces.krok, 5 if nowy.kompletnosc.wszystkie_decyzje else 3)
        with baza:
            baza.execute("UPDATE procesy SET krok = ? WHERE id = ?", (krok, proces.id))
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "proces", str(proces.id), przed, po, metodyka.id)
        return nowy

    @r.get("/procesy/{proces_id}/ocena")
    def odczyt(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc")
    ) -> StanOceny:
        """Wskaźniki wybrane w kroku 2 z opisami 5 zachowań, oceny i przykłady, sugestia poziomu
        każdego kryterium (z etykietą metodyki) i decyzja przełożonego."""
        return stan(request, proces_dostepny(request, proces_id, uz, "ocena.tresc"))

    @r.put("/procesy/{proces_id}/ocena/wskazniki")
    def wskazniki(
        proces_id: int,
        body: ZapisWskaznikow,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanOceny:
        """Krok 3: wybór opisu zachowania (1/3/5/7/9) albo „brak podstaw do oceny” i przykłady
        S-D-R. Scala z poprzednim stanem; ``null`` usuwa ocenę wskaźnika."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        obecne, _ = _wczytaj_dane(request.app.state.baza, proces.id)
        try:
            nowe = scal_oceny(obecne, body, proces.krok2)
        except BladOceny as e:
            raise HTTPException(422, {"komunikat": "Niepoprawne oceny wskaźników.", "bledy": e.args[0]})
        zrzut = lambda d: json.loads(_OCENY.dump_json(d))  # noqa: E731
        return zapisz(
            request, uz, proces, "oceny_wskaznikow", _OCENY.dump_json(nowe).decode(),
            {"oceny_wskaznikow": zrzut(obecne)}, {"oceny_wskaznikow": zrzut(nowe)},
        )

    @r.put("/procesy/{proces_id}/ocena/decyzje")
    def decyzje(
        proces_id: int,
        body: ZapisDecyzji,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanOceny:
        """Krok 5: ocena cząstkowa kryterium wybrana przez przełożonego. Punkty ze skali ścieżki;
        odejście od sugestii wymaga uzasadnienia. ``null`` cofa decyzję."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        _, obecne = _wczytaj_dane(request.app.state.baza, proces.id)
        try:
            nowe = scal_decyzje(
                obecne, body, stan(request, proces), konf_procesu(request, proces), uz.login, datetime.now(UTC)
            )
        except BladOceny as e:
            raise HTTPException(422, {"komunikat": "Niepoprawne decyzje.", "bledy": e.args[0]})
        zrzut = lambda d: {k: {"punkty": v.punkty, "uzasadnienie": v.uzasadnienie} for k, v in d.items()}  # noqa: E731
        return zapisz(
            request, uz, proces, "decyzje", _DECYZJE.dump_json(nowe).decode(),
            {"decyzje": zrzut(obecne)}, {"decyzje": zrzut(nowe)},
        )

    return r
