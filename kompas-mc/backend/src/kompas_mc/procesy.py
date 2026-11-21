"""API kroku 1 i procesu oceny (#29): analiza OSP, wybór ścieżki i arkusza, start procesu.

Decyzję o ścieżce podejmuje przełożony. System proponuje ścieżkę z przesłankami; gdy
przełożony wybiera inną albo propozycji nie ma, musi podać uzasadnienie.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from pydantic import BaseModel, Field

from .krok1 import AnalizaKroku1, KonfiguracjaKroku1, Sciezka, Uwaga, analizuj
from .krok2 import WyborKroku2
from .osp import KatalogOsp
from .qnt import MockQnt, Pracownik

WERSJA_REGUL = "krok1@1"


class NowyProces(BaseModel):
    osoba_id: str
    sciezka: Sciezka
    uzasadnienie: str | None = Field(default=None, max_length=4000)


STREFA_URZEDU = ZoneInfo("Europe/Warsaw")
"""Daty czynności (ustalenie kryteriów, rozpoczęcie) liczy się w czasie urzędowym, nie w UTC zapisu (#72)."""


def dzien_urzedowy(chwila: datetime) -> date:
    """Dzień kalendarzowy w Polsce dla chwili zapisanej w UTC (zapis po północy to już następny dzień)."""
    return (chwila if chwila.tzinfo else chwila.replace(tzinfo=UTC)).astimezone(STREFA_URZEDU).date()


class ProcesOceny(BaseModel):
    id: int
    osoba_id: str
    sciezka: Sciezka
    arkusz: Literal["B", "C", "PIERWSZA"]
    """„PIERWSZA” to arkusz pierwszej oceny (zał. 2 rozp. 2015)."""
    krok: int
    status: Literal["W_TOKU", "ZAKONCZONY"]
    rozpoczal: str
    rozpoczeto: datetime
    zgodna_z_propozycja: bool
    uzasadnienie: str | None
    krok1: AnalizaKroku1
    krok2: WyborKroku2 | None = None
    """Kryteria i wskaźniki zatwierdzone przez przełożonego (#30); None przed zapisem."""


_KOLUMNY = (
    "id, osoba_id, sciezka, arkusz, krok, status, rozpoczal, rozpoczeto,"
    " zgodna_z_propozycja, uzasadnienie, krok1, krok2"
)


def wczytaj_proces(baza, proces_id: int) -> ProcesOceny | None:
    w = baza.execute(f"SELECT {_KOLUMNY} FROM procesy WHERE id = ?", (proces_id,)).fetchone()
    return _z_wiersza(w) if w else None


def _z_wiersza(w: tuple) -> ProcesOceny:
    i, o, s, a, k, st, roz, czas, zg, uz, k1, k2 = w
    return ProcesOceny(
        id=i,
        osoba_id=o,
        sciezka=s,
        arkusz=a,
        krok=k,
        status=st,
        rozpoczal=roz,
        rozpoczeto=datetime.fromisoformat(czas),
        zgodna_z_propozycja=bool(zg),
        uzasadnienie=uz,
        krok1=AnalizaKroku1.model_validate_json(k1),
        krok2=WyborKroku2.model_validate_json(k2) if k2 else None,
    )


def router(
    auth: Autoryzacja, qnt: MockQnt, katalog: KatalogOsp, konf: KonfiguracjaKroku1
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["krok 1 i proces oceny"])

    def dostepny(osoba_id: str, uz: Uzytkownik, akcja: str) -> Pracownik:
        p = qnt.pracownik(osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), akcja)
        return p

    @r.get("/pracownicy/{osoba_id}/krok1")
    def krok1(osoba_id: str, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> AnalizaKroku1:
        """Analiza OSP, propozycja ścieżki z przesłankami i arkusz B/C (§ 3 rozp. 2016).

        Nic nie zapisuje, więc wystarcza podgląd (``ocena.czytaj``): przełożony widzi
        podwładnych, HR wszystkich, oceniany siebie. Przy niejednoznacznych danych kadrowych ``sciezka.proponowana``
        jest ``null``, a ``sciezka.braki`` mówi, czego brakuje.
        """
        return analizuj(dostepny(osoba_id, uz, "ocena.czytaj"), katalog, konf)

    @r.post("/procesy", status_code=201)
    def rozpocznij(
        body: NowyProces, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz")
    ) -> ProcesOceny:
        """Przełożony rozpoczyna proces oceny na wybranej ścieżce.

        422: inna ścieżka niż proponowana (albo brak propozycji) bez uzasadnienia; ocena
        okresowa bez ustalonego arkusza B/C. 409: osoba ma już proces w toku.
        """
        p = dostepny(body.osoba_id, uz, "ocena.prowadz")
        analiza = analizuj(p, katalog, konf)
        zgodna = analiza.sciezka.proponowana == body.sciezka
        uzasadnienie = (body.uzasadnienie or "").strip() or None
        if not zgodna and uzasadnienie is None:
            raise HTTPException(
                422,
                {
                    "komunikat": "Wybrana ścieżka różni się od propozycji systemu albo propozycji "
                    "nie ma; podaj uzasadnienie.",
                    "proponowana": analiza.sciezka.proponowana,
                    "braki": [b.model_dump() for b in analiza.sciezka.braki],
                },
            )
        if body.sciezka == "okresowa":
            if analiza.arkusz_okresowy.arkusz is None:
                raise HTTPException(
                    422,
                    {
                        "komunikat": "Nie da się ustalić arkusza B/C; uzupełnij dane.",
                        "braki": [b.model_dump() for b in analiza.arkusz_okresowy.braki],
                    },
                )
            arkusz = analiza.arkusz_okresowy.arkusz
        else:
            arkusz = "PIERWSZA"
            if not any(u.id == "rozbieznosc.osp-pierwsza-ocena" for u in analiza.uwagi):
                u = konf.uwagi["osp-pierwsza-ocena"]
                analiza.uwagi.append(Uwaga(id=u.id, komunikat=u.komunikat, adnotacje=u.adnotacje))

        baza = request.app.state.baza
        czas = datetime.now(UTC)
        with baza:
            if baza.execute(
                "SELECT 1 FROM procesy WHERE osoba_id = ? AND status = 'W_TOKU'", (p.osoba_id,)
            ).fetchone():
                raise HTTPException(409, "Ta osoba ma już proces oceny w toku")
            kursor = baza.execute(
                "INSERT INTO procesy (osoba_id, sciezka, arkusz, krok, status, rozpoczal,"
                " rozpoczeto, zgodna_z_propozycja, uzasadnienie, krok1)"
                " VALUES (?, ?, ?, 1, 'W_TOKU', ?, ?, ?, ?, ?)",
                (
                    p.osoba_id,
                    body.sciezka,
                    arkusz,
                    uz.login,
                    czas.isoformat(),
                    int(zgodna),
                    uzasadnienie,
                    analiza.model_dump_json(by_alias=True),
                ),
            )
        proces = _wczytaj(request, kursor.lastrowid)
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(
            uz.login,
            "proces",
            str(proces.id),
            None,
            json.loads(proces.model_dump_json(exclude={"krok1"})),
            WERSJA_REGUL,
        )
        return proces

    def _wczytaj(request: Request, proces_id: int) -> ProcesOceny | None:
        return wczytaj_proces(request.app.state.baza, proces_id)

    @r.get("/procesy")
    def lista(request: Request, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> list[ProcesOceny]:
        """Procesy osób, które użytkownik widzi: przełożony podwładnych, HR wszystkich,
        oceniany siebie."""
        wiersze = request.app.state.baza.execute(f"SELECT {_KOLUMNY} FROM procesy ORDER BY id")
        wynik = []
        for w in wiersze.fetchall():
            p = qnt.pracownik(w[1])
            if p and auth.moze(uz, "pracownik", p.model_dump(), "ocena.czytaj"):
                wynik.append(_z_wiersza(w))
        return wynik

    @r.get("/procesy/{proces_id}")
    def jeden(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")
    ) -> ProcesOceny:
        proces = _wczytaj(request, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        dostepny(proces.osoba_id, uz, "ocena.czytaj")
        return proces

    return r
