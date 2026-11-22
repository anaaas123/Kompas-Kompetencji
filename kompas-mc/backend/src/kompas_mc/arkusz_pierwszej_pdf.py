"""Nadruk wartości pierwszej oceny na załączniku nr 2 do rozporządzenia z 2015 r."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from typing import Any

from .wzor_druk import MIN_ROZMIAR, Krzyzyk, Pole, _font, _wiersze, wypelnij


def _dane_osoby(prefiks: str, dolne_krawedzie: tuple[int, ...]) -> dict[str, Pole]:
    kolumna = ("imie", "nazwisko", "komorka_organizacyjna", "stanowisko")
    return {
        f"{prefiks}.{klucz}": Pole(0, 228, y, 537, y + 13, 9.5)
        for klucz, y in zip(kolumna, dolne_krawedzie, strict=True)
    }


def _potwierdzenie(prefiks: str, strona: int, y: float) -> dict[str, Pole]:
    # Wolne miejsce pomiędzy poprzednim wierszem a kropkami. Podpis jest odręczny.
    if strona == 0:
        return {
            f"{prefiks}.miejscowosc": Pole(0, 58, y, 150, y + 10, 8),
            f"{prefiks}.data": Pole(0, 174, y, 266, y + 10, 8),
        }
    return {
        f"{prefiks}.miejscowosc": Pole(strona, 59, y, 150, y + 10, 8),
        f"{prefiks}.data": Pole(strona, 155, y, 224, y + 10, 8),
        f"{prefiks}.imie_nazwisko_lub_pieczatka": Pole(strona, 251, y, 408, y + 10, 8),
    }


# Punkty PDF względem lewego dolnego rogu. Daty przedziałów są nad legendą „od … – do …”.
_POLA = {
    "nazwa_urzedu": Pole(0, 228, 641, 537, 654, 9.5),
    **_dane_osoby("oceniany", (605, 590, 575, 559)),
    "oceniany.data_nawiazania_stosunku_pracy": Pole(0, 303, 543, 490, 556, 9.5),
    **_dane_osoby("bezposredni_przelozony", (506, 491, 476, 460)),
    **_dane_osoby("kierujacy_komorka", (425, 409, 394, 379)),
    "rozmowa_wstepna.data": Pole(0, 303, 323, 490, 340),
    "termin_sprawozdania.od": Pole(0, 428, 300, 479, 316, 9.5, True),
    "termin_sprawozdania.do": Pole(0, 487, 300, 537, 316, 9.5, True),
    "okres_pierwszej_oceny.od": Pole(0, 428, 272, 479, 285, 9.5, True),
    "okres_pierwszej_oceny.do": Pole(0, 487, 272, 537, 285, 9.5, True),
    **_potwierdzenie("potwierdzenie_rozmowy_wstepnej.przelozony", 0, 212),
    **_potwierdzenie("potwierdzenie_rozmowy_wstepnej.oceniany", 0, 178),
    "rozmowa_oceniajaca.data": Pole(1, 304, 732, 491, 750),
    **_potwierdzenie("potwierdzenie_rozmowy_oceniajacej.przelozony", 1, 697),
    **_potwierdzenie("potwierdzenie_rozmowy_oceniajacej.oceniany", 1, 655),
    "ocena_laczna": Pole(1, 327, 451, 537, 465, 10, True),
    "uzasadnienie": Pole(2, 58, 588, 537, 747),
    "wnioski_rozwojowe": Pole(2, 58, 463, 537, 541),
    **_potwierdzenie("dokonanie_oceny.przelozony", 2, 410),
    **_potwierdzenie("dokonanie_oceny.kierujacy", 2, 368),
    **_potwierdzenie("zapoznanie.oceniany", 2, 288),
}

_KRATKI = {
    **{
        f"ocena_czastkowa.{nr}": {
            "3": Krzyzyk(1, 271.5, y), "5": Krzyzyk(1, 379.5, y), "7": Krzyzyk(1, 487.5, y),
        }
        for nr, y in enumerate((547, 529, 511, 493, 476), 1)
    },
    "egzamin": {"TAK": Krzyzyk(1, 169, 401), "NIE": Krzyzyk(1, 315, 401), "NIE DOTYCZY": Krzyzyk(1, 514, 401)},
    "sprawozdanie_w_terminie": {"TAK": Krzyzyk(1, 272, 357.5), "NIE": Krzyzyk(1, 514, 357.5)},
    "wynik": {"POZYTYWNA": Krzyzyk(1, 272, 314.5), "NEGATYWNA": Krzyzyk(1, 514, 314.5)},
}


def _wydruk(
    wzor: Mapping[str, Any], wartosci: Mapping[str, str | None], *, drukuj_wnioski: bool, strony: Sequence[int],
) -> bytes:
    wpisy = []
    nazwy_pol = {}
    krzyzyki = []
    for sekcja in wzor["sekcje"]:
        for definicja in sekcja["pola"]:
            klucz = definicja["id"]
            wartosc = wartosci.get(klucz)
            if not wartosc or (klucz == "wnioski_rozwojowe" and not drukuj_wnioski):
                continue
            if klucz in _KRATKI:
                kratka = _KRATKI[klucz].get(wartosc)
                if kratka and kratka.strona in strony:
                    krzyzyki.append(kratka)
                continue
            pole = _POLA.get(klucz)
            if pole and pole.strona in strony:
                if definicja["rodzaj"] == "data":
                    wartosc = date.fromisoformat(wartosc).strftime("%d.%m.%Y")
                if klucz.endswith(".komorka_organizacyjna"):
                    wpisy.extend(_wpisy_komorki(pole, wartosc))
                else:
                    wpisy.append((pole, wartosc))
                nazwy_pol[pole] = definicja["etykieta"]
    return wypelnij("arkusz_pierwszej.pdf", wpisy, krzyzyki, strony=strony, nazwy_pol=nazwy_pol)


def _wpisy_komorki(pole: Pole, nazwa: str) -> list[tuple[Pole, str]]:
    # Długi wpis „Departament / Wydział” potrzebuje dwóch linii w wierszu o wysokości 15 pt.
    # Zwykła interlinia wzor_druk wynosi 8,4 pt przy czcionce 7 pt.
    linie = _wiersze(nazwa, _font(), MIN_ROZMIAR, pole.x1 - pole.x0)
    if len(linie) != 2:
        return [(pole, nazwa)]
    gora = replace(pole, y0=pole.y0 + 6.5, y1=pole.y1 + 0.5, rozmiar=MIN_ROZMIAR)
    dol = replace(pole, y0=pole.y0 - 0.5, y1=pole.y0 + 6.5, rozmiar=MIN_ROZMIAR)
    return [(gora, linie[0]), (dol, linie[1])]


def arkusz_pierwszej_oceny_pdf(
    wzor: Mapping[str, Any],
    wartosci: Mapping[str, str | None],
    *,
    drukuj_wnioski: bool,
    wersja: str,
) -> bytes:
    """Pełny arkusz wraz z potwierdzeniem zapoznania się z oceną."""
    return _wydruk(wzor, wartosci, drukuj_wnioski=drukuj_wnioski, strony=(0, 1, 2))


def rozmowa_wstepna_pdf(wzor: Mapping[str, Any], wartosci: Mapping[str, str | None], *, wersja: str) -> bytes:
    """Pierwsza strona arkusza do podpisu po rozmowie wstępnej."""
    return _wydruk(wzor, wartosci, drukuj_wnioski=False, strony=(0,))
