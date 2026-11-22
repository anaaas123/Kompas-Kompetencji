"""API kroku 6 (#32): wynik okresowy, terminy i zawiadomienie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from kompas_core.pdf import hash_tresci
from kompas_core.skala import WynikSkali, oblicz_wynik
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from .krok2 import WyborKroku2
from .ocena import Decyzja, aktualne_decyzje
from .procesy import ProcesOceny, wczytaj_proces
from .qnt import MockQnt, Pracownik
from .samoocena import ukryj_przed_przekazaniem
from .zakonczenie import pracownik_procesu
from .terminy_okresowej import DaneTerminow, KonfiguracjaTerminow, TerminyOkresowej, oblicz_terminy
from .wynik_okresowy import KonfiguracjaWynikuOkresowego
from .zawiadomienie import zawiadomienie_pdf

_DECYZJE = TypeAdapter(dict[str, Decyzja])
_PRZYCZYNY_PISMA = {
    "zmiana_oceniajacego": "Zmiana osoby oceniającej w trakcie okresu oceny.",
    "przewidywana_nieobecnosc_ocenianego": "Przewidywana dłuższa usprawiedliwiona nieobecność ocenianego.",
    "przewidywana_nieobecnosc_oceniajacego": "Przewidywana dłuższa usprawiedliwiona nieobecność oceniającego.",
    "wniosek_ocenianego": "Uwzględnienie wniosku ocenianego o zmianę terminu.",
}


class DaneWynikuOkresowego(DaneTerminow):
    model_config = ConfigDict(extra="forbid")

    uzasadnienie: str | None = Field(default=None, max_length=4000)
    poprzednia_ocena_poziom: str | None = Field(default=None, max_length=120)
    dolacz_wniosek_o_stopien: bool = False

    @field_validator("uzasadnienie", "poprzednia_ocena_poziom")
    @classmethod
    def wyczysc_tekst(cls, tekst: str | None) -> str | None:
        return (tekst or "").strip() or None


class OcenaCzastkowa(BaseModel):
    kompetencja_id: str
    nazwa: str
    rodzaj: Literal["OBOWIAZKOWE", "DODATKOWE"]
    punkty: int


class PoprzedniaOcena(BaseModel):
    data: date
    wynik: Literal["pozytywna", "negatywna"]
    poziom: str | None = None


class CzescIII(BaseModel):
    dostepna: bool
    dolaczana: bool
    adnotacja: SourceRef


class WynikOkresowy(BaseModel):
    proces_id: int
    arkusz: Literal["B", "C"]
    zapisany: bool
    wersja_regul: str
    oceny_czastkowe: list[OcenaCzastkowa]
    obliczenie: WynikSkali
    uzasadnienie_wymagane: bool
    podstawa_uzasadnienia: SourceRef | None
    dane: DaneWynikuOkresowego
    terminy: TerminyOkresowej
    poprzednia_ocena: PoprzedniaOcena | None
    czesc_iii: CzescIII
    zawiadomienie_dostepne: bool


class _Zapis(BaseModel):
    dane: DaneWynikuOkresowego
    podstawa: str


@dataclass(frozen=True)
class MigawkaWyniku:
    proces: ProcesOceny
    pracownik: Pracownik
    wybory_json: str
    decyzje_json: str
    oceny: list[OcenaCzastkowa]
    zapis_json: str | None


class SerwisWynikuOkresowego:
    """Wspólne wyliczenie wyniku dla kroku 6 i arkusza oceny."""

    def __init__(
        self,
        konfiguracja: KonfiguracjaWynikuOkresowego,
        terminy: KonfiguracjaTerminow,
        punkty: list[int],
    ) -> None:
        self.konfiguracja = konfiguracja
        self.terminy = terminy
        self.skala = konfiguracja.skala_core(punkty)
        self.wersja = f"{konfiguracja.wersja}/{terminy.wersja}"

    def migawka(
        self,
        proces: ProcesOceny,
        pracownik: Pracownik,
        wybory_json: str | None,
        decyzje_json: str | None,
        zapis: str | None,
    ) -> MigawkaWyniku:
        if wybory_json is None:
            raise HTTPException(409, "Najpierw zatwierdź kryteria (krok 2).")

        wybor = WyborKroku2.model_validate_json(wybory_json)
        decyzje = aktualne_decyzje(wybor, _DECYZJE.validate_json(decyzje_json) if decyzje_json else {})
        oceny = []
        brakujace = []
        for kryterium in wybor.kryteria:
            decyzja = decyzje.get(kryterium.kompetencja_id)
            if decyzja is None:
                brakujace.append(kryterium.kompetencja_id)
                continue
            oceny.append(OcenaCzastkowa(
                kompetencja_id=kryterium.kompetencja_id, nazwa=kryterium.nazwa,
                rodzaj=kryterium.rodzaj, punkty=decyzja.punkty,
            ))
        if brakujace or not oceny:
            raise HTTPException(409, {
                "komunikat": "Najpierw zapisz bieżące oceny cząstkowe wszystkich kryteriów (krok 5).",
                "brakujace_kryteria": brakujace,
            })
        return MigawkaWyniku(proces, pracownik, wybory_json, decyzje_json, oceny, zapis)

    def podstawa(self, m: MigawkaWyniku) -> str:
        return hash_tresci({"kryteria": m.wybory_json, "decyzje": m.decyzje_json, "reguly": self.wersja})

    def widok(self, m: MigawkaWyniku, dane: DaneWynikuOkresowego, zapisany: bool) -> WynikOkresowy:
        try:
            obliczenie = oblicz_wynik([o.punkty for o in m.oceny], self.skala)
            wyliczone_terminy = oblicz_terminy(m.pracownik, dane, self.terminy)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        negatywna = obliczenie.wynik == "negatywna"
        urzednik = m.pracownik.korpus == "urzednik_sc"
        czesc_dostepna = urzednik and not negatywna
        poprzednia = m.pracownik.ostatnia_ocena_okresowa if urzednik else None
        return WynikOkresowy(
            proces_id=m.proces.id,
            arkusz=m.proces.arkusz,
            zapisany=zapisany,
            wersja_regul=self.wersja,
            oceny_czastkowe=m.oceny,
            obliczenie=obliczenie,
            uzasadnienie_wymagane=negatywna,
            podstawa_uzasadnienia=self.konfiguracja.uzasadnienie.adnotacje[0] if negatywna else None,
            dane=dane,
            terminy=wyliczone_terminy,
            poprzednia_ocena=PoprzedniaOcena(
                data=poprzednia.data, wynik=poprzednia.wynik, poziom=dane.poprzednia_ocena_poziom,
            ) if poprzednia else None,
            czesc_iii=CzescIII(
                dostepna=czesc_dostepna,
                dolaczana=czesc_dostepna and dane.dolacz_wniosek_o_stopien,
                adnotacja=self.konfiguracja.czesc_iii.adnotacje[0],
            ),
            zawiadomienie_dostepne=dane.zmiana_terminu is not None and wyliczone_terminy.termin_bazowy is not None,
        )

    def terminy_przed_ocena(self, pracownik: Pracownik, zapis: str | None) -> TerminyOkresowej:
        """Terminy cyklu bez ocen cząstkowych, np. do części I arkusza po kroku 2.

        Błąd danych terminów trafia do ``braki`` zamiast 422, bo podgląd arkusza musi się otworzyć.
        """
        dane = _Zapis.model_validate_json(zapis).dane if zapis else DaneWynikuOkresowego()
        try:
            return oblicz_terminy(pracownik, dane, self.terminy)
        except ValueError as e:
            return TerminyOkresowej(braki=(str(e),))

    def obecny_widok(self, m: MigawkaWyniku) -> WynikOkresowy:
        if m.zapis_json is None:
            return self.widok(m, DaneWynikuOkresowego(), False)
        zapis = _Zapis.model_validate_json(m.zapis_json)
        aktualny = zapis.podstawa == self.podstawa(m)
        dane = zapis.dane if aktualny else zapis.dane.model_copy(
            update={"uzasadnienie": None, "dolacz_wniosek_o_stopien": False},
        )
        return self.widok(m, dane, aktualny)


def router(auth: Autoryzacja, qnt: MockQnt, serwis: SerwisWynikuOkresowego) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["krok 6: wynik i terminy oceny okresowej"])
    sciezka = "/procesy/{proces_id}/wynik-okresowy"

    def dostepny(request: Request, proces_id: int, uz: Uzytkownik, akcja: str) -> MigawkaWyniku:
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), akcja)
        if proces.sciezka != "okresowa" or proces.arkusz not in ("B", "C"):
            raise HTTPException(409, "Krok 6 dotyczy oceny okresowej na arkuszu B lub C.")
        pracownik = pracownik_procesu(baza, pracownik, proces)
        ukryj_przed_przekazaniem(auth, uz, pracownik.model_dump(), baza, proces)

        wybory_json, decyzje_json, zapis = baza.execute(
            "SELECT krok2, decyzje, wynik_okresowy FROM procesy WHERE id = ?", (proces_id,)
        ).fetchone()
        return serwis.migawka(proces, pracownik, wybory_json, decyzje_json, zapis)

    @r.get(sciezka)
    def odczyt(proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc")) -> WynikOkresowy:
        """Przelicz wynik z zapisanych decyzji kroku 5 i pokaż terminy ze źródłami."""
        return serwis.obecny_widok(dostepny(request, proces_id, uz, "ocena.tresc"))

    @r.put(sciezka)
    def zapisz(
        proces_id: int, body: DaneWynikuOkresowego, request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> WynikOkresowy:
        """Zastąp dane kroku 6. Wynik wylicza serwer z bieżących decyzji przełożonego."""
        m = dostepny(request, proces_id, uz, "ocena.prowadz")
        if m.proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        wynik = serwis.widok(m, body, True)
        if wynik.uzasadnienie_wymagane and body.uzasadnienie is None:
            raise HTTPException(422, "Ocena negatywna wymaga uzasadnienia.")
        if body.dolacz_wniosek_o_stopien and not wynik.czesc_iii.dostepna:
            raise HTTPException(422, "Część III jest dostępna przy pozytywnej ocenie urzędnika służby cywilnej.")
        if body.poprzednia_ocena_poziom is not None and (
            wynik.poprzednia_ocena is None or body.poprzednia_ocena_poziom not in {p.poziom for p in serwis.konfiguracja.progi}
        ):
            raise HTTPException(422, "Wskaż poprawny poziom istniejącej poprzedniej oceny urzędnika.")

        nowy = _Zapis(dane=body, podstawa=serwis.podstawa(m))
        zapis_json = nowy.model_dump_json()
        if zapis_json == m.zapis_json:
            return wynik
        baza = request.app.state.baza
        with baza:
            zmieniono = baza.execute(
                "UPDATE procesy SET wynik_okresowy = ?, krok = MAX(krok, 6)"
                " WHERE id = ? AND status = 'W_TOKU' AND krok2 = ? AND decyzje = ? AND wynik_okresowy IS ?",
                (zapis_json, proces_id, m.wybory_json, m.decyzje_json, m.zapis_json),
            ).rowcount
        if not zmieniono:
            raise HTTPException(409, "Dane procesu zmieniły się. Odśwież wynik i ponów zapis.")

        przed = _Zapis.model_validate_json(m.zapis_json).dane.model_dump(mode="json") if m.zapis_json else None
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(
            uz.login, "proces", str(proces_id), {"wynik_okresowy": przed},
            {"wynik_okresowy": body.model_dump(mode="json"), "ocena": wynik.obliczenie.wynik}, serwis.wersja,
        )
        return wynik

    @r.get(
        sciezka + "/zawiadomienie.pdf", response_class=Response,
        responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
    )
    def zawiadomienie(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> Response:
        """Pobierz zawiadomienie z § 8 po zapisaniu zmiany terminu."""
        m = dostepny(request, proces_id, uz, "ocena.tresc")
        wynik = serwis.obecny_widok(m)
        zmiana = wynik.dane.zmiana_terminu
        bazowy = wynik.terminy.termin_bazowy
        if zmiana is None or bazowy is None:
            raise HTTPException(404, "Brak zapisanej zmiany terminu z § 8.")
        pdf = zawiadomienie_pdf(
            m.pracownik, bazowy.data, zmiana.nowy_termin, zmiana.data_zawiadomienia,
            _PRZYCZYNY_PISMA[zmiana.przyczyna], serwis.terminy.zrodlo_zmiany, serwis.wersja,
        )
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="zawiadomienie-{proces_id}.pdf"',
        })

    return r
