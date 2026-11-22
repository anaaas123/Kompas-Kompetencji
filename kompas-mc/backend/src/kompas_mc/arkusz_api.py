"""Krok 7: elektroniczny arkusz B/C, wydruk i rejestracja w mocku EZD."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from kompas_core.pdf import hash_tresci
from pydantic import BaseModel, ConfigDict, Field

from .arkusz_pdf import arkusz_pdf
from .arkusze import (
    KOMUNIKAT_PODPIS, BrakArkusza, NiepoprawnePola, SekcjaArkusza, WzorArkusza, WzoryArkuszy,
    ZrodloArkusza, sprawdz_uzupelnienia, wypelnij,
)
from .krok2 import KonfiguracjaKroku2, WyborKroku2
from .procesy import ProcesOceny, wczytaj_proces
from .qnt import MockQnt, OstatniaOcenaOkresowa, Pracownik
from .samoocena import ukryj_przed_przekazaniem
from .terminy_okresowej import TerminyOkresowej
from .wynik_okresowy_api import SerwisWynikuOkresowego, WynikOkresowy

_NIEZMIENIONY_PROCES = (
    "id = ? AND status = 'W_TOKU' AND krok2 IS ? AND decyzje IS ?"
    " AND wynik_okresowy IS ? AND arkusz_okresowy IS ?"
)


class DaneArkusza(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pola: dict[str, str | None] = Field(
        default_factory=dict, description="Pełny zestaw uzupełnień edytowalnych pól. Daty w formacie RRRR-MM-DD.",
    )
    zatwierdz: bool = Field(
        default=False, description="Wymaga kompletu danych. Zatwierdzenie w aplikacji nie stanowi podpisu.",
    )


class RejestracjaEzd(BaseModel):
    numer_sprawy: str
    zarejestrowano: datetime
    sha256_pdf: str
    mock: Literal[True] = True


class ArkuszOkresowy(BaseModel):
    proces_id: int
    arkusz: Literal["B", "C"]
    zrodlo: ZrodloArkusza
    wersja_wzoru: str
    sekcje: list[SekcjaArkusza]
    przypisy: dict[str, str]
    braki: list[BrakArkusza]
    pdf_dostepny: bool
    zatwierdzony: bool
    komunikat_podpis: str = KOMUNIKAT_PODPIS
    rejestracja_ezd: RejestracjaEzd | None = None


class DaneZakonczenia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_zapoznania_z_ocena: date | None = Field(
        default=None, description="Dzień zapoznania ocenianego z oceną (§ 12 ust. 1). Domyślnie z wyniku (krok 7).",
    )


class ZakonczenieOceny(BaseModel):
    """Zakończona ocena okresowa (#72): po zapoznaniu ocenianego z oceną sporządzoną na piśmie (§ 12 rozp. 2016)."""

    proces_id: int
    data_sporzadzenia_oceny: date
    data_zapoznania_z_ocena: date
    wynik: Literal["pozytywna", "negatywna"]
    srednia: str
    oceny_czastkowe: dict[str, int]
    zakonczyl: str
    zakonczono: datetime


def zastosuj_zakonczone(baza, qnt: MockQnt) -> None:
    """Przy starcie: zakończone oceny z aplikacji wracają do mocka QNT jako ostatnia ocena (kolejno od najstarszej)."""
    for osoba_id, zapis in baza.execute(
        "SELECT osoba_id, zakonczenie FROM procesy WHERE status = 'ZAKONCZONY' AND sciezka = 'okresowa'"
        " AND zakonczenie IS NOT NULL ORDER BY id"
    ):
        z = ZakonczenieOceny.model_validate_json(zapis)
        qnt.zapisz_ocene_okresowa(osoba_id, OstatniaOcenaOkresowa(
            data=z.data_sporzadzenia_oceny, wynik=z.wynik, oceny_czastkowe=z.oceny_czastkowe,
            data_zapoznania=z.data_zapoznania_z_ocena,
        ))


class _ZapisArkusza(BaseModel):
    pola: dict[str, str | None] = Field(default_factory=dict)
    zatwierdzony_odcisk: str | None = None


@dataclass(frozen=True)
class _StanProcesu:
    proces: ProcesOceny
    pracownik: Pracownik
    kryteria: WyborKroku2 | None
    wynik: WynikOkresowy | None
    oceniajacy_kryteria: Pracownik | None
    oceniajacy: Pracownik | None
    terminy: TerminyOkresowej | None
    wiersz: tuple[str | None, str | None, str | None, str | None]

    @property
    def zapis(self) -> _ZapisArkusza:
        return _ZapisArkusza.model_validate_json(self.wiersz[-1]) if self.wiersz[-1] else _ZapisArkusza()


@dataclass(frozen=True)
class _Dokument:
    widok: ArkuszOkresowy
    wzor: WzorArkusza
    wartosci: dict[str, str | None]
    odcisk: str
    czesc_iii: bool

    def pdf(self, *, tylko_czesc_i: bool = False) -> bytes:
        return arkusz_pdf(
            self.wzor.model_dump(exclude_unset=True), self.wartosci,
            drukuj_czesc_iii=self.czesc_iii and not tylko_czesc_i, wersja=self.widok.wersja_wzoru,
            tylko_czesc_i=tylko_czesc_i,
        )

    def odpowiedz_pdf(self, pdf: bytes, nazwa: str) -> Response:
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="arkusz-{self.widok.arkusz}-{self.widok.proces_id}{nazwa}.pdf"',
        })


def _rejestracja(wiersz: tuple) -> RejestracjaEzd:
    numer, zarejestrowano, sha, _ = wiersz
    return RejestracjaEzd(
        numer_sprawy=f"EZD-MC-{numer:06d}", zarejestrowano=datetime.fromisoformat(zarejestrowano), sha256_pdf=sha,
    )


def _wpis_ezd(baza, dokument: _Dokument) -> tuple | None:
    return baza.execute(
        "SELECT id, zarejestrowano, sha256_pdf, pdf FROM rejestr_ezd"
        " WHERE proces_id = ? AND odcisk = ?",
        (dokument.widok.proces_id, dokument.odcisk),
    ).fetchone()


def _wymagaj_kompletu(dokument: _Dokument) -> None:
    if dokument.widok.braki:
        raise HTTPException(422, {
            "komunikat": "Uzupełnij arkusz przed wykonaniem tej czynności.",
            "braki": [b.model_dump() for b in dokument.widok.braki],
        })


def router(
    auth: Autoryzacja,
    qnt: MockQnt,
    serwis: SerwisWynikuOkresowego,
    konf_krok2: KonfiguracjaKroku2,
    wzory: WzoryArkuszy,
) -> APIRouter:
    r = APIRouter(prefix="/api/procesy/{proces_id}/arkusz-okresowy", tags=["krok 7: arkusz B lub C"])
    wersja = f"arkusze@{wzory.wersja}"

    def wczytaj(request: Request, proces_id: int, uz: Uzytkownik, akcja: str) -> _StanProcesu:
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), akcja)
        if proces.sciezka != "okresowa" or proces.arkusz not in ("B", "C"):
            raise HTTPException(409, "Arkusz B/C dotyczy wyłącznie oceny okresowej.")
        ukryj_przed_przekazaniem(auth, uz, pracownik.model_dump(), baza, proces)
        if akcja == "ocena.prowadz" and proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")

        wiersz = baza.execute(
            "SELECT krok2, decyzje, wynik_okresowy, arkusz_okresowy FROM procesy WHERE id = ?", (proces_id,),
        ).fetchone()
        wybory, decyzje, zapis_wyniku, _ = wiersz
        kryteria = WyborKroku2.model_validate_json(wybory) if wybory else None
        try:
            migawka = serwis.migawka(proces, pracownik, wybory, decyzje, zapis_wyniku)
        except HTTPException as e:
            if e.status_code != 409:
                raise
            wynik = None
        else:
            wynik = serwis.obecny_widok(migawka)

        oceniajacy = qnt.pracownik(pracownik.przelozony_id)
        oceniajacy_kryteria = oceniajacy
        zmiana = pracownik.zmiana_oceniajacego
        data_ustalenia = wynik.dane.data_ustalenia_kryteriow if wynik else None
        if zmiana and data_ustalenia and data_ustalenia < zmiana.data:
            oceniajacy_kryteria = qnt.pracownik(zmiana.poprzedni_przelozony)
        if wynik:
            terminy = wynik.terminy
        elif kryteria:
            terminy = serwis.terminy_przed_ocena(pracownik, zapis_wyniku)
        else:
            terminy = None
        return _StanProcesu(proces, pracownik, kryteria, wynik, oceniajacy_kryteria, oceniajacy, terminy, wiersz)

    def dokument(stan: _StanProcesu, zapis: _ZapisArkusza) -> _Dokument:
        arkusz = stan.proces.arkusz
        wzor = wzory.dla(arkusz)
        sekcje, braki = wypelnij(
            wzor, zapis.pola, nazwa_urzedu=wzory.nazwa_urzedu, pracownik=stan.pracownik,
            oceniajacy_kryteria=stan.oceniajacy_kryteria, oceniajacy=stan.oceniajacy,
            kryteria=stan.kryteria, ids_obowiazkowych=konf_krok2.obowiazkowe[arkusz].kompetencje,
            wynik=stan.wynik, terminy=stan.terminy,
        )
        wartosci = {p.id: p.wartosc for s in sekcje for p in s.pola if p.widoczne}
        czesc_iii = bool(stan.wynik and stan.wynik.czesc_iii.dolaczana)
        odcisk = hash_tresci({
            "wzor": wzor.model_dump(), "wersja": wersja, "reguly": serwis.wersja,
            "wartosci": wartosci, "czesc_iii": czesc_iii,
        })
        widok = ArkuszOkresowy(
            proces_id=stan.proces.id, arkusz=arkusz, zrodlo=wzor.zrodlo, wersja_wzoru=wersja,
            sekcje=sekcje, przypisy=wzor.przypisy, braki=braki, pdf_dostepny=not braki,
            zatwierdzony=not braki and zapis.zatwierdzony_odcisk == odcisk,
        )
        return _Dokument(widok, wzor, wartosci, odcisk, czesc_iii)

    def widok_z_rejestrem(request: Request, doc: _Dokument) -> ArkuszOkresowy:
        wpis = _wpis_ezd(request.app.state.baza, doc) if doc.widok.pdf_dostepny else None
        if wpis:
            doc.widok.rejestracja_ezd = _rejestracja(wpis)
        return doc.widok

    @r.get("")
    def podglad(proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc")) -> ArkuszOkresowy:
        """Sekcje i pola wzoru, dane z procesu i QNT oraz lista braków do wydruku."""
        stan = wczytaj(request, proces_id, uz, "ocena.tresc")
        return widok_z_rejestrem(request, dokument(stan, stan.zapis))

    @r.put("")
    def zapisz(
        proces_id: int, body: DaneArkusza, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> ArkuszOkresowy:
        """Zastąp uzupełnienia formularza. Opcja zatwierdz rejestruje zgodę w aplikacji."""
        stan = wczytaj(request, proces_id, uz, "ocena.prowadz")
        przed = stan.zapis
        stary_widok = dokument(stan, przed).widok
        try:
            pola = sprawdz_uzupelnienia(body.pola, stary_widok.sekcje)
        except NiepoprawnePola as e:
            raise HTTPException(422, e.szczegoly) from e
        nowy = _ZapisArkusza(pola=pola, zatwierdzony_odcisk=przed.zatwierdzony_odcisk)
        doc = dokument(stan, nowy)
        if body.zatwierdz:
            _wymagaj_kompletu(doc)
            nowy.zatwierdzony_odcisk = doc.odcisk
            doc.widok.zatwierdzony = True
        elif doc.odcisk != przed.zatwierdzony_odcisk:
            nowy.zatwierdzony_odcisk = None
        if nowy != przed:
            baza = request.app.state.baza
            with baza:
                zmieniono = baza.execute(
                    f"UPDATE procesy SET arkusz_okresowy = ?, krok = MAX(krok, ?) WHERE {_NIEZMIENIONY_PROCES}",
                    (nowy.model_dump_json(), 7 if body.zatwierdz else stan.proces.krok, proces_id, *stan.wiersz),
                ).rowcount
            if not zmieniono:
                raise HTTPException(409, "Dane procesu zmieniły się. Odśwież arkusz i ponów zapis.")
            dziennik: Dziennik = request.app.state.dziennik
            dziennik.zapisz(
                uz.login, "proces", str(proces_id), {"arkusz_okresowy": przed.model_dump()},
                {"arkusz_okresowy": nowy.model_dump()}, wersja,
            )
        return widok_z_rejestrem(request, doc)

    @r.get(
        "/pdf", response_class=Response,
        responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
    )
    def pobierz_pdf(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> Response:
        """Pobierz wypełniony arkusz z miejscami na podpis odręczny. 422 zwraca listę braków."""
        stan = wczytaj(request, proces_id, uz, "ocena.tresc")
        doc = dokument(stan, stan.zapis)
        _wymagaj_kompletu(doc)
        wpis = _wpis_ezd(request.app.state.baza, doc)
        return doc.odpowiedz_pdf(wpis[-1] if wpis else doc.pdf(), "")

    @r.get(
        "/czesc-i/pdf", response_class=Response,
        responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
    )
    def pobierz_czesc_i_pdf(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc"),
    ) -> Response:
        """Pobierz samą część I do podpisu po rozmowie na początku okresu (rozp. 2016 § 5 ust. 3, § 6).

        Dostępna od zapisu kryteriów w kroku 2, bez wyniku oceny. Zawiera dane obu stron, kryteria,
        termin sporządzenia oceny i miejsca na podpisy. Przed krokiem 2 zwraca 409.
        """
        stan = wczytaj(request, proces_id, uz, "ocena.tresc")
        if stan.kryteria is None:
            raise HTTPException(409, "Najpierw zatwierdź kryteria (krok 2). Część I zawiera wybrane kryteria.")
        if stan.terminy is None or stan.terminy.termin_sporzadzenia_oceny is None:
            raise HTTPException(422, {
                "komunikat": "Nie można ustalić terminu sporządzenia oceny, który wpisuje się do części I.",
                "braki_terminu": list(stan.terminy.braki) if stan.terminy else [],
            })
        doc = dokument(stan, stan.zapis)
        return doc.odpowiedz_pdf(doc.pdf(tylko_czesc_i=True), "-czesc-I")

    @r.post("/ezd")
    def przekaz_do_ezd(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> RejestracjaEzd:
        """Rejestruj PDF w lokalnym mocku EZD. Ponowienie tej samej wersji zwraca ten sam numer.

        Zwraca numer sprawy, czas i SHA-256 zapisanego PDF. Wymaga kompletnego arkusza (422)
        i dostępu przełożonego (403). Zmiana danych w trakcie zapisu skutkuje 409.
        """
        stan = wczytaj(request, proces_id, uz, "ocena.prowadz")
        doc = dokument(stan, stan.zapis)
        _wymagaj_kompletu(doc)
        baza = request.app.state.baza
        if wpis := _wpis_ezd(baza, doc):
            return _rejestracja(wpis)

        pdf = doc.pdf()
        with baza:
            nowy = baza.execute(
                "INSERT INTO rejestr_ezd (proces_id, odcisk, zarejestrowano, sha256_pdf, pdf)"
                f" SELECT id, ?, ?, ?, ? FROM procesy WHERE {_NIEZMIENIONY_PROCES}"
                " ON CONFLICT(proces_id, odcisk) DO NOTHING",
                (doc.odcisk, datetime.now(UTC).isoformat(), sha256(pdf).hexdigest(), pdf, proces_id, *stan.wiersz),
            ).rowcount
        wpis = _wpis_ezd(baza, doc)
        if wpis is None:
            raise HTTPException(409, "Dane procesu zmieniły się. Odśwież arkusz i ponów rejestrację.")
        rejestracja = _rejestracja(wpis)
        if nowy:
            dziennik: Dziennik = request.app.state.dziennik
            dziennik.zapisz(
                uz.login, "proces", str(proces_id), None,
                {"mock_ezd": rejestracja.model_dump(mode="json")}, wersja,
            )
        return rejestracja

    @r.post("/zakoncz")
    def zakoncz(
        proces_id: int, body: DaneZakonczenia, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> ZakonczenieOceny:
        """Zakończ ocenę po zapoznaniu ocenianego z oceną sporządzoną na piśmie (§ 12 ust. 1 rozp. 2016).

        Wymaga zatwierdzonego, kompletnego arkusza (409/422). Proces dostaje status ZAKONCZONY i krok 8,
        a ocena trafia do kartoteki (mock QNT) jako ostatnia ocena okresowa, więc cykl liczy następny okres
        i można rozpocząć kolejną ocenę. Rejestracja w EZD jest możliwa tylko przed zakończeniem.
        """
        stan = wczytaj(request, proces_id, uz, "ocena.prowadz")
        doc = dokument(stan, stan.zapis)
        _wymagaj_kompletu(doc)
        if not doc.widok.zatwierdzony or stan.wynik is None:
            raise HTTPException(409, "Najpierw zatwierdź arkusz oceny (krok 7).")
        dane = stan.wynik.dane
        sporzadzono = dane.data_sporzadzenia_oceny
        zapoznano = body.data_zapoznania_z_ocena or dane.data_zapoznania_z_ocena
        if sporzadzono is None:
            raise HTTPException(422, "Brak daty sporządzenia oceny na piśmie (krok 7).")
        if zapoznano is None:
            raise HTTPException(422, "Podaj dzień zapoznania ocenianego z oceną (§ 12 ust. 1).")
        if zapoznano < sporzadzono:
            raise HTTPException(422, "Zapoznanie z oceną nie może być wcześniejsze niż jej sporządzenie.")
        obl = stan.wynik.obliczenie
        zak = ZakonczenieOceny(
            proces_id=proces_id, data_sporzadzenia_oceny=sporzadzono, data_zapoznania_z_ocena=zapoznano,
            wynik=obl.wynik, srednia=f"{obl.srednia:.2f}".replace(".", ","),
            oceny_czastkowe={o.kompetencja_id: o.punkty for o in stan.wynik.oceny_czastkowe},
            zakonczyl=uz.login, zakonczono=datetime.now(UTC),
        )
        baza = request.app.state.baza
        with baza:
            zmieniono = baza.execute(
                "UPDATE procesy SET status = 'ZAKONCZONY', krok = MAX(krok, 8), zakonczenie = ?"
                f" WHERE {_NIEZMIENIONY_PROCES}",
                (zak.model_dump_json(), proces_id, *stan.wiersz),
            ).rowcount
        if not zmieniono:
            raise HTTPException(409, "Dane procesu zmieniły się. Odśwież arkusz i ponów zakończenie.")
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "proces", str(proces_id), {"status": "W_TOKU"},
                        {"status": "ZAKONCZONY", "zakonczenie": zak.model_dump(mode="json")}, wersja)
        qnt.zapisz_ocene_okresowa(stan.pracownik.osoba_id, OstatniaOcenaOkresowa(
            data=sporzadzono, wynik=zak.wynik, oceny_czastkowe=zak.oceny_czastkowe, data_zapoznania=zapoznano,
        ))
        return zak

    return r
