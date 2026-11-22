"""Rejestr operacji: kto, co, komu i z jakim skutkiem (Karol 22.11 02:11, rada 3/3 CONDITIONAL_GO).

Warstwa HTTP zapisuje każdą zmianę (żądanie inne niż GET), pobranie dokumentu, wybrane odczyty danych
osobowych i każdą odmowę 401/403, także gdy obsługa żądania rzuci wyjątek. Trasa może dopisać szczegóły
przez ``ustaw_szczegoly`` (np. tryb i dostawca modelu AI); przechodzą tylko pola z ``DOZWOLONE_SZCZEGOLY``,
bez treści żądań, odpowiedzi, notatek, promptów i tokenów. Wpisy są tylko dopisywane (``Dziennik.operacja``).
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date, timedelta
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Query, Request, Response
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

Wynik = Literal["ok", "odmowa", "blad"]

# Odczyty danych osobowych zapisywane mimo GET (RODO art. 5 ust. 2, rozliczalność). Listy i słowniki pomijamy
# (pulpit odpytuje je przy każdym wejściu), pobrania dokumentów łapie _czy_dokument.
ODCZYTY = frozenset({
    "/api/pracownicy/{osoba_id}",
    "/api/pracownicy/{osoba_id}/poprzednia-ocena",
    "/api/pracownicy/{osoba_id}/notatki",
    "/api/pracownicy/{osoba_id}/opis",
    "/api/procesy/{proces_id}/ocena",
    "/api/procesy/{proces_id}/wynik-okresowy",
    "/api/procesy/{proces_id}/arkusz-okresowy",
    "/api/procesy/{proces_id}/pierwsza-ocena",
    "/api/procesy/{proces_id}/samoocena",
    "/api/rejestr",
})
POMIJANE = frozenset({"/api/zdrowie"})
DOZWOLONE_SZCZEGOLY = frozenset({
    "deklarowany_login", "tryb", "dostawca", "model", "walidacja", "odrzuceni", "pokrycie", "liczba", "format",
})


def ustaw_szczegoly(request: Request, **pola: object) -> None:
    """Szczegóły wpisu rejestru dla bieżącego żądania (tylko pola z ``DOZWOLONE_SZCZEGOLY``)."""
    nieznane = set(pola) - DOZWOLONE_SZCZEGOLY
    if nieznane:
        raise ValueError(f"pola spoza listy dozwolonych: {sorted(nieznane)}")
    biezace = getattr(request.state, "rejestr", None) or {}
    request.state.rejestr = {**biezace, **pola}


def ustaw_osobe(request: Request, osoba_id: str) -> None:
    """Osoba oceniana dla wpisu, gdy nie wynika ze ścieżki (np. rozpoczęcie procesu z ``osoba_id`` w treści)."""
    request.state.rejestr_osoba = osoba_id[:32]


def _czy_dokument(trasa: str) -> bool:
    return trasa.endswith((".pdf", ".csv", "/pdf"))


def czy_rejestrowac(metoda: str, trasa: str, status: int) -> bool:
    if trasa in POMIJANE:
        return False
    return status in (401, 403) or metoda != "GET" or _czy_dokument(trasa) or trasa in ODCZYTY


def wynik(status: int) -> Wynik:
    return "ok" if status < 400 else "odmowa" if status in (401, 403) else "blad"


def _krotko(wartosc: object, dlugosc: int = 200) -> object:
    if isinstance(wartosc, str):
        return wartosc[:dlugosc]
    if isinstance(wartosc, list):
        return [_krotko(w, 64) for w in wartosc[:20]]
    return wartosc if isinstance(wartosc, int | float | bool) or wartosc is None else str(wartosc)[:dlugosc]


def _oceniany(baza: sqlite3.Connection, parametry: dict[str, str]) -> str | None:
    if "osoba_id" in parametry:
        return parametry["osoba_id"][:32]
    if "proces_id" in parametry and parametry["proces_id"].isdigit():
        wiersz = baza.execute("SELECT osoba_id FROM procesy WHERE id = ?", (int(parametry["proces_id"]),)).fetchone()
        return wiersz[0] if wiersz else None
    return None


def _etykieta(trasa: object, metoda: str, sciezka: str) -> tuple[str, str]:
    """Stały kod akcji (nazwa funkcji trasy) i etykieta po ludzku (pierwsze zdanie opisu trasy)."""
    nazwa = getattr(trasa, "name", None)
    opis = (getattr(trasa, "description", "") or "").strip().split("\n")[0].strip()
    return (nazwa or f"{metoda} {sciezka}"), (opis.rstrip(".") or f"{metoda} {sciezka}")


def zainstaluj(app: FastAPI, auth: Autoryzacja) -> None:
    """Warstwa HTTP rejestru; czyta ``app.state.dziennik`` i ``app.state.baza`` utworzone przy starcie."""

    @app.middleware("http")
    async def rejestr_operacji(request: Request, call_next):
        poczatek = perf_counter()
        request_id = uuid4().hex[:16]
        status = 500
        try:
            odpowiedz = await call_next(request)
            status = odpowiedz.status_code
            odpowiedz.headers["X-Request-Id"] = request_id
            return odpowiedz
        finally:
            trasa = request.scope.get("route")
            sciezka = getattr(trasa, "path", None)
            if sciezka and czy_rejestrowac(request.method, sciezka, status):
                parametry = {k: str(v)[:64] for k, v in (request.scope.get("path_params") or {}).items()}
                akcja, etykieta = _etykieta(trasa, request.method, sciezka)
                uz: Uzytkownik | None = auth.kto(request.headers.get("authorization"))
                deklarowany = (getattr(request.state, "rejestr", None) or {}).get("deklarowany_login")
                if uz is None and deklarowany and status < 400:  # udane logowanie: konto potwierdzone hasłem
                    konto = next((k for k in auth.konfig.konta if k.login == deklarowany), None)
                    uz = Uzytkownik(login=konto.login, rola=konto.rola, osoba_id=konto.osoba_id) if konto else None
                szczegoly = {
                    k: _krotko(v) for k, v in (getattr(request.state, "rejestr", None) or {}).items()
                    if k in DOZWOLONE_SZCZEGOLY
                }
                wpis = {
                    "request_id": request_id, "aktor_login": uz.login if uz else None,
                    "aktor_rola": uz.rola if uz else None, "aktor_osoba": uz.osoba_id if uz else None,
                    "akcja": akcja, "etykieta": etykieta, "metoda": request.method, "trasa": sciezka,
                    "obiekt": json.dumps(parametry, ensure_ascii=False) if parametry else None,
                    "wynik": wynik(status), "status": status,
                    "czas_ms": round((perf_counter() - poczatek) * 1000), "szczegoly": szczegoly,
                }
                stan = request.app.state

                wskazana = getattr(request.state, "rejestr_osoba", None)

                def zapisz() -> None:
                    wpis["oceniany_osoba"] = wskazana or _oceniany(stan.baza, parametry)
                    stan.dziennik.operacja(**wpis)

                await run_in_threadpool(zapisz)


class WpisRejestru(BaseModel):
    id: int
    czas: str
    request_id: str | None
    aktor_login: str | None
    aktor_rola: str | None
    aktor_osoba: str | None
    akcja: str
    etykieta: str | None
    metoda: str | None
    trasa: str | None
    obiekt: str | None
    oceniany_osoba: str | None
    wynik: Wynik
    status: int | None
    czas_ms: int | None
    szczegoly: dict


class StronaRejestru(BaseModel):
    wpisy: list[WpisRejestru]
    razem: int
    strona: int
    na_stronie: int


def _filtry(od: date | None, do: date | None, uzytkownik: str | None, akcja: str | None,
            wynik: Wynik | None, osoba: str | None) -> dict:
    return {
        "od": od.isoformat() if od else None,
        "do": (do + timedelta(days=1)).isoformat() if do else None,
        "aktor": uzytkownik, "akcja": akcja, "wynik": wynik, "osoba": osoba,
    }


_GROZNE = ("=", "+", "-", "@", "\t", "\r")


def _do_csv(wartosc: object) -> str:
    """Komórka CSV bez wykonywania formuł w arkuszu (wiodące = + - @ dostają apostrof)."""
    tekst = "" if wartosc is None else wartosc if isinstance(wartosc, str) else json.dumps(wartosc, ensure_ascii=False)
    return f"'{tekst}" if tekst.startswith(_GROZNE) else tekst


def router(auth: Autoryzacja) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["rejestr operacji"])

    @r.get("/rejestr")
    def rejestr(
        request: Request,
        od: date | None = None, do: date | None = None, uzytkownik: str | None = None,
        akcja: str | None = None, wynik: Wynik | None = None, osoba: str | None = None,
        strona: int = Query(1, ge=1), na_stronie: int = Query(50, ge=1, le=200),
        _uz: Uzytkownik = auth.wymagaj("rejestr.czytaj"),
    ) -> StronaRejestru:
        """Podgląd rejestru operacji (kto, co, komu i z jakim skutkiem), od najnowszych."""
        dziennik: Dziennik = request.app.state.dziennik
        wpisy, razem = dziennik.operacje(
            **_filtry(od, do, uzytkownik, akcja, wynik, osoba), limit=na_stronie, offset=(strona - 1) * na_stronie,
        )
        return StronaRejestru(wpisy=wpisy, razem=razem, strona=strona, na_stronie=na_stronie)

    @r.get("/rejestr.csv", response_class=Response)
    def rejestr_csv(
        request: Request,
        od: date | None = None, do: date | None = None, uzytkownik: str | None = None,
        akcja: str | None = None, wynik: Wynik | None = None, osoba: str | None = None,
        _uz: Uzytkownik = auth.wymagaj("rejestr.czytaj"),
    ) -> Response:
        """Eksport rejestru operacji do CSV (do 10 000 wpisów, filtry jak w podglądzie)."""
        dziennik: Dziennik = request.app.state.dziennik
        wpisy, _ = dziennik.operacje(**_filtry(od, do, uzytkownik, akcja, wynik, osoba), limit=10_000)
        ustaw_szczegoly(request, liczba=len(wpisy), format="csv")
        bufor = io.StringIO()
        zapis = csv.writer(bufor, delimiter=";")
        naglowek = ["czas", "uzytkownik", "rola", "akcja", "kod_akcji", "metoda", "trasa", "obiekt",
                    "osoba_oceniana", "wynik", "status", "czas_ms", "request_id", "szczegoly"]
        zapis.writerow(naglowek)
        for w in wpisy:
            zapis.writerow([_do_csv(x) for x in (
                w["czas"], w["aktor_login"], w["aktor_rola"], w["etykieta"], w["akcja"], w["metoda"], w["trasa"],
                w["obiekt"], w["oceniany_osoba"], w["wynik"], w["status"], w["czas_ms"], w["request_id"],
                w["szczegoly"] or None,
            )])
        return Response("﻿" + bufor.getvalue(), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": 'attachment; filename="rejestr-operacji.csv"',
        })

    return r
