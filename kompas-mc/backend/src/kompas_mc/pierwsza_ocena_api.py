"""Odrębna ścieżka pierwszej oceny, sprawozdanie, wynik i wydruki."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from kompas_core.pdf import hash_tresci
from kompas_core.skala import WynikSkali
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field, TypeAdapter

from .arkusz_pierwszej_pdf import arkusz_pierwszej_oceny_pdf, rozmowa_wstepna_pdf
from .arkusze import (
    KOMUNIKAT_PODPIS, BrakArkusza, NiepoprawnePola, SekcjaArkusza,
    WzoryArkuszy, ZrodloArkusza, sprawdz_uzupelnienia,
)
from .krok2 import KonfiguracjaKroku2, WyborKroku2
from .metodyka import RejestrMetodyk
from .ocena import Decyzja, Mapowanie, aktualne_decyzje
from .pierwsza_ocena import DanePierwszejOceny, ZapisDanychPierwszej, uzupelnij_z_kadr, wypelnij_pierwsza
from .procesy import ProcesOceny, dzien_urzedowy, wczytaj_proces
from .qnt import MockQnt, Pracownik
from .rejestr import ustaw_szczegoly
from .terminy_pierwszej import KonfiguracjaTerminowPierwszej, TerminyPierwszej, oblicz_terminy_pierwszej
from .wynik_pierwszej import (
    KonfiguracjaWynikuPierwszej, EgzaminPierwszej, WarunekPierwszej,
    egzamin_z_qnt, sprawdz_podstawe_egzaminu, wynik_pierwszej,
)
from .zawiadomienie import zawiadomienie_pierwszej_pdf

_DECYZJE = TypeAdapter(dict[str, Decyzja])
_PDF = {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}


class ZapisPierwszejOceny(DanePierwszejOceny):
    zatwierdz: bool = Field(default=False, description="Zatwierdza kompletny arkusz w aplikacji.")


class ZakonczeniePierwszej(BaseModel):
    """Zakończenie pierwszej oceny po zapoznaniu ocenianego z oceną sporządzoną na piśmie (§ 11 ust. 1 rozp. 2015)."""

    data_zapoznania_z_ocena: date = Field(description="Dzień zapoznania ocenianego z oceną (podpis na arkuszu).")


class ArkuszPierwszej(BaseModel):
    zrodlo: ZrodloArkusza
    sekcje: list[SekcjaArkusza]
    przypisy: dict[str, str]
    braki: list[BrakArkusza]
    pdf_dostepny: bool
    zatwierdzony: bool
    komunikat_podpis: str = KOMUNIKAT_PODPIS


class StanPierwszejOceny(BaseModel):
    proces_id: int
    arkusz: Literal["PIERWSZA"] = "PIERWSZA"
    wersja_regul: str
    dane: DanePierwszejOceny
    terminy: TerminyPierwszej
    egzamin: EgzaminPierwszej | None
    przeslanki_egzaminu: dict[str, SourceRef]
    obliczenie: WynikSkali | None
    warunki: list[WarunekPierwszej]
    uzasadnienie_wymagane: bool
    podstawa_uzasadnienia: SourceRef
    wnioski_dostepne: bool
    podstawa_wnioskow: SourceRef
    mapowanie: Mapowanie
    wersja_metodyki: str
    zawiadomienie_dostepne: bool
    formularz: ArkuszPierwszej


CzytajPierwsza = Callable[[int, Request, Uzytkownik], StanPierwszejOceny]


@dataclass(frozen=True)
class _Migawka:
    proces: ProcesOceny
    pracownik: Pracownik
    przelozony: Pracownik | None
    kierujacy: Pracownik | None
    punkty: dict[str, int]
    wiersz: tuple[str | None, str | None, str | None]

    @property
    def zapis(self) -> ZapisDanychPierwszej:
        return ZapisDanychPierwszej.wczytaj(self.wiersz[2])


def _braki_sprawozdania(dane: DanePierwszejOceny, terminy: TerminyPierwszej) -> list[BrakArkusza]:
    brak = []
    if dane.data_zlozenia_sprawozdania is not None:
        if dane.sprawozdanie is None:
            brak.append(BrakArkusza(
                id="sprawozdanie", etykieta="Sprawozdanie", komunikat="Zarejestruj treść sprawozdania z § 6 ust. 2.",
            ))
        if terminy.sprawozdanie_min_7_miesiecy is not True:
            brak.append(BrakArkusza(
                id="sprawozdanie_okres", etykieta="Okres sprawozdania",
                komunikat="Sprawozdanie musi obejmować co najmniej 7 przepracowanych miesięcy (§ 6 ust. 1).",
            ))
    elif dane.sprawozdanie is not None:
        brak.append(BrakArkusza(
            id="data_zlozenia_sprawozdania", etykieta="Data złożenia sprawozdania",
            komunikat="Podaj faktyczną datę złożenia zarejestrowanego sprawozdania.",
        ))

    rozmowa = dane.data_rozmowy_oceniajacej
    zlozenie = dane.data_zlozenia_sprawozdania
    koniec = terminy.termin_sprawozdania_do
    if rozmowa and (zlozenie is None or rozmowa < zlozenie) and (koniec is not None and rozmowa <= koniec.data):
        brak.append(BrakArkusza(
            id="rozmowa_oceniajaca.data", etykieta="Rozmowa oceniająca",
            komunikat="Rozmowę oceniającą przeprowadza się po złożeniu sprawozdania lub po upływie terminu (§ 8 ust. 1).",
        ))
    if dane.data_sporzadzenia_oceny and terminy.pierwsza_ocena_do and not (
        terminy.pierwsza_ocena_od.data <= dane.data_sporzadzenia_oceny <= terminy.pierwsza_ocena_do.data
    ):
        brak.append(BrakArkusza(
            id="dokonanie_oceny.przelozony.data", etykieta="Data pierwszej oceny",
            komunikat="Data sporządzenia oceny wypada poza okresem dokonania pierwszej oceny.",
        ))
    return brak


def _sprawdz_gotowosc(widok: StanPierwszejOceny) -> None:
    if widok.formularz.braki:
        raise HTTPException(422, {
            "komunikat": "Uzupełnij dane pierwszej oceny.",
            "braki": [b.model_dump() for b in widok.formularz.braki],
        })


def router(
    auth: Autoryzacja,
    qnt: MockQnt,
    konf: KonfiguracjaWynikuPierwszej,
    konf_terminow: KonfiguracjaTerminowPierwszej,
    konf_krok2: KonfiguracjaKroku2,
    wzory: WzoryArkuszy,
    punkty: list[int],
) -> tuple[APIRouter, CzytajPierwsza]:
    r = APIRouter(prefix="/api/procesy/{proces_id}/pierwsza-ocena", tags=["pierwsza ocena w służbie cywilnej"])
    wersja = f"{konf.wersja}/{konf_terminow.wersja}/arkusze@{wzory.wersja}"
    kryteria = konf_krok2.obowiazkowe["PIERWSZA"].kompetencje
    wzor = wzory.dla("PIERWSZA")
    skala = konf.skala_core(punkty)

    def podstawa(m: _Migawka) -> str:
        return hash_tresci({"kryteria": m.wiersz[0], "decyzje": m.wiersz[1], "reguly": wersja})

    def wczytaj(request: Request, proces_id: int, uz: Uzytkownik, akcja: str) -> _Migawka:
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), akcja)
        if proces.sciezka != "pierwsza" or proces.arkusz != "PIERWSZA":
            raise HTTPException(409, "Ten proces nie jest ścieżką pierwszej oceny.")
        if akcja == "ocena.prowadz" and proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku.")
        wiersz = baza.execute(
            "SELECT krok2, decyzje, pierwsza_ocena FROM procesy WHERE id = ?", (proces_id,),
        ).fetchone()
        wybor, decyzje, _ = wiersz
        oceny = {}
        if wybor and decyzje:
            oceny = {
                k: d.punkty for k, d in aktualne_decyzje(
                    WyborKroku2.model_validate_json(wybor), _DECYZJE.validate_json(decyzje),
                ).items()
            }
        przelozony = qnt.pracownik(pracownik.przelozony_id)
        kierujacy = qnt.pracownik(przelozony.przelozony_id) if przelozony else None
        return _Migawka(proces, pracownik, przelozony, kierujacy, oceny, wiersz)

    def widok(request: Request, m: _Migawka, zapis: ZapisDanychPierwszej) -> tuple[StanPierwszejOceny, str]:
        dane = uzupelnij_z_kadr(zapis.dane, m.pracownik)
        egzamin = dane.egzamin or egzamin_z_qnt(m.pracownik)
        obliczenie, warunki = None, []
        try:
            if egzamin:
                sprawdz_podstawe_egzaminu(egzamin, m.pracownik)
            terminy = oblicz_terminy_pierwszej(m.pracownik, dane, konf_terminow)
            if all(k in m.punkty for k in kryteria) and egzamin and terminy.sprawozdanie_w_terminie is not None:
                obliczenie, warunki = wynik_pierwszej(
                    [m.punkty[k] for k in kryteria], skala, konf, egzamin, terminy.sprawozdanie_w_terminie,
                )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

        rejestr: RejestrMetodyk = request.app.state.metodyki
        metodyka = rejestr.dla_procesu(m.proces.id)
        mapowanie = rejestr.konfiguracja(metodyka).mapowanie_pierwsza
        sekcje, braki = wypelnij_pierwsza(
            wzor, dane, terminy, nazwa_urzedu=wzory.nazwa_urzedu, pracownik=m.pracownik,
            przelozony=m.przelozony, kierujacy=m.kierujacy, punkty=m.punkty,
            kolejnosc_kryteriow=kryteria, egzamin=egzamin, obliczenie=obliczenie,
        )
        braki.extend(_braki_sprawozdania(dane, terminy))
        if obliczenie and zapis.podstawa_decyzji != podstawa(m):
            braki.append(BrakArkusza(
                id="aktualne_decyzje", etykieta="Bieżące decyzje przełożonego",
                komunikat="Po zmianie ocen cząstkowych zapisz dane pierwszej oceny dla bieżącego wyniku.",
            ))
        odcisk = hash_tresci({
            "kryteria": m.wiersz[0], "decyzje": m.wiersz[1], "dane": dane.model_dump(mode="json"),
            "pola": [s.model_dump(mode="json") for s in sekcje],
            "reguly": wersja, "metodyka": metodyka.id, "wzor": wzor.zrodlo.sha256,
        })
        return StanPierwszejOceny(
            proces_id=m.proces.id, wersja_regul=wersja, dane=dane, terminy=terminy,
            egzamin=egzamin, przeslanki_egzaminu={k: reg.adnotacje[0] for k, reg in konf.przeslanki.items()},
            obliczenie=obliczenie, warunki=warunki,
            uzasadnienie_wymagane=bool(obliczenie and obliczenie.wynik == "negatywna"),
            podstawa_uzasadnienia=konf.uzasadnienie.adnotacje[0],
            wnioski_dostepne=bool(obliczenie and obliczenie.wynik == "pozytywna"),
            podstawa_wnioskow=konf.wnioski.adnotacje[0],
            mapowanie=mapowanie, wersja_metodyki=metodyka.id,
            zawiadomienie_dostepne=bool(
                dane.przedluzenie and terminy.termin_sprawozdania_bazowy_do
                and terminy.termin_sprawozdania_do
                and (
                    terminy.termin_sprawozdania_do.data != terminy.termin_sprawozdania_bazowy_do.data
                    or terminy.termin_sprawozdania_od.data != terminy.termin_sprawozdania_bazowy_od.data
                )
            ),
            formularz=ArkuszPierwszej(
                zrodlo=wzor.zrodlo, sekcje=sekcje, przypisy=wzor.przypisy, braki=braki,
                pdf_dostepny=not braki, zatwierdzony=not braki and odcisk == zapis.zatwierdzony_odcisk,
            ),
        ), odcisk

    def ukryj_przed_sporzadzeniem(uz: Uzytkownik, m: _Migawka) -> None:
        """Oceniany widzi punkty i arkusz pierwszej oceny dopiero po jej sporządzeniu na piśmie (zatwierdzeniu
        arkusza, § 11 rozp. 2015). Pierwsza ocena nie ma samooceny, więc blokada okresowej (przekazanie samooceny)
        tu nie pasuje; kopię części I–II po rozmowie wstępnej (§ 4 ust. 4) oceniany dostaje bez punktów."""
        if (
            m.proces.status == "W_TOKU" and m.zapis.zatwierdzony_odcisk is None
            and auth.moze(uz, "pracownik", m.pracownik.model_dump(), "samoocena.zapisz")
        ):
            raise HTTPException(403, "Pierwszą ocenę zobaczysz po jej sporządzeniu na piśmie przez przełożonego.")

    @r.get("")
    def odczyt(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> StanPierwszejOceny:
        """Pokaż terminy, status sprawozdania, egzamin, warunki wyniku i formularz pierwszej oceny."""
        m = wczytaj(request, proces_id, uz, "ocena.tresc")
        ukryj_przed_sporzadzeniem(uz, m)
        return widok(request, m, m.zapis)[0]

    @r.put("")
    def zapisz(
        proces_id: int, body: ZapisPierwszejOceny, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanPierwszejOceny:
        """Zastąp dane ścieżki. Wynik pochodzi z ocen cząstkowych zapisanych w kroku 5."""
        m = wczytaj(request, proces_id, uz, "ocena.prowadz")
        przed = m.zapis
        dane = DanePierwszejOceny.model_validate(body.model_dump(exclude={"zatwierdz"}))
        nowy = ZapisDanychPierwszej(
            dane=dane, zatwierdzony_odcisk=przed.zatwierdzony_odcisk, podstawa_decyzji=podstawa(m),
        )
        stan, _ = widok(request, m, nowy)
        try:
            pola = sprawdz_uzupelnienia(dane.pola, stan.formularz.sekcje)
        except NiepoprawnePola as e:
            raise HTTPException(422, e.szczegoly) from e
        nowy.dane = dane.model_copy(update={"pola": pola})
        stan, odcisk = widok(request, m, nowy)
        if stan.dane.wnioski_rozwojowe and not stan.wnioski_dostepne:
            raise HTTPException(422, "Wnioski rozwojowe są dostępne tylko po pozytywnej pierwszej ocenie (§ 10 ust. 6).")
        if body.zatwierdz:
            _sprawdz_gotowosc(stan)
            nowy.zatwierdzony_odcisk = odcisk
            stan.formularz.zatwierdzony = True
        elif nowy.zatwierdzony_odcisk != odcisk:
            nowy.zatwierdzony_odcisk = None
        krok = m.proces.krok
        if body.zatwierdz:
            krok = 7
        elif stan.obliczenie and (not stan.uzasadnienie_wymagane or stan.dane.uzasadnienie):
            krok = 6
        if nowy != przed or krok > m.proces.krok:
            baza = request.app.state.baza
            with baza:
                zmieniono = baza.execute(
                    "UPDATE procesy SET pierwsza_ocena = ?, krok = MAX(krok, ?)"
                    " WHERE id = ? AND status = 'W_TOKU' AND krok2 IS ? AND decyzje IS ? AND pierwsza_ocena IS ?",
                    (nowy.model_dump_json(), krok, proces_id, *m.wiersz),
                ).rowcount
            if not zmieniono:
                raise HTTPException(409, "Dane procesu zmieniły się. Odśwież pierwszą ocenę i ponów zapis.")
            dziennik: Dziennik = request.app.state.dziennik
            dziennik.zapisz(
                uz.login, "proces", str(proces_id), {"pierwsza_ocena": przed.model_dump(mode="json")},
                {"pierwsza_ocena": nowy.model_dump(mode="json")}, wersja,
            )
        return stan

    @r.post("/zakoncz")
    def zakoncz(
        proces_id: int, body: ZakonczeniePierwszej, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanPierwszejOceny:
        """Zakończ pierwszą ocenę po zapoznaniu ocenianego z oceną (§ 11 ust. 1 rozp. 2015).

        Wymaga zatwierdzonego arkusza (409). Data zapoznania nie wcześniejsza niż sporządzenie oceny i nie
        z przyszłości (422). Proces dostaje status ZAKONCZONY i krok 8; dalej decyzja kadrowa poza aplikacją.
        """
        m = wczytaj(request, proces_id, uz, "ocena.prowadz")
        stan, _ = widok(request, m, m.zapis)
        if not stan.formularz.zatwierdzony or stan.obliczenie is None:
            raise HTTPException(409, "Najpierw zatwierdź arkusz pierwszej oceny.")
        sporzadzono = stan.dane.data_sporzadzenia_oceny
        if sporzadzono is None:
            raise HTTPException(422, "Brak daty sporządzenia oceny na piśmie.")
        if body.data_zapoznania_z_ocena < sporzadzono:
            raise HTTPException(422, "Zapoznanie z oceną nie może być wcześniejsze niż jej sporządzenie.")
        if body.data_zapoznania_z_ocena > dzien_urzedowy(datetime.now(UTC)):
            raise HTTPException(422, "Data zapoznania z oceną nie może być z przyszłości.")
        zakonczenie = {
            "data_zapoznania_z_ocena": body.data_zapoznania_z_ocena.isoformat(),
            "data_sporzadzenia_oceny": sporzadzono.isoformat(), "wynik": stan.obliczenie.wynik,
            "zakonczyl": uz.login, "zakonczono": datetime.now(UTC).isoformat(),
        }
        baza = request.app.state.baza
        with baza:
            zmieniono = baza.execute(
                "UPDATE procesy SET status = 'ZAKONCZONY', krok = MAX(krok, 8), zakonczenie = ?"
                " WHERE id = ? AND status = 'W_TOKU' AND krok2 IS ? AND decyzje IS ? AND pierwsza_ocena IS ?",
                (json.dumps(zakonczenie, ensure_ascii=False), proces_id, *m.wiersz),
            ).rowcount
        if not zmieniono:
            raise HTTPException(409, "Dane procesu zmieniły się. Odśwież pierwszą ocenę i ponów zakończenie.")
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "proces", str(proces_id), {"status": "W_TOKU"},
                        {"status": "ZAKONCZONY", "zakonczenie": zakonczenie}, wersja)
        return stan

    @r.get("/arkusz.pdf", response_class=Response, responses={200: {"content": _PDF}})
    def arkusz(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> Response:
        """Pobierz arkusz pierwszej oceny z miejscami na podpisy odręczne."""
        ustaw_szczegoly(request, format="pdf")
        m = wczytaj(request, proces_id, uz, "ocena.tresc")
        ukryj_przed_sporzadzeniem(uz, m)
        stan, _ = widok(request, m, m.zapis)
        _sprawdz_gotowosc(stan)
        pdf = arkusz_pierwszej_oceny_pdf(
            wzor.model_dump(exclude_unset=True),
            {p.id: p.wartosc for s in stan.formularz.sekcje for p in s.pola if p.widoczne},
            drukuj_wnioski=stan.wnioski_dostepne, wersja=wersja,
        )
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="pierwsza-ocena-{proces_id}.pdf"',
        })

    @r.get("/rozmowa-wstepna.pdf", response_class=Response, responses={200: {"content": _PDF}})
    def rozmowa_wstepna(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> Response:
        """Pobierz część ogólną i rozmowę wstępną arkusza do podpisu po rozmowie wstępnej (rozp. 2015 § 3–4).

        Dostępne po zapisie daty rozmowy wstępnej i wyznaczonego końca terminu sprawozdania; wcześniej 409.
        """
        ustaw_szczegoly(request, format="pdf")
        m = wczytaj(request, proces_id, uz, "ocena.tresc")
        stan, _ = widok(request, m, m.zapis)
        if stan.terminy.data_rozmowy_wstepnej is None or stan.terminy.termin_sprawozdania_do is None:
            raise HTTPException(409, "Najpierw zapisz datę rozmowy wstępnej i wyznaczony termin sprawozdania.")
        pdf = rozmowa_wstepna_pdf(
            wzor.model_dump(exclude_unset=True),
            {p.id: p.wartosc for s in stan.formularz.sekcje for p in s.pola if p.widoczne},
            wersja=wersja,
        )
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="pierwsza-ocena-{proces_id}-rozmowa-wstepna.pdf"',
        })

    @r.get("/zawiadomienie.pdf", response_class=Response, responses={200: {"content": _PDF}})
    def zawiadomienie(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> Response:
        """Wygeneruj pismo o zapisanej zmianie terminu sprawozdania (§ 5 ust. 4)."""
        ustaw_szczegoly(request, format="pdf")
        m = wczytaj(request, proces_id, uz, "ocena.tresc")
        stan, _ = widok(request, m, m.zapis)
        if not stan.zawiadomienie_dostepne:
            raise HTTPException(404, "Brak zapisanej zmiany terminu sprawozdania.")
        pdf = zawiadomienie_pierwszej_pdf(
            m.pracownik, stan.dane.przedluzenie, stan.terminy, konf_terminow, wersja,
            nazwa_urzedu=wzory.nazwa_urzedu, oceniajacy=m.przelozony,
        )
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="pierwsza-zawiadomienie-{proces_id}.pdf"',
        })

    return r, odczyt
