"""Logowanie kontami demo (token sesji) i autoryzacja egzekwowana w API."""

from __future__ import annotations

import hmac
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field

from .model import KonfiguracjaRol, Uzytkownik, _Model


class _DaneLogowania(_Model):
    login: str
    haslo: str = Field(alias="hasło")


class Autoryzacja:
    def __init__(self, konfig: KonfiguracjaRol) -> None:
        self.konfig = konfig
        self._sesje: dict[str, Uzytkownik] = {}

    def zaloguj(self, login: str, haslo: str) -> str:
        """Token sesji. Błędny login lub hasło: ``HTTPException(401)``."""
        for konto in self.konfig.konta:
            if konto.login == login and hmac.compare_digest(konto.haslo.encode(), haslo.encode()):
                token = secrets.token_urlsafe(32)
                self._sesje[token] = Uzytkownik(
                    login=konto.login, rola=konto.rola, osoba_id=konto.osoba_id
                )
                return token
        raise HTTPException(401, "Nieprawidłowy login lub hasło")

    def _z_naglowka(self, authorization: str | None = Header(default=None)) -> Uzytkownik:
        schemat, _, token = (authorization or "").partition(" ")
        uz = self._sesje.get(token) if schemat.lower() == "bearer" else None
        if uz is None:
            raise HTTPException(401, "Wymagane zalogowanie")
        return uz

    def _ma_akcje(self, uz: Uzytkownik, akcja: str) -> bool:
        akcje = self.konfig.uprawnienia.get(uz.rola, [])
        return "*" in akcje or akcja in akcje

    def wymagaj(self, akcja: str):
        """Zależność FastAPI zwracająca ``Uzytkownik``::

            @app.get("/pracownicy")
            def lista(uz: Uzytkownik = auth.wymagaj("czytaj")): ...

        Brak lub nieznany token (``Authorization: Bearer``): 401. Rola bez akcji: 403.
        """

        def zaleznosc(uz: Uzytkownik = Depends(self._z_naglowka)) -> Uzytkownik:
            if not self._ma_akcje(uz, akcja):
                raise HTTPException(403, "Brak uprawnienia")
            return uz

        return Depends(zaleznosc)

    def moze(self, uz: Uzytkownik, zasob: str, rekord: dict, akcja: str) -> bool:
        """Rola ma akcję, a przy regułach dostępu do zasobu rekord spełnia którąś z nich."""
        if not self._ma_akcje(uz, akcja):
            return False
        reguly = [r for r in self.konfig.reguly_dostepu if r.zasob == zasob and r.rola == uz.rola]
        if not reguly:
            return True
        for r in reguly:
            szukana = getattr(uz, r.pole_uzytkownika, None)
            wartosc = rekord.get(r.pole)
            if szukana is not None and (
                szukana in wartosc if isinstance(wartosc, list) else szukana == wartosc
            ):
                return True
        return False

    def sprawdz(self, uz: Uzytkownik, zasob: str, rekord: dict, akcja: str) -> None:
        """``HTTPException(403)``, gdy ``moze`` zwraca ``False``."""
        if not self.moze(uz, zasob, rekord, akcja):
            raise HTTPException(403, "Brak dostępu do rekordu")

    def filtruj(self, uz: Uzytkownik, zasob: str, rekordy: list[dict], akcja: str) -> list[dict]:
        """Rekordy, dla których ``moze`` zwraca ``True``."""
        return [r for r in rekordy if self.moze(uz, zasob, r, akcja)]

    def router(self) -> APIRouter:
        """``POST /auth/login`` z ``{"login", "hasło"}`` zwraca ``{"token"}``."""
        router = APIRouter()

        @router.post("/auth/login")
        def login(dane: _DaneLogowania) -> dict:
            return {"token": self.zaloguj(dane.login, dane.haslo)}

        return router
