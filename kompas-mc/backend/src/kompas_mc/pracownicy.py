"""API pracowników z mocka QNT i notatek przełożonego; uprawnienia z ``konfiguracja/role.yaml``."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from pydantic import BaseModel, Field

from .qnt import MockQnt, Pracownik


class NowaNotatka(BaseModel):
    tresc: str = Field(min_length=1, max_length=4000)


class Notatka(BaseModel):
    """Notatka przełożonego o podwładnym. HR i oceniany jej nie widzą."""

    id: int
    osoba_id: str
    autor: str
    tresc: str
    czas: datetime


def router(auth: Autoryzacja, qnt: MockQnt) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["pracownicy (mock QNT)"])

    @r.get("/ja")
    def ja(uz: Uzytkownik = auth.wymagaj("pracownicy.czytaj")) -> Uzytkownik:
        """Zalogowany użytkownik i jego rola."""
        return uz

    @r.get("/pracownicy")
    def lista(uz: Uzytkownik = auth.wymagaj("pracownicy.czytaj")) -> list[Pracownik]:
        """Przełożony dostaje swoich podwładnych, oceniany siebie, HR wszystkich."""
        rekordy = [p.model_dump() for p in qnt.pracownicy]
        return [
            qnt.pracownik(r["osoba_id"])
            for r in auth.filtruj(uz, "pracownik", rekordy, "pracownicy.czytaj")
        ]

    def dostepny(osoba_id: str, uz: Uzytkownik, akcja: str) -> Pracownik:
        p = qnt.pracownik(osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), akcja)
        return p

    @r.get("/pracownicy/{osoba_id}")
    def jeden(osoba_id: str, uz: Uzytkownik = auth.wymagaj("pracownicy.czytaj")) -> Pracownik:
        """404, gdy osoby nie ma w QNT; 403, gdy osoba jest poza zakresem użytkownika."""
        return dostepny(osoba_id, uz, "pracownicy.czytaj")

    @r.get("/pracownicy/{osoba_id}/notatki")
    def notatki(
        osoba_id: str, request: Request, uz: Uzytkownik = auth.wymagaj("notatki.czytaj")
    ) -> list[Notatka]:
        """Notatki przełożonego o podwładnym; HR i oceniany dostają 403."""
        dostepny(osoba_id, uz, "notatki.czytaj")
        wiersze = request.app.state.baza.execute(
            "SELECT id, osoba_id, autor, tresc, czas FROM notatki WHERE osoba_id = ? ORDER BY id",
            (osoba_id,),
        )
        return [
            Notatka(id=i, osoba_id=o, autor=a, tresc=t, czas=datetime.fromisoformat(c))
            for i, o, a, t, c in wiersze
        ]

    @r.post("/pracownicy/{osoba_id}/notatki", status_code=201)
    def dodaj_notatke(
        osoba_id: str,
        body: NowaNotatka,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("notatki.zapisz"),
    ) -> Notatka:
        dostepny(osoba_id, uz, "notatki.zapisz")
        czas = datetime.now(UTC)
        baza = request.app.state.baza
        with baza:
            kursor = baza.execute(
                "INSERT INTO notatki (osoba_id, autor, tresc, czas) VALUES (?, ?, ?, ?)",
                (osoba_id, uz.login, body.tresc, czas.isoformat()),
            )
        return Notatka(
            id=kursor.lastrowid, osoba_id=osoba_id, autor=uz.login, tresc=body.tresc, czas=czas
        )

    return r
