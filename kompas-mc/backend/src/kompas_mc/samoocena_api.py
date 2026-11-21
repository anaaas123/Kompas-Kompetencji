"""API samooceny (#8): szkic i przekazanie przez ocenianego, odczyt przełożonego po przekazaniu.

Uprawnienia (``role.yaml``): ``samoocena.zapisz`` ma oceniany (reguła dostępu: tylko własny proces),
``samoocena.czytaj`` przełożony (podwładni, treść dopiero po przekazaniu). HR nie ma żadnego z nich,
więc dostaje 403. Konfiguracja: ``app.state.samoocena`` (``konfiguracja/samoocena.yaml``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik

from .krok2_api import StanKroku2
from .procesy import ProcesOceny, wczytaj_proces
from .qnt import MockQnt
from .samoocena import BladSamooceny, Samoocena, ZapisSamooceny, przekaz, wczytaj, zapisz_szkic, zbuduj


def router(auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["samoocena"])

    def proces_z_osoba(request: Request, proces_id: int) -> tuple[ProcesOceny, dict]:
        proces = wczytaj_proces(request.app.state.baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        p = qnt.pracownik(proces.osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        if proces.krok2 is None:
            raise HTTPException(409, "Samoocena jest dostępna po zapisaniu kryteriów i wskaźników (krok 2).")
        return proces, p.model_dump()

    def do_zapisu(request: Request, proces_id: int, uz: Uzytkownik) -> ProcesOceny:
        proces, osoba = proces_z_osoba(request, proces_id)
        auth.sprawdz(uz, "pracownik", osoba, "samoocena.zapisz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        if wczytaj(request.app.state.baza, proces.id)[0] == "przekazana":
            raise HTTPException(409, "Samoocena jest już przekazana i nie można jej zmienić.")
        return proces

    def widok(request: Request, proces: ProcesOceny, tresc_widoczna: bool) -> Samoocena:
        status, przekazano, pozycje = wczytaj(request.app.state.baza, proces.id)
        return zbuduj(
            proces.id, proces.krok2, stan2.model, status, przekazano, pozycje, request.app.state.samoocena,
            tresc_widoczna,
        )

    def zapisz_w_dzienniku(request: Request, uz: Uzytkownik, proces_id: int, przed: dict, po: dict) -> None:
        # W dzienniku tylko status i liczba odpowiedzi: treść samooceny nie trafia do historii widocznej dla innych.
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "samoocena", str(proces_id), przed, po, request.app.state.samoocena.regula.id)

    def stan_do_dziennika(request: Request, proces_id: int) -> dict:
        status, _, pozycje = wczytaj(request.app.state.baza, proces_id)
        return {"status": status, "odpowiedzi": len(pozycje)}

    @r.get("/procesy/{proces_id}/samoocena")
    def odczyt(proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> Samoocena:
        """Oceniany: własna samoocena (szkic albo przekazana). Przełożony: status zawsze, treść po
        przekazaniu. HR: 403 (bez dostępu do treści samooceny)."""
        proces, osoba = proces_z_osoba(request, proces_id)
        if auth.moze(uz, "pracownik", osoba, "samoocena.zapisz"):
            return widok(request, proces, tresc_widoczna=True)
        if auth.moze(uz, "pracownik", osoba, "samoocena.czytaj"):
            przekazana = wczytaj(request.app.state.baza, proces.id)[0] == "przekazana"
            return widok(request, proces, tresc_widoczna=przekazana)
        raise HTTPException(403, "Brak dostępu do samooceny")

    @r.put("/procesy/{proces_id}/samoocena")
    def szkic(
        proces_id: int, body: ZapisSamooceny, request: Request, uz: Uzytkownik = auth.wymagaj("samoocena.zapisz")
    ) -> Samoocena:
        """Zapis szkicu: poziom 1/3/5/7/9 albo „brak zdania” i opcjonalny przykład S–D–R przy wskaźnikach
        z kroku 2. Scala z zapisanym; ``null`` usuwa odpowiedź. Po przekazaniu: 409."""
        proces = do_zapisu(request, proces_id, uz)
        przed = stan_do_dziennika(request, proces.id)
        try:
            zapisz_szkic(request.app.state.baza, proces.id, body, proces.krok2, datetime.now(UTC))
        except BladSamooceny as e:
            raise HTTPException(422, {"komunikat": "Niepoprawna samoocena.", "bledy": e.args[0]})
        zapisz_w_dzienniku(request, uz, proces.id, przed, stan_do_dziennika(request, proces.id))
        return widok(request, proces, tresc_widoczna=True)

    @r.post("/procesy/{proces_id}/samoocena/przekaz")
    def przekazanie(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("samoocena.zapisz")
    ) -> Samoocena:
        """Przekazanie przełożonemu. Wymaga odpowiedzi przy każdym wskaźniku (poziom albo „brak zdania”);
        potem samoocena jest tylko do odczytu."""
        proces = do_zapisu(request, proces_id, uz)
        przed = stan_do_dziennika(request, proces.id)
        try:
            przekaz(request.app.state.baza, proces.id, proces.krok2, datetime.now(UTC))
        except BladSamooceny as e:
            raise HTTPException(422, {"komunikat": "Samoocena jest niepełna.", "bledy": e.args[0]})
        zapisz_w_dzienniku(request, uz, proces.id, przed, stan_do_dziennika(request, proces.id))
        return widok(request, proces, tresc_widoczna=True)

    return r
