"""Wnioski rozwojowe procesu (#36, krok 8): propozycje z kroków 3–5 obok pola arkusza.

Asystent tylko proponuje. Treść wniosków przełożony wpisuje sam w polu `wnioski_iprz`
arkusza okresowego (krok 7, #33), skąd trafia do PDF. Ten endpoint niczego nie zapisuje.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from pydantic import BaseModel

from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import zbuduj_stan
from .ocena_api import _wczytaj_dane
from .pierwsza_ocena_api import CzytajPierwsza
from .procesy import wczytaj_proces
from .qnt import MockQnt
from .rozwoj import DaneRozwoju, OcenaWskaznika, WynikRozwoju, zaproponuj
from .wynik_okresowy_api import SerwisWynikuOkresowego

POLE_ARKUSZA = "wnioski_iprz"


class WnioskiProcesu(BaseModel):
    proces_id: int
    sciezka: Literal["pierwsza", "okresowa"]
    wynik_oceny: Literal["pozytywna", "negatywna"] | None
    """None, gdy wynik jeszcze nie jest dostępny."""
    propozycje: WynikRozwoju
    pole_arkusza: str | None
    """Pole formularza, do którego przełożony wpisuje wnioski (None, gdy arkusz nie dotyczy)."""
    gdzie_wpisac: str
    wnioski_w_arkuszu: str | None
    """Aktualna treść pola w arkuszu – wpisana przez przełożonego, nie przez asystenta."""


def router(
    auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2,
    serwis: SerwisWynikuOkresowego, czytaj_pierwsza: CzytajPierwsza,
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["krok 8: wnioski rozwojowe"])

    @r.get("/procesy/{proces_id}/rozwoj")
    def wnioski(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("rozwoj.propozycje")
    ) -> WnioskiProcesu:
        """Propozycje obszarów i form rozwoju ze wskaźników ocenionych w krokach 3–5, warunek
        wyniku pozytywnego w pierwszej ocenie i aktualna treść pola wniosków w arkuszu."""
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        p = qnt.pracownik(proces.osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), "ocena.prowadz")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")

        oceny, decyzje = _wczytaj_dane(baza, proces.id)
        metodyki: RejestrMetodyk = request.app.state.metodyki
        konf_oceny = metodyki.konfiguracja(metodyki.dla_procesu(proces.id))
        stan = zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model, konf_oceny
        )

        wynik_oceny, pierwsza = None, None
        if proces.sciezka == "okresowa":
            krok2_json, decyzje_json, zapis = baza.execute(
                "SELECT krok2, decyzje, wynik_okresowy FROM procesy WHERE id = ?", (proces.id,)
            ).fetchone()
            try:
                wynik_oceny = serwis.obecny_widok(
                    serwis.migawka(proces, p, krok2_json, decyzje_json, zapis)
                ).obliczenie.wynik
            except HTTPException as e:
                if e.status_code != 409:  # 409 = krok 5 niekompletny: wyniku jeszcze nie ma
                    raise
        else:
            pierwsza = czytaj_pierwsza(proces_id, request, uz)
            if pierwsza.obliczenie:
                wynik_oceny = pierwsza.obliczenie.wynik

        dane = DaneRozwoju(
            sciezka=proces.sciezka,
            wynik_pozytywny=None if wynik_oceny is None else wynik_oceny == "pozytywna",
            wskazniki=[OcenaWskaznika.model_validate(w.model_dump()) for w in stan.dla_rozwoju],
        )

        pole, gdzie, tresc = None, "Wnioski rozwojowe są dostępne po pozytywnej pierwszej ocenie.", None
        if proces.sciezka == "okresowa":
            pole = POLE_ARKUSZA
            gdzie = "Krok 7: arkusz okresowy, pole „Wnioski dotyczące indywidualnego programu rozwoju zawodowego”."
            (zapis_arkusza,) = baza.execute(
                "SELECT arkusz_okresowy FROM procesy WHERE id = ?", (proces.id,)
            ).fetchone()
            if zapis_arkusza:
                tresc = json.loads(zapis_arkusza).get("pola", {}).get(POLE_ARKUSZA)
        elif pierwsza and pierwsza.wnioski_dostepne:
            pole = "wnioski_rozwojowe"
            gdzie = "Arkusz pierwszej oceny, pole „Wnioski dotyczące rozwoju zawodowego ocenianego”."
            tresc = pierwsza.dane.wnioski_rozwojowe

        return WnioskiProcesu(
            proces_id=proces.id,
            sciezka=proces.sciezka,
            wynik_oceny=wynik_oceny,
            propozycje=zaproponuj(dane, request.app.state.rozwoj),
            pole_arkusza=pole,
            gdzie_wpisac=gdzie,
            wnioski_w_arkuszu=tresc,
        )

    return r
