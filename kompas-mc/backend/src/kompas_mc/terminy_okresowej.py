"""Terminy oceny okresowej MC wraz z adnotacjami do materiałów źródłowych."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.kalendarz import RegulaTerminu, WynikTerminu, wyznacz_termin
from kompas_core.slad import KrokObliczenia, Regula
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .qnt import Pracownik


class ZmianaStanowiska(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: date
    istotna_zmiana_obowiazkow: bool


class ZmianaTerminu(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nowy_termin: date
    data_zawiadomienia: date
    przyczyna: Literal[
        "zmiana_oceniajacego",
        "przewidywana_nieobecnosc_ocenianego",
        "przewidywana_nieobecnosc_oceniajacego",
        "wniosek_ocenianego",
    ]

    @model_validator(mode="after")
    def _kolejnosc_dat(self) -> ZmianaTerminu:
        if self.nowy_termin < self.data_zawiadomienia:
            raise ValueError("Nowy termin nie może przypadać przed datą zawiadomienia.")
        return self


class DaneTerminow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_ustalenia_kryteriow: date | None = None
    data_zapoznania_z_kryteriami: date | None = None
    data_sporzadzenia_oceny: date | None = None
    data_zapoznania_z_ocena: date | None = None
    data_zapoznania_z_poprzednia_ocena: date | None = None
    zmiana_stanowiska: ZmianaStanowiska | None = None
    zmiana_terminu: ZmianaTerminu | None = None

    @model_validator(mode="after")
    def _kolejnosc_dat(self) -> DaneTerminow:
        if (
            self.data_zapoznania_z_ocena
            and self.data_sporzadzenia_oceny
            and self.data_zapoznania_z_ocena < self.data_sporzadzenia_oceny
        ):
            raise ValueError("Zapoznanie z oceną nie może poprzedzać sporządzenia oceny.")
        if (
            self.data_zapoznania_z_kryteriami
            and self.data_ustalenia_kryteriow
            and self.data_zapoznania_z_kryteriami < self.data_ustalenia_kryteriow
        ):
            raise ValueError("Zapoznanie z kryteriami nie może poprzedzać ustalenia kryteriów.")
        return self


class _Podstawa(BaseModel):
    id: str
    adnotacje: list[SourceRef] = Field(min_length=1)

    @property
    def regula(self) -> Regula:
        return Regula(self.id, self.adnotacje[0])


class _Odstep(_Podstawa):
    liczba: int
    jednostka: Literal["dni", "miesiace"]

    def od(self, data: date) -> WynikTerminu:
        return wyznacz_termin(data, RegulaTerminu(self.liczba, self.jednostka, self.regula))


class KonfiguracjaTerminow(BaseModel):
    wersja: str
    kryteria_zwykle: _Odstep
    kryteria_po_negatywnej: _Odstep
    cykl_podstawowy: _Odstep
    cykl_po_negatywnej: _Odstep
    dzien_po_uplywie_cyklu: _Odstep
    ponowne_kryteria: _Odstep
    granica_zmiany_stanowiska: _Odstep
    okno_zmiany_od: _Odstep
    okno_zmiany_do: _Odstep
    sprzeciw: _Odstep
    zmiana_oceniajacego: _Podstawa
    granica_zmiany_terminu: _Odstep
    zmiana_terminu: _Podstawa
    dzien_wolny: _Podstawa
    okno_oceny_koncowej: _Odstep
    """Od ilu dni przed terminem oceny na piśmie ocena końcowa jest bieżącą czynnością (GET /api/cykl)."""
    dni_wolne: frozenset[date] = frozenset()

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaTerminow:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))

    @property
    def zrodlo_zmiany(self) -> SourceRef:
        return self.zmiana_terminu.adnotacje[0]


class OknoSporzadzenia(BaseModel):
    od: WynikTerminu
    do: WynikTerminu


class TerminyOkresowej(BaseModel):
    termin_kryteriow: WynikTerminu | None = None
    termin_bazowy: WynikTerminu | None = None
    termin_sporzadzenia_oceny: WynikTerminu | None = None
    termin_sprzeciwu: WynikTerminu | None = None
    ponowne_kryteria: WynikTerminu | None = None
    okno_zmiany_stanowiska: OknoSporzadzenia | None = None
    zachowaj_kryteria: bool = False
    slad: tuple[KrokObliczenia, ...] = ()
    braki: tuple[str, ...] = ()


def _dzien_roboczy(wynik: WynikTerminu, konf: KonfiguracjaTerminow) -> WynikTerminu:
    # Poradnik s. 9 opisuje niedzielę i święto. CORE-2 przy domyślnym
    # przesunięciu pomija też każdą sobotę, więc stosujemy dni z materiału MC.
    data = wynik.data
    slad = list(wynik.slad)
    while data.weekday() == 6 or data in konf.dni_wolne:
        kolejny = wyznacz_termin(data, RegulaTerminu(1, "dni", konf.dzien_wolny.regula))
        data = kolejny.data
        slad.extend(kolejny.slad)
    return WynikTerminu(data, tuple(slad))


def _uwzglednij_zmiane_stanowiska(
    wynik: TerminyOkresowej, dane: DaneTerminow, ostatnia_data: date | None,
    konf: KonfiguracjaTerminow, braki: list[str], slad: list[KrokObliczenia],
) -> None:
    zmiana = dane.zmiana_stanowiska
    if zmiana is None or not zmiana.istotna_zmiana_obowiazkow:
        return

    ustalenie = ostatnia_data or dane.data_ustalenia_kryteriow
    zapoznanie = ostatnia_data or dane.data_zapoznania_z_kryteriami
    if ustalenie is not None:
        granica = konf.granica_zmiany_stanowiska.od(ustalenie)
        if ustalenie <= zmiana.data <= granica.data:
            wynik.ponowne_kryteria = _dzien_roboczy(konf.ponowne_kryteria.od(zmiana.data), konf)
            slad.extend(granica.slad)
            slad.append(KrokObliczenia(
                konf.ponowne_kryteria.regula,
                "Powtórz czynności dotyczące kryteriów w ustawionym terminie. Termin oceny pozostaje bez zmian.",
            ))
            return

    if zapoznanie is None:
        braki.append("Brak daty zapoznania z kryteriami potrzebnej do oceny skutku zmiany stanowiska.")
        return
    granica = konf.granica_zmiany_stanowiska.od(zapoznanie)
    if zmiana.data > granica.data:
        od = konf.okno_zmiany_od.od(zmiana.data)
        do = _dzien_roboczy(konf.okno_zmiany_do.od(zmiana.data), konf)
        wynik.okno_zmiany_stanowiska = OknoSporzadzenia(od=od, do=do)
        wynik.termin_bazowy = do
        slad.extend(granica.slad)
        return
    if ustalenie is None and zmiana.data >= zapoznanie:
        braki.append("Brak daty ustalenia kryteriów potrzebnej do wyznaczenia terminu ich ponowienia.")
    elif ustalenie is not None and zmiana.data > konf.granica_zmiany_stanowiska.od(ustalenie).data:
        braki.append(
            "Zmiana wypadła między upływem 6 miesięcy od ustalenia kryteriów i upływem 6 miesięcy "
            "od zapoznania z nimi. Skutek zmiany wymaga potwierdzenia."
        )


def _zastosuj_zmiane_terminu(
    zmiana: ZmianaTerminu, wynik: TerminyOkresowej, kotwica: date | None,
    po_negatywnej: bool, konf: KonfiguracjaTerminow,
) -> WynikTerminu:
    bazowy = wynik.termin_bazowy
    if po_negatywnej or wynik.okno_zmiany_stanowiska is not None or bazowy is None:
        raise ValueError("Zmiana z zawiadomieniem dotyczy ustalonego terminu cyklu 24-miesięcznego.")
    if kotwica is None:
        raise ValueError("Przed zmianą terminu podaj datę zapoznania z kryteriami.")

    granica = konf.granica_zmiany_terminu.od(kotwica)
    if zmiana.data_zawiadomienia <= granica.data:
        raise ValueError("Zmianę terminu można zastosować po upływie więcej niż 6 miesięcy.")
    if zmiana.nowy_termin == bazowy.data:
        raise ValueError("Nowy termin musi różnić się od dotychczasowego.")

    krok = KrokObliczenia(
        konf.zmiana_terminu.regula,
        f"Zapisano zmianę terminu z {bazowy.data} na {zmiana.nowy_termin} i datę zawiadomienia "
        f"{zmiana.data_zawiadomienia}. Kopię pisma dołącz do arkusza.",
    )
    return WynikTerminu(zmiana.nowy_termin, (*bazowy.slad, *granica.slad, krok))


def oblicz_terminy(
    pracownik: Pracownik, dane: DaneTerminow, konfiguracja: KonfiguracjaTerminow,
) -> TerminyOkresowej:
    konf = konfiguracja
    ostatnia = pracownik.ostatnia_ocena_okresowa
    ostatnia_data = ostatnia.data if ostatnia else None
    kotwica = ostatnia_data or (
        pracownik.data_zatrudnienia if pracownik.rodzaj_umowy == "nieokreslony" else None
    )
    po_negatywnej = ostatnia is not None and ostatnia.wynik == "negatywna"
    wynik = TerminyOkresowej()
    braki: list[str] = []
    slad: list[KrokObliczenia] = []

    if kotwica is None:
        braki.append("Brak daty poprzedniej oceny pisemnej lub zatrudnienia na czas nieokreślony.")
    else:
        kryteria = konf.kryteria_po_negatywnej if po_negatywnej else konf.kryteria_zwykle
        wynik.termin_kryteriow = _dzien_roboczy(kryteria.od(kotwica), konf)
        if not po_negatywnej:
            wynik.termin_bazowy = _dzien_roboczy(konf.cykl_podstawowy.od(kotwica), konf)

    if po_negatywnej:
        # Formularz kroku 7 ma pierwszeństwo; bez niego data z akt osobowych (kartoteka QNT).
        poprzednie_zapoznanie = dane.data_zapoznania_z_poprzednia_ocena or ostatnia.data_zapoznania
        if poprzednie_zapoznanie is None:
            braki.append("Brak daty zapoznania z poprzednią oceną negatywną potrzebnej do wyznaczenia ponownej oceny.")
        elif ostatnia_data is not None and poprzednie_zapoznanie < ostatnia_data:
            raise ValueError("Zapoznanie z poprzednią oceną nie może poprzedzać jej sporządzenia.")
        else:
            uplyw = konf.cykl_po_negatywnej.od(poprzednie_zapoznanie)
            dzien = konf.dzien_po_uplywie_cyklu.od(uplyw.data)
            wynik.termin_bazowy = WynikTerminu(dzien.data, (*uplyw.slad, *dzien.slad))

    _uwzglednij_zmiane_stanowiska(wynik, dane, ostatnia_data, konf, braki, slad)

    zmiana_oceniajacego = pracownik.zmiana_oceniajacego
    poczatek = dane.data_zapoznania_z_kryteriami or dane.data_ustalenia_kryteriow or kotwica
    if (
        zmiana_oceniajacego is not None
        and wynik.ponowne_kryteria is None
        and (poczatek is None or zmiana_oceniajacego.data >= poczatek)
        and (dane.data_sporzadzenia_oceny is None or zmiana_oceniajacego.data <= dane.data_sporzadzenia_oceny)
    ):
        wynik.zachowaj_kryteria = True
        slad.append(KrokObliczenia(
            konf.zmiana_oceniajacego.regula,
            f"Zmiana oceniającego {zmiana_oceniajacego.data}. Zachowaj wcześniej wybrane kryteria.",
        ))

    wynik.termin_sporzadzenia_oceny = wynik.termin_bazowy
    if dane.zmiana_terminu is not None:
        wynik.termin_sporzadzenia_oceny = _zastosuj_zmiane_terminu(
            dane.zmiana_terminu, wynik, ostatnia_data or dane.data_zapoznania_z_kryteriami,
            po_negatywnej, konf,
        )

    if dane.data_zapoznania_z_ocena is not None:
        wynik.termin_sprzeciwu = _dzien_roboczy(konf.sprzeciw.od(dane.data_zapoznania_z_ocena), konf)

    wynik.slad = tuple(slad)
    wynik.braki = tuple(braki)
    return wynik


def dane_terminow_procesu(zapis_wyniku: str | None, **z_kroku_2: date | None) -> DaneTerminow:
    """Dane terminów procesu z zapisu oceny na piśmie (zmiana terminu i stanowiska, daty), uzupełnione datami
    z kroku 2, gdy zapis ich nie ma. Jedno źródło dla wyniku, cyklu i panelu HR (Helix G3, pkt 5, zgłoszenie 124).
    Błąd kolejności dat: ``ValueError`` jak przy ``DaneTerminow``."""
    dane: dict = {}
    if zapis_wyniku:
        zapisane = json.loads(zapis_wyniku).get("dane") or {}
        dane = {k: v for k, v in zapisane.items() if k in DaneTerminow.model_fields and v is not None}
    for pole, wartosc in z_kroku_2.items():
        if wartosc is not None:
            dane.setdefault(pole, wartosc)
    return DaneTerminow.model_validate(dane)
