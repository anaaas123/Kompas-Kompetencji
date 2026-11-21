"""Mapa kompetencji zespołu (#33): punkty ocen cząstkowych osób, które użytkownik może oceniać.

Źródło dla każdej osoby: bieżąca ocena w aplikacji, gdy przełożony zapisał już decyzje kryteriów,
w przeciwnym razie ostatnia ocena okresowa z kartoteki (QNT). Treść ocen: uprawnienie ``ocena.tresc``
z regułą dostępu do pracownika (przełożony – podwładni, oceniany – siebie); HR go nie ma, więc 403
(zadanie MC: HR monitoruje procesy i terminy, minimalizacja danych). Pracownikowi bieżących decyzji
nie pokazujemy przed przekazaniem samooceny (jak w ``GET …/ocena``).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from pydantic import BaseModel

from .krok2_api import StanKroku2
from .ocena import KonfiguracjaOceny, aktualne_decyzje
from .ocena_api import _wczytaj_dane
from .procesy import _KOLUMNY, _z_wiersza
from .qnt import MockQnt
from .samoocena import rozbieznosc, wczytaj as wczytaj_samoocene


class KryteriumMapy(BaseModel):
    kompetencja_id: str
    nazwa: str


class OsobaMapy(BaseModel):
    osoba_id: str
    zrodlo: Literal["biezaca_ocena", "ostatnia_ocena"]
    data: date | None
    """Data ostatniej oceny z kartoteki albo ostatniej decyzji w aplikacji."""
    punkty: dict[str, int]
    rozbieznosci: int | None = None
    """Wskaźniki z różnicą samoocena–ocena ≥ progu; tylko dla przełożonego i po przekazaniu samooceny."""


class MapaKompetencji(BaseModel):
    skala: list[int]
    poziom_oczekiwan: int
    kryteria: list[KryteriumMapy]
    osoby: list[OsobaMapy]


def router(auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2, konf: KonfiguracjaOceny) -> APIRouter:
    """Skala i poziom oczekiwań z ``konfiguracja/ocena.yaml`` (ocena okresowa, § 11 rozp. 2016)."""
    r = APIRouter(prefix="/api", tags=["zespół"])

    @r.get("/zespol/kompetencje")
    def kompetencje(request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc")) -> MapaKompetencji:
        baza = request.app.state.baza
        prog = request.app.state.samoocena.prog_rozbieznosci
        procesy = {}
        for w in baza.execute(f"SELECT {_KOLUMNY} FROM procesy WHERE status = 'W_TOKU' ORDER BY id").fetchall():
            p = _z_wiersza(w)
            procesy[p.osoba_id] = p

        osoby: list[OsobaMapy] = []
        for p in qnt.pracownicy:
            rekord = p.model_dump()
            if not auth.moze(uz, "pracownik", rekord, "ocena.tresc"):
                continue
            wynik: OsobaMapy | None = None
            proces = procesy.get(p.osoba_id)
            pracownik_sam = auth.moze(uz, "pracownik", rekord, "samoocena.zapisz")
            if proces is not None and proces.krok2 is not None:
                status, _, samo = wczytaj_samoocene(baza, proces.id)
                if not (pracownik_sam and status != "przekazana"):
                    oceny, decyzje = _wczytaj_dane(baza, proces.id)
                    biezace = aktualne_decyzje(proces.krok2, decyzje)
                    if biezace:
                        rozb = None
                        if status == "przekazana" and auth.moze(uz, "pracownik", rekord, "samoocena.czytaj"):
                            rozb = sum(1 for wid, s in samo.items() if rozbieznosc(s, oceny.get(wid), prog))
                        wynik = OsobaMapy(
                            osoba_id=p.osoba_id,
                            zrodlo="biezaca_ocena",
                            data=max(d.zapisano for d in biezace.values()).date(),
                            punkty={k: d.punkty for k, d in biezace.items()},
                            rozbieznosci=rozb,
                        )
            if wynik is None and p.ostatnia_ocena_okresowa and p.ostatnia_ocena_okresowa.oceny_czastkowe:
                o = p.ostatnia_ocena_okresowa
                wynik = OsobaMapy(osoba_id=p.osoba_id, zrodlo="ostatnia_ocena", data=o.data, punkty=dict(o.oceny_czastkowe))
            if wynik is not None:
                osoby.append(wynik)

        # Kolumny: kryteria występujące w danych, w kolejności modelu kompetencji.
        wystepuja = {k for o in osoby for k in o.punkty}
        kryteria = [
            KryteriumMapy(kompetencja_id=k.id, nazwa=k.nazwa) for k in stan2.model.kompetencje if k.id in wystepuja
        ]
        znane = {k.kompetencja_id for k in kryteria}
        kryteria += [KryteriumMapy(kompetencja_id=k, nazwa=k) for k in sorted(wystepuja - znane)]
        return MapaKompetencji(
            skala=konf.skale["okresowa"].punkty, poziom_oczekiwan=konf.poziom_oczekiwan, kryteria=kryteria, osoby=osoby
        )

    return r
