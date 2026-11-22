"""API celów rozwojowych (#10).

Uprawnienia (``role.yaml``): ``cele.czytaj`` (przełożony, pracownik, HR), ``cele.proponuj``
(przełożony, pracownik), ``cele.zatwierdz`` (przełożony). Reguły dostępu do zasobu ``pracownik``
ograniczają przełożonego do podwładnych, a pracownika do siebie. HR ma tylko odczyt.
Konfiguracja: ``app.state.cele`` (``konfiguracja/cele.yaml``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik, WpisDziennika
from pydantic import BaseModel, Field

from . import cele as c
from .cele_llm import PodpowiedziLlm
from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import StanOceny, zbuduj_stan
from .ocena_api import _wczytaj_dane
from .procesy import ProcesOceny, wczytaj_proces
from .pseudonimizacja import Pseudonimizator
from .qnt import MockQnt
from .rejestr import ustaw_osobe
from .rozwoj import DaneRozwoju, OcenaWskaznika, zaproponuj
from .samoocena import wczytaj as wczytaj_samoocene


class Odrzucenie(BaseModel):
    komentarz: str = Field(max_length=2000)


class ZmianaStatusu(BaseModel):
    status: c.StatusPostepu


class ListaCelow(BaseModel):
    osoba_id: str
    pracownik_moze_edytowac: bool
    cele: list[c.Cel]
    regula: c.Regula


def router(auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["cele rozwojowe"])

    def osoba(osoba_id: str) -> dict:
        p = qnt.pracownik(osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        return p.model_dump()

    def aktor(uz: Uzytkownik, rekord: dict) -> c.Aktor:
        """Przełożony osoby (``cele.zatwierdz``) albo sam pracownik (``cele.proponuj``); inaczej 403."""
        if auth.moze(uz, "pracownik", rekord, "cele.zatwierdz"):
            return "przelozony"
        auth.sprawdz(uz, "pracownik", rekord, "cele.proponuj")
        return "pracownik"

    def konf(request: Request) -> c.KonfiguracjaCelow:
        return request.app.state.cele

    def sprawdz_wskaznik(wskaznik_id: str | None) -> None:
        if wskaznik_id is None:
            return
        if not any(w.id == wskaznik_id for k in stan2.model.kompetencje for w in k.wskazniki):
            raise HTTPException(422, f"Nie ma wskaźnika „{wskaznik_id}” w modelu kompetencji.")

    def zapisz_w_dzienniku(request: Request, uz: Uzytkownik, przed: c.Cel | None, po: c.Cel) -> None:
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "cel", str(po.id), c.zrzut(przed), c.zrzut(po), konf(request).regula.id)

    def blad(e: c.BladCelu) -> HTTPException:
        return HTTPException(e.kod, e.komunikat)

    @r.get("/pracownicy/{osoba_id}/cele")
    def lista(osoba_id: str, request: Request, uz: Uzytkownik = auth.wymagaj("cele.czytaj")) -> ListaCelow:
        """Cele osoby od najstarszego. Przełożony: podwładni, pracownik: siebie, HR: wszyscy (odczyt)."""
        auth.sprawdz(uz, "pracownik", osoba(osoba_id), "cele.czytaj")
        return ListaCelow(
            osoba_id=osoba_id,
            pracownik_moze_edytowac=konf(request).pracownik_moze_edytowac,
            cele=c.lista(request.app.state.baza, osoba_id),
            regula=konf(request).regula,
        )

    @r.post("/pracownicy/{osoba_id}/cele", status_code=201)
    def utworz(
        osoba_id: str, body: c.TrescCelu, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")
    ) -> c.Cel:
        """Nowy cel ze statusem ``propozycja``. Pracownik tylko przy ``pracownik_moze_edytowac: true``."""
        kto = aktor(uz, osoba(osoba_id))
        try:
            c.moze_tworzyc(kto, konf(request))
        except c.BladCelu as e:
            raise blad(e)
        sprawdz_wskaznik(body.wskaznik_id)
        cel = c.utworz(request.app.state.baza, osoba_id, body, uz.login, datetime.now(UTC))
        zapisz_w_dzienniku(request, uz, None, cel)
        return cel

    def cel_z_aktorem(request: Request, cel_id: int, uz: Uzytkownik) -> tuple[c.Cel, c.Aktor]:
        cel = c.wczytaj(request.app.state.baza, cel_id)
        if cel is None:
            raise HTTPException(404, "Nie ma takiego celu")
        ustaw_osobe(request, cel.osoba_id)  # rejestr: „Dotyczy” także przy zmianie, zatwierdzeniu i statusie celu
        return cel, aktor(uz, osoba(cel.osoba_id))

    def wykonaj(request: Request, uz: Uzytkownik, cel_id: int, zmiana) -> c.Cel:
        """Wczytuje cel, stosuje regułę ``zmiana(cel, aktor)``, zapisuje i dopisuje różnicę do dziennika."""
        przed, kto = cel_z_aktorem(request, cel_id, uz)
        try:
            nowy = zmiana(przed, kto)
        except c.BladCelu as e:
            raise blad(e)
        po = c.zapisz(request.app.state.baza, nowy, datetime.now(UTC))
        zapisz_w_dzienniku(request, uz, przed, po)
        return po

    @r.put("/cele/{cel_id}")
    def zmien(cel_id: int, body: c.TrescCelu, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")) -> c.Cel:
        """Zmiana treści. Pracownik (przy ``pracownik_moze_edytowac: true``) przywraca status
        ``propozycja``; przełożony zostawia status. Cel ``osiągnięty`` albo ``porzucony``: 409."""
        sprawdz_wskaznik(body.wskaznik_id)
        return wykonaj(request, uz, cel_id, lambda cel, kto: c.zmien_tresc(cel, body, kto, konf(request)))

    @r.post("/cele/{cel_id}/zatwierdz")
    def zatwierdz(cel_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("cele.zatwierdz")) -> c.Cel:
        """Przełożony zatwierdza propozycję. Pracownik: 403, inny status: 409."""
        return wykonaj(request, uz, cel_id, c.zatwierdz)

    @r.post("/cele/{cel_id}/odrzuc")
    def odrzuc(
        cel_id: int, body: Odrzucenie, request: Request, uz: Uzytkownik = auth.wymagaj("cele.zatwierdz")
    ) -> c.Cel:
        """Przełożony odrzuca propozycję; pusty komentarz: 422."""
        return wykonaj(request, uz, cel_id, lambda cel, kto: c.odrzuc(cel, kto, body.komentarz))

    @r.post("/cele/{cel_id}/status")
    def status(
        cel_id: int, body: ZmianaStatusu, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")
    ) -> c.Cel:
        """Postęp: ``w_realizacji`` (pracownik albo przełożony, z ``zatwierdzony``), ``osiągnięty``
        (pracownik zgłasza, przełożony potwierdza), ``porzucony`` (przełożony). Cel zamknięty: 409."""
        return wykonaj(request, uz, cel_id, lambda cel, kto: c.ustaw_status(cel, kto, body.status))

    def ostatni_proces(request: Request, osoba_id: str) -> ProcesOceny | None:
        baza = request.app.state.baza
        w = baza.execute(
            "SELECT id FROM procesy WHERE osoba_id = ? AND krok2 IS NOT NULL AND oceny_wskaznikow IS NOT NULL"
            " ORDER BY id DESC LIMIT 1",
            (osoba_id,),
        ).fetchone()
        return wczytaj_proces(baza, w[0]) if w else None

    def stan_oceny(request: Request, proces: ProcesOceny) -> StanOceny:
        oceny, decyzje = _wczytaj_dane(request.app.state.baza, proces.id)
        metodyki: RejestrMetodyk = request.app.state.metodyki
        return zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model,
            metodyki.konfiguracja(metodyki.dla_procesu(proces.id)),
        )

    @r.get("/pracownicy/{osoba_id}/cele/podpowiedzi")
    def podpowiedzi(
        osoba_id: str, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")
    ) -> c.WynikPodpowiedzi:
        """Propozycje celów do przyjęcia albo odrzucenia; status ``propozycja``, niczego nie zapisują.

        Najpierw LLM z RAG (#12): 1–3 cele SMART z modelu kompetencji i poradników o IPRZ, na
        podstawie wskaźników z ostatniego procesu, przekazanej samooceny i istniejących celów, po
        pseudonimizacji. Cel ze wskaźnikiem spoza modelu albo z cytatem bez pokrycia jest odrzucany.
        Gdy LLM zawiedzie (np. brak klucza) albo żaden cel nie przejdzie walidacji, zwraca propozycje
        regułowe ze wskaźników poniżej poziomu oczekiwań (``rozwoj.yaml``). Pracownik widzi
        podpowiedzi z oceny w toku dopiero po przekazaniu samooceny."""
        kto = aktor(uz, osoba(osoba_id))
        proces = ostatni_proces(request, osoba_id)
        if proces is None:
            return c.WynikPodpowiedzi(
                osoba_id=osoba_id, proces_id=None, podpowiedzi=[],
                komunikat="Brak ocenionych wskaźników: podpowiedzi pojawią się po ocenie w krokach 3–5.",
            )
        baza = request.app.state.baza
        status_samooceny, _, samoocena = wczytaj_samoocene(baza, proces.id)
        if kto == "pracownik" and proces.status == "W_TOKU" and status_samooceny != "przekazana":
            return c.WynikPodpowiedzi(
                osoba_id=osoba_id, proces_id=proces.id, podpowiedzi=[],
                komunikat="Podpowiedzi z bieżącej oceny będą dostępne po przekazaniu samooceny.",
            )
        stan = stan_oceny(request, proces)
        ocenione = [w for w in stan.dla_rozwoju if w.poziom is not None]

        kontekst = {
            "sciezka": proces.sciezka,
            "wskazniki_ocenione": [w.model_dump(mode="json") for w in ocenione],
            "samoocena": (
                {wid: s.model_dump(mode="json") for wid, s in samoocena.items()}
                if status_samooceny == "przekazana" else None
            ),
            "istniejace_cele": [
                cel.model_dump(mode="json", include={"nazwa", "opis", "wskaznik_id", "miernik", "termin", "status"})
                for cel in c.lista(baza, osoba_id)
            ],
        }
        llm: PodpowiedziLlm = request.app.state.cele_llm
        z_llm = llm.zaproponuj(
            Pseudonimizator(qnt).json(kontekst, osoba_id), [w.wskaznik_id for w in ocenione], date.today()
        )
        if z_llm.podpowiedzi:
            return c.WynikPodpowiedzi(
                osoba_id=osoba_id, proces_id=proces.id, podpowiedzi=z_llm.podpowiedzi, zrodlo="llm",
                dostawca=z_llm.dostawca, tryb=z_llm.tryb, odrzucone=z_llm.odrzucone,
            )

        konf_rozwoju = request.app.state.rozwoj
        wynik = zaproponuj(
            DaneRozwoju(
                sciezka=proces.sciezka,
                wskazniki=[OcenaWskaznika.model_validate(w.model_dump()) for w in stan.dla_rozwoju],
            ),
            konf_rozwoju,
        )
        return c.WynikPodpowiedzi(
            osoba_id=osoba_id, proces_id=proces.id,
            podpowiedzi=c.podpowiedzi_regulowe(wynik, konf_rozwoju.poziom_oczekiwan),
            odrzucone=z_llm.odrzucone,
        )

    @r.get("/cele/{cel_id}/historia")
    def historia(cel_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("cele.czytaj")) -> list[WpisDziennika]:
        """Dziennik zmian celu: kto, kiedy i które pola zmienił."""
        cel = c.wczytaj(request.app.state.baza, cel_id)
        if cel is None:
            raise HTTPException(404, "Nie ma takiego celu")
        auth.sprawdz(uz, "pracownik", osoba(cel.osoba_id), "cele.czytaj")
        return request.app.state.dziennik.historia("cel", str(cel_id))

    return r
