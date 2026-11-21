"""API wersji metodyki (#39): lista, nowa wersja, zatwierdzenie z osobą i datą."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from pydantic import BaseModel

from .metodyka import BladMetodyki, NowaWersja, RejestrMetodyk, WersjaMetodyki, zrzut


class StanMetodyki(BaseModel):
    aktywna: str
    wersje: list[WersjaMetodyki]


class Zatwierdzenie(BaseModel):
    osoba: str | None = None
    """Imię i nazwisko zatwierdzającego; domyślnie login."""
    dzien: date | None = None


def router(auth: Autoryzacja) -> APIRouter:
    r = APIRouter(prefix="/api/metodyka", tags=["metodyka sugestii (#39)"])

    def rejestr(request: Request) -> RejestrMetodyk:
        return request.app.state.metodyki

    @r.get("")
    def lista(request: Request, _uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> StanMetodyki:
        """Wersje metodyki sugestii i mapowania 5→3 oraz wersja aktywna."""
        return StanMetodyki(aktywna=rejestr(request).aktywna().id, wersje=rejestr(request).lista())

    @r.post("")
    def nowa(
        body: NowaWersja, request: Request, uz: Uzytkownik = auth.wymagaj("metodyka.zarzadzaj")
    ) -> WersjaMetodyki:
        """Zmiana parametrów tworzy nową wersję (PROJEKT). Do ocen trafia dopiero po zatwierdzeniu."""
        w = rejestr(request).nowa(body, uz.login)
        request.app.state.dziennik.zapisz(uz.login, "metodyka", w.id, None, zrzut(w), w.id)
        return w

    @r.post("/{metodyka_id}/zatwierdz")
    def zatwierdz(
        metodyka_id: str,
        body: Zatwierdzenie,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("metodyka.zarzadzaj"),
    ) -> WersjaMetodyki:
        """Zatwierdzenie z osobą i datą; poprzednia zatwierdzona wersja staje się ZASTĄPIONA."""
        try:
            przed = zrzut(rejestr(request).wersja(metodyka_id))
            w = rejestr(request).zatwierdz(metodyka_id, body.osoba or uz.login, body.dzien or date.today())
        except KeyError:
            raise HTTPException(404, f"Nie ma wersji metodyki {metodyka_id}")
        except BladMetodyki as e:
            raise HTTPException(409, str(e))
        request.app.state.dziennik.zapisz(uz.login, "metodyka", w.id, przed, zrzut(w), w.id)
        return w

    return r
