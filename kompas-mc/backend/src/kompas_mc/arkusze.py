"""Wzory arkuszy i dane wydruku oceny okresowej (M-7)."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .krok2 import WyborKroku2
from .qnt import Pracownik
from .terminy_okresowej import TerminyOkresowej
from .wynik_okresowy_api import WynikOkresowy

KOMUNIKAT_PODPIS = "Wygenerowanie PDF i użycie „Zatwierdź” nie są podpisem."

EDYTOWALNE = frozenset({
    "nazwa_urzedu",
    "potwierdzenie_kryteriow.oceniajacy.miejscowosc",
    "potwierdzenie_kryteriow.oceniany.miejscowosc",
    "rozmowa_oceniajaca.data",
    "wnioski_iprz",
    "dokonanie_oceny.oceniajacy.miejscowosc",
    "zapoznanie.oceniany.miejscowosc",
    "urzednik.rok_mianowania",
    "urzednik.stopien_sluzbowy",
    "urzednik.data_przyznania_stopnia",
    "wniosek_o_stopien.stopien",
    "wniosek_o_stopien.umotywowanie",
    "wniosek_o_stopien.oceniajacy.miejscowosc",
    "wniosek_o_stopien.oceniajacy.data",
})

OPCJONALNE_PRZED_DRUKIEM = frozenset({
    "zapoznanie.oceniany.miejscowosc", "zapoznanie.oceniany.data",
})

DANE_OSOBY = {
    "imie": "imie",
    "nazwisko": "nazwisko",
    "komorka_organizacyjna": "komorka",
    "stanowisko": "stanowisko",
}


class ZrodloArkusza(BaseModel):
    sciezka: str
    zalacznik: int
    sha256: str


class PoleWzoru(BaseModel):
    id: str
    etykieta: str
    rodzaj: str
    lokalizator: str
    warianty: list[int | str] = Field(default_factory=list)
    przypisy: list[int] = Field(default_factory=list)
    fakultatywne: bool = False
    pokaz_gdy: list[str] = Field(default_factory=list)
    wymagane_gdy: list[str] = Field(default_factory=list)


class SekcjaWzoru(BaseModel):
    tytul: str
    pola: list[PoleWzoru]
    drukuj_gdy: list[str] = Field(default_factory=list)
    pokaz_gdy: list[str] = Field(default_factory=list)
    przypisy: list[int] = Field(default_factory=list)


class WzorArkusza(BaseModel):
    id: Literal["okresowa_b", "okresowa_c", "pierwsza"]
    zrodlo: ZrodloArkusza
    zakres_punktow: list[int]
    kolejnosc_kryteriow: list[str]
    sekcje: list[SekcjaWzoru]
    przypisy: dict[str, str]
    uwagi: list[str]


class WzoryArkuszy(BaseModel):
    wersja: int
    wzory: list[WzorArkusza]
    nazwa_urzedu: str

    @classmethod
    def z_pliku(cls, plik: Path) -> WzoryArkuszy:
        return cls.model_validate_json(plik.read_text(encoding="utf-8"))

    def dla(self, arkusz: Literal["B", "C", "PIERWSZA"]) -> WzorArkusza:
        wzor_id = "pierwsza" if arkusz == "PIERWSZA" else f"okresowa_{arkusz.lower()}"
        return next(w for w in self.wzory if w.id == wzor_id)


class PoleArkusza(PoleWzoru):
    wartosc: str | None
    widoczne: bool
    edytowalne: bool
    wymagane: bool


class SekcjaArkusza(BaseModel):
    tytul: str
    widoczna: bool
    przypisy: list[int]
    pola: list[PoleArkusza]


class BrakArkusza(BaseModel):
    id: str
    etykieta: str
    komunikat: str


def wypelnij(
    wzor: WzorArkusza,
    uzupelnienia: dict[str, str | None],
    *,
    nazwa_urzedu: str,
    pracownik: Pracownik,
    oceniajacy_kryteria: Pracownik | None,
    oceniajacy: Pracownik | None,
    kryteria: WyborKroku2 | None,
    ids_obowiazkowych: list[str],
    wynik: WynikOkresowy | None,
    terminy: TerminyOkresowej | None,
) -> tuple[list[SekcjaArkusza], list[BrakArkusza]]:
    """Połącz wartości ze źródeł i pola uzupełniane przez przełożonego.

    ``terminy`` są dostępne od kroku 2, także przed wystawieniem oceny (część I, § 5 ust. 3 rozp. 2016).
    """
    dane = wynik.dane if wynik else None
    poprzednia = wynik.poprzednia_ocena if wynik else None
    czesc_iii = bool(wynik and wynik.czesc_iii.dolaczana)
    pozytywna = bool(wynik and wynik.obliczenie.wynik == "pozytywna")
    urzednik = pracownik.korpus == "urzednik_sc"
    termin = terminy.termin_sporzadzenia_oceny if terminy else None
    zmiana = dane.zmiana_stanowiska if dane else None
    data_oceny = dane.data_sporzadzenia_oceny if dane else None
    koniec_przed_zmiana = bool(
        zmiana and wynik and wynik.terminy.okno_zmiany_stanowiska and data_oceny and data_oceny >= zmiana.data
    )
    status_wniosku = None
    if wynik:
        status_wniosku = ("TAK" if czesc_iii else "NIE") if urzednik else "NIE DOTYCZY"

    wartosci = {
        "nazwa_urzedu": nazwa_urzedu,
        "termin_sporzadzenia_oceny": _data(termin.data) if termin else None,
        "potwierdzenie_kryteriow.oceniajacy.data": _data(dane.data_ustalenia_kryteriow) if dane else None,
        "potwierdzenie_kryteriow.oceniany.data": _data(dane.data_zapoznania_z_kryteriami) if dane else None,
        "okres_oceny.od": _data(dane.data_zapoznania_z_kryteriami) if dane else None,
        "okres_oceny.do": None if koniec_przed_zmiana else _data(data_oceny),
        "srednia": str(wynik.obliczenie.srednia).replace(".", ",") if wynik else None,
        "poziom": wynik.obliczenie.poziom if wynik else None,
        "wynik": wynik.obliczenie.wynik.upper() if wynik else None,
        "uzasadnienie": dane.uzasadnienie if dane else None,
        "poprzednia_ocena.wynik": poprzednia.wynik if poprzednia else None,
        "poprzednia_ocena.poziom": poprzednia.poziom if poprzednia else None,
        "poprzednia_ocena.data": _data(poprzednia.data) if poprzednia else None,
        "wniosek_o_stopien.status": status_wniosku,
        "dokonanie_oceny.oceniajacy.data": _data(data_oceny),
        "zapoznanie.oceniany.data": _data(dane.data_zapoznania_z_ocena) if dane else None,
        "zapoznanie.oceniany.imie_nazwisko_lub_pieczatka": _pelne_imie(pracownik),
        "urzednik.imie": pracownik.imie,
        "urzednik.nazwisko": pracownik.nazwisko,
        "wniosek_o_stopien.imie_nazwisko": _pelne_imie(pracownik),
        "wniosek_o_stopien.oceniajacy.imie_nazwisko_lub_pieczatka": _pelne_imie(oceniajacy),
    }
    edytowalne = set(EDYTOWALNE)
    if koniec_przed_zmiana:
        edytowalne.add("okres_oceny.do")

    for prefiks, osoba in {
        "oceniany": pracownik, "oceniajacy.czesc_I": oceniajacy_kryteria, "oceniajacy.czesc_II": oceniajacy,
    }.items():
        for pole, atrybut in DANE_OSOBY.items():
            klucz = f"{prefiks}.{pole}"
            wartosc = getattr(osoba, atrybut, None)
            wartosci[klucz] = wartosc
            if not wartosc:
                edytowalne.add(klucz)
    if not wartosci["wniosek_o_stopien.oceniajacy.imie_nazwisko_lub_pieczatka"]:
        edytowalne.add("wniosek_o_stopien.oceniajacy.imie_nazwisko_lub_pieczatka")

    punkty = {o.kompetencja_id: str(o.punkty) for o in wynik.oceny_czastkowe} if wynik else {}
    dodatkowe = [k for k in kryteria.kryteria if k.rodzaj == "DODATKOWE"] if kryteria else []
    for numer, kryterium in enumerate(ids_obowiazkowych, start=1):
        wartosci[f"ocena_obowiazkowa.{numer}"] = punkty.get(kryterium)

    warunki = {
        "oceniany_jest_urzednikiem": urzednik,
        "ocena_pozytywna": pozytywna,
        "ocena_negatywna": bool(wynik and wynik.uzasadnienie_wymagane),
        "skladany_wniosek_o_stopien": czesc_iii,
    }
    for numer, kryterium in enumerate(dodatkowe, start=1):
        klucz = f"kryterium_dodatkowe.{numer}"
        warunki[f"{klucz}_wybrane"] = True
        wartosci[klucz] = kryterium.nazwa
        wartosci[f"ocena_dodatkowa.{numer}.kryterium"] = kryterium.nazwa
        wartosci[f"ocena_dodatkowa.{numer}.punkty"] = punkty.get(kryterium.kompetencja_id)

    wartosci.update({k: v for k, v in uzupelnienia.items() if k in edytowalne})
    pominiete = {"poprzednia_ocena.wynik", "poprzednia_ocena.poziom", "poprzednia_ocena.data"} if not poprzednia else ()
    sekcje, braki = pola_arkusza(
        wzor, wartosci, warunki, edytowalne=edytowalne,
        opcjonalne=OPCJONALNE_PRZED_DRUKIEM, pominiete=pominiete,
    )
    if not wynik or not wynik.zapisany:
        braki.insert(0, BrakArkusza(
            id="wynik_okresowy", etykieta="Wynik i terminy z kroku 6",
            komunikat="Zapisz aktualny wynik i terminy w kroku 6.",
        ))

    pola = {p.id: p for s in sekcje for p in s.pola}
    od = wartosci["okres_oceny.od"]
    do = wartosci["okres_oceny.do"]
    rozmowa = wartosci.get("rozmowa_oceniajaca.data")
    for pole_id, komunikat in _sprawdz_kolejnosc(
        od, do, rozmowa, _data(data_oceny), _data(zmiana.data) if koniec_przed_zmiana else None,
    ):
        braki.append(BrakArkusza(id=pole_id, etykieta=pola[pole_id].etykieta, komunikat=komunikat))
    return sekcje, braki


def pola_arkusza(
    wzor: WzorArkusza,
    wartosci: Mapping[str, str | None],
    warunki: Mapping[str, bool],
    *,
    edytowalne: Collection[str],
    opcjonalne: Collection[str] = (),
    pominiete: Collection[str] = (),
) -> tuple[list[SekcjaArkusza], list[BrakArkusza]]:
    """Przygotuj widok uporządkowany według wzoru i wskaż brakujące wartości."""
    sekcje = []
    braki = []
    for sekcja in wzor.sekcje:
        widoczna = all(warunki.get(w, False) for w in sekcja.drukuj_gdy + sekcja.pokaz_gdy)
        pola = []
        for pole in sekcja.pola:
            dotyczy = widoczna and pole.id not in pominiete and all(warunki.get(w, False) for w in pole.pokaz_gdy)
            staly = pole.rodzaj == "tekst_staly"
            podpis = pole.rodzaj == "miejsce_na_podpis_odreczny"
            wartosc = (pole.etykieta if staly else wartosci.get(pole.id)) if dotyczy else None
            wymagane = dotyczy and not (
                staly or podpis or pole.fakultatywne or pole.id in opcjonalne
            )
            wymagane = wymagane and all(warunki.get(w, False) for w in pole.wymagane_gdy)
            if wymagane and not wartosc:
                braki.append(BrakArkusza(
                    id=pole.id, etykieta=pole.etykieta, komunikat=f"Uzupełnij pole „{pole.etykieta}”.",
                ))
            pola.append(PoleArkusza(
                **pole.model_dump(), wartosc=wartosc, widoczne=dotyczy,
                edytowalne=dotyczy and pole.id in edytowalne, wymagane=wymagane,
            ))
        sekcje.append(SekcjaArkusza(tytul=sekcja.tytul, widoczna=widoczna, przypisy=sekcja.przypisy, pola=pola))

    return sekcje, braki


class NiepoprawnePola(ValueError):
    def __init__(self, szczegoly: dict) -> None:
        self.szczegoly = szczegoly
        super().__init__(szczegoly["komunikat"])


def sprawdz_uzupelnienia(pola: Mapping[str, str | None], sekcje: Sequence[SekcjaArkusza]) -> dict[str, str]:
    edytowalne = {p.id: p for s in sekcje for p in s.pola if p.edytowalne}
    if niedozwolone := pola.keys() - edytowalne.keys():
        raise NiepoprawnePola({
            "komunikat": "Te pola pochodzą z procesu, kadr albo nie dotyczą tego arkusza.",
            "pola": sorted(niedozwolone),
        })
    wynik = {}
    for klucz, tekst in pola.items():
        wartosc = (tekst or "").strip()
        if not wartosc:
            continue
        rodzaj = edytowalne[klucz].rodzaj
        limit = 4000 if rodzaj == "tekst_wielowierszowy" else 240
        if len(wartosc) > limit:
            raise NiepoprawnePola({"pole": klucz, "komunikat": f"Maksymalna długość to {limit} znaków."})
        if rodzaj == "data":
            try:
                wartosc = date.fromisoformat(wartosc).isoformat()
            except ValueError as e:
                raise NiepoprawnePola({"pole": klucz, "komunikat": "Wpisz datę w formacie RRRR-MM-DD."}) from e
        if rodzaj == "rok" and (
            len(wartosc) != 4 or not wartosc.isascii() or not wartosc.isdecimal() or wartosc == "0000"
        ):
            raise NiepoprawnePola({"pole": klucz, "komunikat": "Wpisz czterocyfrowy rok."})
        wynik[klucz] = wartosc
    return wynik


def _data(wartosc: date | None) -> str | None:
    return wartosc.isoformat() if wartosc else None


def _pelne_imie(osoba: Pracownik | None) -> str | None:
    return f"{osoba.imie} {osoba.nazwisko}".strip() or None if osoba else None


def _sprawdz_kolejnosc(od, do, rozmowa, data_oceny, zmiana):
    if od and do and do < od:
        yield "okres_oceny.do", "Koniec okresu oceny nie może poprzedzać jego początku."
    if do and zmiana and do >= zmiana:
        yield "okres_oceny.do", "Wpisz ostatni dzień pracy na poprzednim stanowisku przed datą zmiany."
    if rozmowa and ((od and rozmowa < od) or (data_oceny and rozmowa > data_oceny)):
        yield "rozmowa_oceniajaca.data", "Data rozmowy musi przypadać od zapoznania z kryteriami do sporządzenia oceny."
