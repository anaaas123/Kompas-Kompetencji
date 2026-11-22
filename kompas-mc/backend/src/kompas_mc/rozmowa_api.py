"""API asystenta rozmowy (#35, krok 6): plan rozmowy oceniającej jako sugestia."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from kompas_core.llm import BrakOdpowiedzi, Zapytanie, wywolaj
from pydantic import BaseModel, Field

from .asystent import OdpowiedzAsystenta, proponuje_ocene
from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import zbuduj_stan
from .ocena_api import _wczytaj_dane
from .procesy import wczytaj_proces
from .pseudonimizacja import Pseudonimizator
from .qnt import MockQnt
from .rozmowa import KonfiguracjaRozmowy, KontekstRozmowy, PlanRozmowy, przygotuj


class PytanieCzatu(BaseModel):
    pytanie: str = Field(min_length=1, max_length=1000)


class OdpowiedzCzatu(OdpowiedzAsystenta):
    oznaczenie_sugestii: str


# Podpowiedź przy wskaźniku (Karol 22.11, 02:04: „to ma być podpowiedź taka inteligentna AI”). Model dostaje
# fragmenty modelu kompetencji dla wskaźnika (opis i 5 poziomów) oraz pseudonimizowane zadania z OSP i przykład;
# odpowiedź bez dosłownego cytatu z tych fragmentów odrzuca walidacja w core (wtedy zostaje pytanie z szablonu).
POLECENIE_PODPOWIEDZI = """Zaproponuj jedno krótkie pytanie (najwyżej dwa zdania), które przełożony zada
Ocenianemu w rozmowie oceniającej o tym wskaźniku. Pytanie ma przywołać konkretną sytuację z okresu oceny
przy zadaniach z opisu stanowiska i pomóc porównać zachowanie ze standardem (poziom „na poziomie oczekiwań”).
Zwracaj się do Ocenianego w drugiej osobie, bez imion. W polu "tresc" zwróć samo pytanie, a w "cytaty"
dosłowny fragment opisu wskaźnika albo poziomu, na którym je opierasz."""


class ZapytaniePodpowiedzi(BaseModel):
    wskaznik_id: str = Field(max_length=200)


class PodpowiedzRozmowy(BaseModel):
    pytanie: str | None
    """Pytanie z modelu; ``None``, gdy model nie odpowiedział poprawnie (ekran zostaje przy szablonie)."""
    dostawca: str | None = None
    tryb: str | None = None


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

    @r.post("/procesy/{proces_id}/rozmowa/czat")
    def czat_rozmowy(
        proces_id: int,
        body: PytanieCzatu,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> OdpowiedzCzatu:
        """RAG dla przełożonego z pseudonimizowanym kontekstem bieżącej oceny."""
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), "ocena.prowadz")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")

        oceny, decyzje = _wczytaj_dane(baza, proces.id)
        metodyki: RejestrMetodyk = request.app.state.metodyki
        konf_oceny = metodyki.konfiguracja(metodyki.dla_procesu(proces.id))
        stan = zbuduj_stan(
            proces.id,
            proces.sciezka,
            proces.arkusz,
            proces.krok2,
            oceny,
            decyzje,
            stan2.model,
            konf_oceny,
        )
        surowy_kontekst = {
            "osoba_id": proces.osoba_id,
            "przelozony_id": pracownik.przelozony_id,
            "sciezka": proces.sciezka,
            "wybrane_wskazniki_poziomy_i_decyzje": stan.model_dump(mode="json"),
        }
        kontekst = Pseudonimizator(qnt).json(surowy_kontekst, proces.osoba_id)
        odpowiedz = request.app.state.asystent.odpowiedz(
            body.pytanie, proces.sciezka, kontekst=kontekst
        )
        if odpowiedz.faq_id is None and proponuje_ocene(odpowiedz.tresc):
            odpowiedz = odpowiedz.model_copy(update={
                "tresc": None,
                "uwagi": [*odpowiedz.uwagi, "Asystent nie proponuje punktów ani poziomu; zostały same cytaty ze źródeł."],
            })
        return OdpowiedzCzatu(
            **odpowiedz.model_dump(), oznaczenie_sugestii=konf.oznaczenie_sugestii
        )

    @r.post("/procesy/{proces_id}/rozmowa/podpowiedz")
    def podpowiedz(
        proces_id: int,
        body: ZapytaniePodpowiedzi,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> PodpowiedzRozmowy:
        """Pytanie do rozmowy przy wskaźniku z modelu (łańcuch dostawców asystenta, Scaleway w UE).
        Kontekst bez imion i nazwisk; podpowiedź, nie decyzja. 404 dla wskaźnika spoza kroku 2."""
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), "ocena.prowadz")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")
        wybrane = {w.id for k in proces.krok2.kryteria for w in k.wskazniki}
        llm = request.app.state.cele_llm
        fragmenty = llm.fragmenty_wskaznikow.get(body.wskaznik_id) if body.wskaznik_id in wybrane else None
        if not fragmenty:
            raise HTTPException(404, "Ten wskaźnik nie należy do kryteriów tej oceny.")
        oceny, _ = _wczytaj_dane(baza, proces.id)
        o = oceny.get(body.wskaznik_id)
        osp = proces.krok1.osp
        kontekst = Pseudonimizator(qnt).json(
            {
                "zadania_osp": [z.tekst for z in (osp.zadania_dominujace if osp else [])],
                "przyklad": o.uwagi if o and o.uwagi else None,
            },
            proces.osoba_id,
        )
        zapytanie = Zapytanie(
            operacja="podpowiedz_rozmowy",
            prompt_wersja="1",
            pytanie=f"{POLECENIE_PODPOWIEDZI}\n\nKONTEKST (dane pseudonimizowane):\n{kontekst}",
            fragmenty=fragmenty,
        )
        if not llm.dostawcy:
            return PodpowiedzRozmowy(pytanie=None)
        try:
            wynik = wywolaj(zapytanie, llm.dostawcy, llm.dziennik)
        except BrakOdpowiedzi:
            return PodpowiedzRozmowy(pytanie=None)
        pytanie = (wynik.odpowiedz.tresc or "").strip()
        # Ma to być jedno pytanie do rozmowy, nie ocena ani wykład: inaczej zostaje pytanie z szablonu.
        if not pytanie.endswith("?") or len(pytanie) > 400 or proponuje_ocene(pytanie):
            return PodpowiedzRozmowy(pytanie=None, dostawca=wynik.dostawca, tryb=str(wynik.tryb))
        return PodpowiedzRozmowy(pytanie=pytanie, dostawca=wynik.dostawca, tryb=str(wynik.tryb))

    return r
