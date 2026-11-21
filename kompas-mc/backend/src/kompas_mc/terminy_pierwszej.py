"""Kalendarz pierwszej oceny i sprawdzenie dat sprawozdania w wersji MC."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.kalendarz import RegulaTerminu, WynikTerminu, wyznacz_termin
from kompas_core.slad import KrokObliczenia, Regula
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .qnt import Pracownik


PrzyczynaPrzedluzenia = Literal[
    "usprawiedliwiona_nieobecnosc", "obowiazki_poza_miejscem_pracy", "przedluzenie_umowy",
]


class PrzedluzeniePierwszej(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nowy_termin: date
    data_zawiadomienia: date
    przyczyna: PrzyczynaPrzedluzenia
    okres_od: date | None = None
    okres_do: date | None = None
    nowy_termin_od: date | None = None

    @model_validator(mode="after")
    def _sprawdz_daty(self) -> PrzedluzeniePierwszej:
        if self.data_zawiadomienia > self.nowy_termin:
            raise ValueError("Zawiadomienie nie może przypadać po nowym terminie sprawozdania.")
        if (self.okres_od is None) != (self.okres_do is None):
            raise ValueError("Podaj obie daty okresu będącego przyczyną przedłużenia.")
        if self.okres_od and self.okres_do and self.okres_od > self.okres_do:
            raise ValueError("Koniec okresu będącego przyczyną przedłużenia poprzedza jego początek.")
        if self.nowy_termin_od and self.przyczyna != "przedluzenie_umowy":
            raise ValueError("Przy przedłużeniu o okres nieobecności lub pracy poza miejscem zmienia się koniec okna.")
        return self


class DaneTerminowPierwszej(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_ustalenia_oceny_zastepstwa: date | None = None
    data_konca_zatrudnienia: date | None = None
    data_rozmowy_wstepnej: date | None = None
    termin_sprawozdania_od: date | None = None
    wyznaczony_termin_sprawozdania: date | None = None
    przedluzenie: PrzedluzeniePierwszej | None = None
    data_zlozenia_sprawozdania: date | None = None
    sprawozdanie_niezlozone: bool = False
    sprawozdanie_okres_od: date | None = None
    sprawozdanie_okres_do: date | None = None
    data_rozmowy_oceniajacej: date | None = None
    data_sporzadzenia_oceny: date | None = None
    data_zapoznania_z_ocena: date | None = None

    @model_validator(mode="after")
    def _sprawdz_daty(self) -> DaneTerminowPierwszej:
        if self.sprawozdanie_niezlozone and self.data_zlozenia_sprawozdania is not None:
            raise ValueError("Podaj datę złożenia sprawozdania albo potwierdź jego niezłożenie po terminie.")

        for wczesniejsza, pozniejsza, komunikat in (
            (self.sprawozdanie_okres_od, self.sprawozdanie_okres_do,
             "Koniec okresu objętego sprawozdaniem poprzedza jego początek."),
            (self.sprawozdanie_okres_do, self.data_zlozenia_sprawozdania,
             "Sprawozdanie nie może obejmować okresu po dacie jego złożenia."),
            (self.data_rozmowy_oceniajacej, self.data_sporzadzenia_oceny,
             "Data sporządzenia oceny nie może poprzedzać rozmowy oceniającej."),
            (self.data_sporzadzenia_oceny, self.data_zapoznania_z_ocena,
             "Zapoznanie z oceną nie może poprzedzać jej sporządzenia."),
        ):
            if wczesniejsza and pozniejsza and wczesniejsza > pozniejsza:
                raise ValueError(komunikat)
        return self


class _Podstawa(BaseModel):
    id: str
    adnotacje: list[SourceRef] = Field(min_length=1)

    @property
    def regula(self) -> Regula:
        return Regula(self.id, self.adnotacje[0])

    def krok(self, opis: str) -> KrokObliczenia:
        return KrokObliczenia(self.regula, opis)


class _Odstep(_Podstawa):
    liczba: int
    jednostka: Literal["dni", "miesiace"]

    def od(self, data: date) -> WynikTerminu:
        return wyznacz_termin(data, RegulaTerminu(self.liczba, self.jednostka, self.regula))


class KonfiguracjaTerminowPierwszej(BaseModel):
    wersja: str
    rozmowa_wstepna: _Odstep
    rozmowa_wstepna_zastepstwo: _Odstep
    dzien_wolny: _Odstep
    uplyw_osmiu_miesiecy: _Odstep
    po_uplywie_osmiu_miesiecy: _Odstep
    ostatni_miesiac_umowy: _Odstep
    przed_ostatnim_miesiacem_umowy: _Odstep
    wyznaczenie_okna_sprawozdania: _Podstawa
    przedluzenie_okres: _Podstawa
    przedluzenie_umowy: _Podstawa
    granica_przedluzenia: _Podstawa
    zawiadomienie: _Podstawa
    okres_sprawozdania: _Odstep
    zlozenie_sprawozdania: _Podstawa
    dni_wolne: frozenset[date] = frozenset()

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaTerminowPierwszej:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))

    @property
    def zrodlo_przedluzenia(self) -> SourceRef:
        return self.zawiadomienie.regula.zrodlo

    def zrodlo_przyczyny(self, przyczyna: PrzyczynaPrzedluzenia) -> SourceRef:
        return self._podstawa_przedluzenia(przyczyna).regula.zrodlo

    def _podstawa_przedluzenia(self, przyczyna: PrzyczynaPrzedluzenia) -> _Podstawa:
        if przyczyna == "przedluzenie_umowy":
            return self.przedluzenie_umowy
        return self.przedluzenie_okres


class TerminyPierwszej(BaseModel):
    termin_rozmowy_wstepnej: WynikTerminu | None = None
    data_rozmowy_wstepnej: date | None = None
    pierwsza_ocena_od: WynikTerminu
    pierwsza_ocena_do: WynikTerminu | None = None
    termin_sprawozdania_bazowy_od: WynikTerminu
    termin_sprawozdania_bazowy_do: WynikTerminu | None = None
    termin_sprawozdania_od: WynikTerminu
    termin_sprawozdania_do: WynikTerminu | None = None
    sprawozdanie_w_terminie: bool | None = None
    sprawozdanie_min_7_miesiecy: bool | None = None
    slad: tuple[KrokObliczenia, ...] = ()
    braki: tuple[str, ...] = ()
    uwagi: tuple[str, ...] = ()


def _termin_rozmowy_wstepnej(
    pracownik: Pracownik, dane: DaneTerminowPierwszej, konf: KonfiguracjaTerminowPierwszej,
) -> WynikTerminu | None:
    zasada = konf.rozmowa_wstepna
    poczatek = pracownik.data_zatrudnienia
    if pracownik.zastepstwo:
        zasada = konf.rozmowa_wstepna_zastepstwo
        poczatek = dane.data_ustalenia_oceny_zastepstwa
        if poczatek is None:
            return None
        if poczatek < pracownik.data_zatrudnienia:
            raise ValueError("Data ustalenia oceny zastępstwa nie może poprzedzać zatrudnienia.")

    termin = zasada.od(poczatek)
    data, slad = termin.data, list(termin.slad)
    # Poradnik na s. 12 wymienia niedziele i dni ustawowo wolne.
    while data.weekday() == 6 or data in konf.dni_wolne:
        kolejny = konf.dzien_wolny.od(data)
        data = kolejny.data
        slad.extend(kolejny.slad)
    return WynikTerminu(data, tuple(slad))


def _pierwsza_ocena_do(koniec_umowy: date, konf: KonfiguracjaTerminowPierwszej) -> WynikTerminu:
    # Rys. 2 poradnika pokazuje ostatni dzień przed początkiem ostatniego miesiąca umowy.
    miesiac = konf.ostatni_miesiac_umowy.od(koniec_umowy)
    ostatni_dzien = konf.przed_ostatnim_miesiacem_umowy.od(miesiac.data)
    return WynikTerminu(ostatni_dzien.data, (*miesiac.slad, *ostatni_dzien.slad))


def _sprawdz_okno_sprawozdania(
    od: date, do: date | None, minimum: date, maksimum: date | None,
) -> None:
    if od < minimum:
        raise ValueError("Termin sprawozdania musi przypadać po upływie 8 miesięcy od zatrudnienia.")
    if do is not None and do < od:
        raise ValueError("Koniec terminu sprawozdania musi przypadać w dniu rozpoczęcia okna lub później.")
    if maksimum is not None and (do or od) > maksimum:
        raise ValueError("Termin sprawozdania musi umożliwić dokonanie pierwszej oceny przed ostatnim miesiącem umowy.")


def _okres_przedluzenia(pracownik: Pracownik, zmiana: PrzedluzeniePierwszej) -> tuple[date, date] | None:
    if zmiana.okres_od is not None and zmiana.okres_do is not None:
        return zmiana.okres_od, zmiana.okres_do
    if zmiana.przyczyna == "usprawiedliwiona_nieobecnosc":
        okresy = [okres for okres in pracownik.nieobecnosci if okres.rodzaj == "usprawiedliwiona"]
        if len(okresy) == 1:
            return okresy[0].od, okresy[0].do
    return None


def _zastosuj_przedluzenie(
    pracownik: Pracownik, zmiana: PrzedluzeniePierwszej, wynik: TerminyPierwszej,
    konf: KonfiguracjaTerminowPierwszej,
) -> None:
    stary = wynik.termin_sprawozdania_bazowy_do
    if stary is None:
        raise ValueError("Przed zmianą podaj pierwotny termin sprawozdania.")
    od = wynik.termin_sprawozdania_bazowy_od
    podstawa = konf._podstawa_przedluzenia(zmiana.przyczyna)
    if zmiana.nowy_termin_od is not None:
        od = WynikTerminu(zmiana.nowy_termin_od, (*od.slad, podstawa.krok(
            f"Nowy początek okna po przedłużeniu umowy wyznaczono na {zmiana.nowy_termin_od}.",
        )))
    if zmiana.nowy_termin == stary.data and od.data == wynik.termin_sprawozdania_bazowy_od.data:
        raise ValueError("Nowe okno złożenia sprawozdania musi się różnić od dotychczasowego.")

    maksimum = wynik.pierwsza_ocena_do
    if maksimum is None:
        raise ValueError("Przed zmianą podaj datę końca zatrudnienia potrzebną do sprawdzenia limitu z § 5 ust. 3.")
    _sprawdz_okno_sprawozdania(od.data, zmiana.nowy_termin, wynik.pierwsza_ocena_od.data, maksimum.data)
    slad = list(stary.slad)
    if zmiana.przyczyna != "przedluzenie_umowy":
        if zmiana.nowy_termin <= stary.data:
            raise ValueError("Przedłużenie o okres nieobecności lub pracy poza miejscem wymaga późniejszego terminu.")
        okres = _okres_przedluzenia(pracownik, zmiana)
        if okres is None:
            raise ValueError("Podaj okres nieobecności lub wykonywania obowiązków poza miejscem pracy.")
        poczatek, koniec = okres
        if poczatek < pracownik.data_zatrudnienia or koniec < poczatek:
            raise ValueError("Okres będący przyczyną przedłużenia musi przypadać w czasie zatrudnienia.")
        dni = (koniec - poczatek).days + 1
        przedluzony = wyznacz_termin(stary.data, RegulaTerminu(dni, "dni", podstawa.regula))
        if przedluzony.data != zmiana.nowy_termin:
            raise ValueError(f"Przedłużenie o {dni} dni daje termin {przedluzony.data}.")
        slad.extend(przedluzony.slad)

    slad.append(podstawa.krok(f"Zapisano zmianę końca okna z {stary.data} na {zmiana.nowy_termin}."))
    slad.extend(maksimum.slad)
    slad.append(konf.granica_przedluzenia.krok(
        f"Zmieniony termin {zmiana.nowy_termin} mieści się w granicy {maksimum.data}.",
    ))
    slad.append(konf.zawiadomienie.krok(
        f"Data pisemnego zawiadomienia: {zmiana.data_zawiadomienia}. Kopię dołącz do arkusza.",
    ))
    wynik.termin_sprawozdania_od = od
    wynik.termin_sprawozdania_do = WynikTerminu(zmiana.nowy_termin, tuple(slad))


def _dni_nieobecnosci(pracownik: Pracownik, od: date, do: date) -> int:
    """Policz każdy dzień z ewidencji co najwyżej raz i tylko w okresie sprawozdania."""
    dni = 0
    ostatni = od.toordinal() - 1
    for okres in sorted(pracownik.nieobecnosci, key=lambda n: n.od):
        poczatek = max(ostatni + 1, okres.od.toordinal())
        koniec = min(do.toordinal(), okres.do.toordinal())
        if poczatek <= koniec:
            dni += koniec - poczatek + 1
            ostatni = koniec
    return dni


def _sprawdz_sprawozdanie(
    pracownik: Pracownik, dane: DaneTerminowPierwszej, wynik: TerminyPierwszej,
    konf: KonfiguracjaTerminowPierwszej, braki: list[str], slad: list[KrokObliczenia],
) -> None:
    zlozenie = dane.data_zlozenia_sprawozdania
    koniec_okna = wynik.termin_sprawozdania_do
    if dane.sprawozdanie_niezlozone:
        wynik.sprawozdanie_w_terminie = False
        slad.append(konf.zlozenie_sprawozdania.krok("Potwierdzono niezłożenie sprawozdania w terminie."))
    elif zlozenie is not None and koniec_okna is not None:
        poczatek_okna = wynik.termin_sprawozdania_od.data
        wynik.sprawozdanie_w_terminie = poczatek_okna <= zlozenie <= koniec_okna.data
        slad.append(konf.zlozenie_sprawozdania.krok(
            f"Porównano datę złożenia {zlozenie} z oknem {poczatek_okna}–{koniec_okna.data}.",
        ))
    elif zlozenie is None:
        braki.append("Brak daty złożenia sprawozdania lub potwierdzenia jego niezłożenia po terminie.")

    od, do = dane.sprawozdanie_okres_od, dane.sprawozdanie_okres_do
    if od is None or do is None:
        if zlozenie is not None or od is not None or do is not None:
            braki.append("Brak dat początku lub końca przepracowanego okresu objętego sprawozdaniem.")
        return
    if od < pracownik.data_zatrudnienia:
        raise ValueError("Okres objęty sprawozdaniem nie może rozpoczynać się przed zatrudnieniem.")
    minimum = konf.okres_sprawozdania.od(od)
    slad.extend(minimum.slad)
    dni_nieobecnosci = _dni_nieobecnosci(pracownik, od, do)
    wynik.sprawozdanie_min_7_miesiecy = (do - minimum.data).days >= dni_nieobecnosci
    slad.append(konf.okres_sprawozdania.krok(
        f"Porównano koniec okresu {do} z granicą {minimum.data}, uwzględniając "
        f"{dni_nieobecnosci} dni nieobecności z ewidencji w okresie {od}–{do}.",
    ))


def oblicz_terminy_pierwszej(
    pracownik: Pracownik, dane: DaneTerminowPierwszej, konfiguracja: KonfiguracjaTerminowPierwszej,
) -> TerminyPierwszej:
    konf = konfiguracja
    braki: list[str] = []
    uwagi: list[str] = []
    slad: list[KrokObliczenia] = []

    zatrudnienie = pracownik.data_zatrudnienia
    koniec_umowy = dane.data_konca_zatrudnienia
    uplyw = konf.uplyw_osmiu_miesiecy.od(zatrudnienie)
    po_uplywie = konf.po_uplywie_osmiu_miesiecy.od(uplyw.data)
    od_oceny = WynikTerminu(po_uplywie.data, (*uplyw.slad, *po_uplywie.slad))

    do_oceny = None
    if koniec_umowy is None:
        braki.append("Brak daty końca zatrudnienia potrzebnej do ustalenia końca okna pierwszej oceny.")
    else:
        if koniec_umowy < zatrudnienie:
            raise ValueError("Koniec zatrudnienia nie może poprzedzać jego początku.")
        do_oceny = _pierwsza_ocena_do(koniec_umowy, konf)
        if do_oceny.data < od_oceny.data:
            uwagi.append("Podany okres zatrudnienia nie pozostawia okna na dokonanie pierwszej oceny.")

    rozmowa = dane.data_rozmowy_wstepnej
    if rozmowa is None and pracownik.pierwsza_ocena is not None:
        rozmowa = pracownik.pierwsza_ocena.rozmowa_wstepna
    termin_rozmowy = _termin_rozmowy_wstepnej(pracownik, dane, konf)
    if termin_rozmowy is None:
        braki.append("Brak daty ustalenia, że pracownik zatrudniony na zastępstwo podlega pierwszej ocenie.")
    if rozmowa is None:
        braki.append("Brak daty przeprowadzenia rozmowy wstępnej.")
    elif termin_rozmowy is not None and rozmowa > termin_rozmowy.data:
        uwagi.append("Rozmowę wstępną przeprowadzono po terminie.")

    podstawa_okna = konf.wyznaczenie_okna_sprawozdania
    jesli_wyznaczony = dane.termin_sprawozdania_od
    od_sprawozdania = WynikTerminu(jesli_wyznaczony or od_oceny.data, (*od_oceny.slad, podstawa_okna.krok(
        f"Początek okna na złożenie sprawozdania wyznaczono na {jesli_wyznaczony}." if jesli_wyznaczony
        else f"Przyjęto najwcześniejszy początek okna na złożenie sprawozdania: {od_oceny.data}.",
    )))
    do_sprawozdania = None
    if dane.wyznaczony_termin_sprawozdania is None:
        braki.append("Brak wyznaczonej daty końca terminu składania sprawozdania.")
    else:
        do_sprawozdania = WynikTerminu(dane.wyznaczony_termin_sprawozdania, (podstawa_okna.krok(
            f"Koniec okna na złożenie sprawozdania wyznaczono na {dane.wyznaczony_termin_sprawozdania}.",
        ),))

    if dane.termin_sprawozdania_od is not None or do_sprawozdania is not None:
        _sprawdz_okno_sprawozdania(od_sprawozdania.data, dane.wyznaczony_termin_sprawozdania,
                                  od_oceny.data, do_oceny.data if do_oceny else None)

    wynik = TerminyPierwszej(
        termin_rozmowy_wstepnej=termin_rozmowy,
        data_rozmowy_wstepnej=rozmowa,
        pierwsza_ocena_od=od_oceny,
        pierwsza_ocena_do=do_oceny,
        termin_sprawozdania_bazowy_od=od_sprawozdania,
        termin_sprawozdania_bazowy_do=do_sprawozdania,
        termin_sprawozdania_od=od_sprawozdania,
        termin_sprawozdania_do=do_sprawozdania,
    )
    if dane.przedluzenie is not None:
        _zastosuj_przedluzenie(pracownik, dane.przedluzenie, wynik, konf)
    _sprawdz_sprawozdanie(pracownik, dane, wynik, konf, braki, slad)

    sporzadzenie = dane.data_sporzadzenia_oceny
    if sporzadzenie is not None and (sporzadzenie < od_oceny.data or (do_oceny and sporzadzenie > do_oceny.data)):
        uwagi.append("Data sporządzenia oceny wypada poza oknem pierwszej oceny.")
    wynik.slad = tuple(slad)
    wynik.braki = tuple(braki)
    wynik.uwagi = tuple(uwagi)
    return wynik
