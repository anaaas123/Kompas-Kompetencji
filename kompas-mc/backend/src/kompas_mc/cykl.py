"""Etap cyklu oceny i następna czynność każdej osoby (#23).

Ocena okresowa ma dwa momenty oddalone o niemal 2 lata: na początku okresu rozmowa o obowiązkach,
kryteriach i oczekiwaniach oraz część I arkusza (rozp. 2016 § 5–7), na końcu rozmowa oceniająca
i ocena na piśmie (§ 10–11). Pierwsza ocena: rozmowa wstępna na początku, ocena przed końcem umowy.
Terminy liczą istniejące reguły (``oblicz_terminy``, ``oblicz_terminy_pierwszej``); ten moduł tylko
wybiera etap i czynność, więc frontend niczego nie liczy.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from kompas_core.kalendarz import WynikTerminu
from pydantic import BaseModel, Field

from .hr import Termin
from .krok1 import Sciezka
from .pierwsza_ocena import ZapisDanychPierwszej, uzupelnij_z_kadr
from .procesy import _KOLUMNY, ProcesOceny, _z_wiersza
from .qnt import MockQnt, Pracownik
from .terminy_okresowej import DaneTerminow, KonfiguracjaTerminow, oblicz_terminy
from .terminy_pierwszej import KonfiguracjaTerminowPierwszej, oblicz_terminy_pierwszej

Etap = Literal["kryteria", "okres", "ocena", "brak_danych"]


class EtapOsoby(BaseModel):
    osoba_id: str
    sciezka: Sciezka | None
    etap: Etap
    czynnosc: str
    """Następna czynność po ludzku, np. „Ustal kryteria”, „Okres oceny”, „Rozmowa oceniająca”."""
    termin: Termin | None
    dni_do_terminu: int | None
    po_terminie: bool
    proces_id: int | None = None
    kryteria_ustalone: date | None = None
    """Dzień zapisu kryteriów w aplikacji (krok 2); ``None``, gdy ustalono je poza nią albo jeszcze nie."""
    braki: list[str] = Field(default_factory=list)


def _termin(nazwa: str, w: WynikTerminu) -> Termin:
    return Termin(nazwa=nazwa, data=w.data, adnotacje=[k.regula.zrodlo for k in w.slad])


def _wynik(
    p: Pracownik, sciezka: Sciezka | None, etap: Etap, czynnosc: str, termin: Termin | None,
    dzis: date, proces: ProcesOceny | None, braki: tuple[str, ...] | list[str] = (),
) -> EtapOsoby:
    dni = (termin.data - dzis).days if termin else None
    return EtapOsoby(
        osoba_id=p.osoba_id, sciezka=sciezka, etap=etap, czynnosc=czynnosc, termin=termin,
        dni_do_terminu=dni, po_terminie=dni is not None and dni < 0,
        proces_id=proces.id if proces else None,
        kryteria_ustalone=proces.krok2.zapisano.date() if proces and proces.krok2 else None,
        braki=list(braki),
    )


def etap_okresowej(
    p: Pracownik, proces: ProcesOceny | None, konf: KonfiguracjaTerminow, dzis: date, od_kiedy: date,
) -> EtapOsoby:
    """``od_kiedy``: od tego dnia aplikacja prowadzi oceny (stan danych kadrowych). Wcześniejszy termin
    kryteriów dotrzymano poza aplikacją (ta sama zasada co w ``hr.terminy_z_regul``); późniejszy pilnujemy."""
    ustalone = proces.krok2.zapisano.date() if proces and proces.krok2 else None
    t = oblicz_terminy(p, DaneTerminow(data_ustalenia_kryteriow=ustalone), konf)
    ocena = t.termin_sporzadzenia_oceny or t.termin_bazowy
    termin_oceny = _termin("sporządzenie oceny na piśmie", ocena) if ocena else None

    if proces and proces.krok >= 6:
        return _wynik(p, "okresowa", "ocena", "Ocena na piśmie", termin_oceny, dzis, proces, t.braki)
    if proces and proces.krok >= 3:
        return _wynik(p, "okresowa", "ocena", "Rozmowa oceniająca", termin_oceny, dzis, proces, t.braki)

    kryteria = t.termin_kryteriow
    poczatek = min(od_kiedy, proces.rozpoczeto.date()) if proces else od_kiedy
    if ustalone is None and kryteria is not None and kryteria.data >= poczatek:
        termin = _termin("rozmowa i kryteria na początku okresu (§ 7)", kryteria)
        return _wynik(p, "okresowa", "kryteria", "Ustal kryteria", termin, dzis, proces, t.braki)
    if termin_oceny is None:
        return _wynik(p, "okresowa", "brak_danych", "Uzupełnij dane kadrowe", None, dzis, proces, t.braki)
    if (termin_oceny.data - dzis).days <= konf.okno_oceny_koncowej.liczba:
        return _wynik(p, "okresowa", "ocena", "Rozmowa oceniająca", termin_oceny, dzis, proces, t.braki)
    return _wynik(p, "okresowa", "okres", "Okres oceny", termin_oceny, dzis, proces, t.braki)


def etap_pierwszej(
    p: Pracownik, proces: ProcesOceny | None, zapis: str | None,
    konf: KonfiguracjaTerminowPierwszej, dzis: date, okno_oceny: int,
) -> EtapOsoby:
    dane = uzupelnij_z_kadr(ZapisDanychPierwszej.wczytaj(zapis).dane, p)
    try:
        t = oblicz_terminy_pierwszej(p, dane, konf)
    except ValueError as e:
        return _wynik(p, "pierwsza", "brak_danych", "Uzupełnij dane kadrowe", None, dzis, proces, [str(e)])

    if t.data_rozmowy_wstepnej is None and t.termin_rozmowy_wstepnej is not None:
        termin = _termin("rozmowa wstępna (§ 3)", t.termin_rozmowy_wstepnej)
        return _wynik(p, "pierwsza", "kryteria", "Rozmowa wstępna", termin, dzis, proces, t.braki)
    if t.pierwsza_ocena_do is None:
        return _wynik(p, "pierwsza", "brak_danych", "Uzupełnij dane kadrowe", None, dzis, proces, t.braki)
    termin = _termin("dokonanie pierwszej oceny", t.pierwsza_ocena_do)
    if (proces and proces.krok >= 3) or (termin.data - dzis).days <= okno_oceny:
        return _wynik(p, "pierwsza", "ocena", "Pierwsza ocena", termin, dzis, proces, t.braki)
    return _wynik(p, "pierwsza", "okres", "Okres przed pierwszą oceną", termin, dzis, proces, t.braki)


def etap_osoby(
    p: Pracownik, sciezka: Sciezka | None, proces: ProcesOceny | None, zapis_pierwszej: str | None,
    konf_okresowej: KonfiguracjaTerminow, konf_pierwszej: KonfiguracjaTerminowPierwszej, dzis: date,
    od_kiedy: date,
) -> EtapOsoby:
    if sciezka == "okresowa":
        return etap_okresowej(p, proces, konf_okresowej, dzis, od_kiedy)
    if sciezka == "pierwsza":
        return etap_pierwszej(p, proces, zapis_pierwszej, konf_pierwszej, dzis, konf_okresowej.okno_oceny_koncowej.liczba)
    return _wynik(p, None, "brak_danych", "Ustal ścieżkę oceny", None, dzis, proces,
                  ["Dane kadrowe nie rozstrzygają ścieżki; zobacz analizę w kroku 1."])


def router(
    auth: Autoryzacja, qnt: MockQnt, konf_okresowej: KonfiguracjaTerminow,
    konf_pierwszej: KonfiguracjaTerminowPierwszej, sciezka_osoby: Callable[[Pracownik], Sciezka | None],
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["cykl oceny"])

    @r.get("/cykl")
    def cykl(request: Request, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> list[EtapOsoby]:
        """Etap, następna czynność i termin każdej osoby, którą użytkownik widzi: przełożony
        podwładnych, HR wszystkich, oceniany siebie. Bez treści ocen."""
        f = getattr(request.app.state, "dzis", None)
        dzis = f() if f else date.today()
        baza: sqlite3.Connection = request.app.state.baza
        w_toku = {}
        for w in baza.execute(f"SELECT {_KOLUMNY}, pierwsza_ocena FROM procesy WHERE status = 'W_TOKU'"):
            w_toku[w[1]] = (_z_wiersza(w[:-1]), w[-1])
        rekordy = [p.model_dump() for p in qnt.pracownicy]
        wynik = []
        for rek in auth.filtruj(uz, "pracownik", rekordy, "ocena.czytaj"):
            p = qnt.pracownik(rek["osoba_id"])
            proces, zapis = w_toku.get(p.osoba_id, (None, None))
            sciezka = proces.sciezka if proces else sciezka_osoby(p)
            wynik.append(etap_osoby(p, sciezka, proces, zapis, konf_okresowej, konf_pierwszej, dzis, qnt.dzis_demo))
        return wynik

    return r
