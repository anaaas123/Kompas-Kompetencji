"""API asystenta rozmowy (#35, krok 6): plan rozmowy oceniającej jako sugestia."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik

from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import zbuduj_stan
from .ocena_api import _wczytaj_dane
from .procesy import wczytaj_proces
from .qnt import MockQnt
from .rozmowa import KonfiguracjaRozmowy, KontekstRozmowy, PlanRozmowy, przygotuj


def router(
    auth: Autoryzacja,
    qnt: MockQnt,
    stan2: StanKroku2,
    konf: KonfiguracjaRozmowy,
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["krok 6: asystent rozmowy"])

    @r.post("/procesy/{proces_id}/rozmowa")
    def plan_rozmowy(
        proces_id: int,
        request: Request,
        kontekst: KontekstRozmowy | None = None,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> PlanRozmowy:
        """Plan rozmowy oceniającej: zakres z przepisu, pytania z powiązaniem i uzasadnieniem,
        argumenty, szkic informacji zwrotnej i kwestie do omówienia. Wszystko jest sugestią
        do edycji; nic nie jest zapisywane i oceny się nie zmieniają. Tylko przełożony
        (``ocena.prowadz``): plan zawiera przykłady i uwagi o pracowniku."""
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
        # Ta sama wersja metodyki co w krokach 3–5 (przypięta do procesu, #39).
        metodyki: RejestrMetodyk = request.app.state.metodyki
        konf_oceny = metodyki.konfiguracja(metodyki.dla_procesu(proces.id))
        stan = zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model, konf_oceny
        )
        return przygotuj(stan, proces.krok1.osp, kontekst or KontekstRozmowy(), konf, stan2.model)

    return r
