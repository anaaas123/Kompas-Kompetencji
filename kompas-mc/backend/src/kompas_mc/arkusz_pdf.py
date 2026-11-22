"""Wydruk arkuszy oceny okresowej B i C według załączników nr 3 i 4."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.textsplit import wordSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

from .wzor_druk import INTERLINIA, MIN_ROZMIAR, Krzyzyk, _font, _wiersze, wypelnij
from .wzor_druk import Pole as PoleWzoru

_LITERY = {"okresowa_b": "B", "okresowa_c": "C"}


def _pola_wydruku(litera: str) -> dict[str, PoleWzoru]:
    """Prostokąty nadruku wewnątrz komórek obu załączników, w punktach PDF od dołu."""
    b = litera == "B"
    pola = {}

    def wiersz(klucz, strona, lewa, prawa, dol, wys=12, rozmiar=9, srodek=False):
        pola[klucz] = PoleWzoru(strona, lewa, dol, prawa, dol + wys, rozmiar, srodek)

    def osoba(prefiks, strona, lewa, prawa, doly):
        for pole, dol in zip(("imie", "nazwisko", "komorka_organizacyjna", "stanowisko"), doly, strict=True):
            wiersz(f"{prefiks}.{pole}", strona, lewa, prawa, dol)

    def przy_podpisie(prefiks, strona, dol, poczatki):
        # Nad liniami kropek. Ostatnia linia formularza służy wyłącznie do odręcznego podpisu.
        for pole, x in zip(("miejscowosc", "data", "imie_nazwisko_lub_pieczatka"), poczatki):
            wiersz(f"{prefiks}.{pole}", strona, x, x + 92, dol, 10, 8, True)

    wiersz("nazwa_urzedu", 0, 235, 519, 616 if b else 618)
    osoba("oceniany", 0, 235, 521, (578, 563, 548, 533) if b else (582, 567, 551, 536))
    osoba("oceniajacy.czesc_I", 0, 235, 521, (495, 480, 465, 450) if b else (500, 485, 469, 454))
    for nr, dol in enumerate((384, 369, 353) if b else (390, 374, 359), 1):
        wiersz(f"kryterium_dodatkowe.{nr}", 0, 301, 519, dol)
    wiersz("termin_sporzadzenia_oceny", 0, 414, 519, 338 if b else 344)
    poczatki = (101, 252) if b else (103, 253)
    przy_podpisie("potwierdzenie_kryteriow.oceniajacy", 0, 236 if b else 252, poczatki)
    przy_podpisie("potwierdzenie_kryteriow.oceniany", 0, 187.5 if b else 203.5, poczatki)

    wiersz("rozmowa_oceniajaca.data", 1, 335, 518, 726 if b else 724)
    wiersz("okres_oceny.od", 1, 308, 398, 706 if b else 704, 10, 8.5, True)
    wiersz("okres_oceny.do", 1, 432, 519, 706 if b else 704, 10, 8.5, True)
    for nr, dol in enumerate((446, 423, 399) if b else (445, 422, 398), 1):
        wiersz(f"ocena_dodatkowa.{nr}.kryterium", 1, 77, 281, dol)
    wiersz("srednia", 1, 432, 519, 375 if b else 374, srodek=True)

    wiersz("uzasadnienie", 2, 78, 518, 589 if b else 590, 159, 10)
    wiersz("wnioski_iprz", 2, 78, 518, 480 if b else 482, 77, 10)
    dol = 439 if b else 443
    wiersz("poprzednia_ocena.wynik", 2, 116, 171, dol)
    wiersz("poprzednia_ocena.poziom", 2, 222, 332, dol)
    wiersz("poprzednia_ocena.data", 2, 465, 519, dol, srodek=True)
    osoba("oceniajacy.czesc_II", 2, 234, 520, (361, 346, 331, 316) if b else (370, 355, 339, 324))
    przy_podpisie("dokonanie_oceny.oceniajacy", 2, 302.5 if b else 311, (101, 251) if b else (103, 253))
    przy_podpisie("zapoznanie.oceniany", 2, 233 if b else 242.5, (82, 195, 307) if b else (84, 196, 309))

    doly = (659, 644, 629, 614, 598) if b else (655, 640, 625, 610, 595)
    for pole, dol, x in zip(
        ("imie", "nazwisko", "rok_mianowania", "stopien_sluzbowy", "data_przyznania_stopnia"),
        doly, (235, 235, 266, 235, 282), strict=True,
    ):
        wiersz(f"urzednik.{pole}", 3, x, 519, dol)
    wiersz("wniosek_o_stopien.imie_nazwisko", 3, 79, 500, 515.5 if b else 514, srodek=True)
    # Krótki wykropkowany fragment na początku ostatniego wiersza zdania.
    wiersz("wniosek_o_stopien.stopien", 3, 79, 101, 473.3 if b else 471.9, 8, 7, True)
    wiersz("wniosek_o_stopien.umotywowanie", 3, 78, 518, 219 if b else 228, 229 if b else 219, 10)
    przy_podpisie("wniosek_o_stopien.oceniajacy", 3, 202.8 if b else 211.3,
                  (88, 207, 321) if b else (94, 227, 347))
    return pola


def _kratki_wydruku(litera: str, wzor: Mapping[str, Any]) -> dict[str, dict[str, Krzyzyk]]:
    """Środki komórek w skali 1/3/5/7/9 oraz kratek pojedynczego wyboru."""
    b = litera == "B"
    kolumny = (308, 356, 403, 451, 498) if b else (310, 357, 405, 452, 500)
    obowiazkowe = (597, 574, 550, 527, 503) if b else (596, 573, 550, 526, 503)
    dodatkowe = (452, 429, 405) if b else (452, 428, 405)
    kratki = {}

    def skala(y):
        return {str(pkt): Krzyzyk(1, x, y) for pkt, x in zip(wzor["zakres_punktow"], kolumny, strict=True)}

    for nr, y in enumerate(obowiazkowe, 1):
        kratki[f"ocena_obowiazkowa.{nr}"] = skala(y)
    for nr, y in enumerate(dodatkowe, 1):
        kratki[f"ocena_dodatkowa.{nr}.punkty"] = skala(y)

    poziomy = next(p["warianty"] for s in wzor["sekcje"] for p in s["pola"] if p["id"] == "poziom")
    wiersze = (306, 291, 275, 260, 244) if b else (308, 293, 277, 262, 246)
    kratki["poziom"] = {poziom: Krzyzyk(1, 116 if b else 118, y) for poziom, y in zip(poziomy, wiersze, strict=True)}
    kratki["wynik"] = {
        "POZYTYWNA": Krzyzyk(1, 318 if b else 319, 220 if b else 222),
        "NEGATYWNA": Krzyzyk(1, 504 if b else 505, 220 if b else 222),
    }
    kratki["wniosek_o_stopien.status"] = {
        status: Krzyzyk(2, x, 405 if b else 412)
        for status, x in zip(("TAK", "NIE", "NIE DOTYCZY"), (165, 263, 511) if b else (166, 264, 512), strict=True)
    }
    return kratki


def _wpisy_osoby(pole: PoleWzoru, tekst: str) -> list[tuple[PoleWzoru, str]]:
    # Wiersz danych osobowych ma 15 pt. Dwie linie po 7 pt mieszczą się w nim
    # z interlinią 7 pt, np. przy pełnej nazwie departamentu i wydziału z QNT.
    linie = _wiersze(tekst, _font(), MIN_ROZMIAR, pole.x1 - pole.x0)
    if len(linie) != 2:
        return [(pole, tekst)]
    return [
        (replace(pole, y0=y, y1=y + 7, rozmiar=MIN_ROZMIAR), linia)
        for linia, y in zip(linie, (pole.y0 + 6.5, pole.y0 - 0.5), strict=True)
    ]


def _wiersze_opisu(tekst: str, font: str, rozmiar: float, szerokosc: float) -> list[str]:
    linie = []
    for linia in _wiersze(tekst, font, rozmiar, szerokosc):
        if stringWidth(linia, font, rozmiar) > szerokosc:
            # Samo łamanie na spacjach nie dzieli np. długiego identyfikatora sprawy.
            linie.extend(fragment for _, fragment in wordSplit(linia, szerokosc, font, rozmiar))
        else:
            linie.append(linia)
    return linie


def _wpis_opisu(pole: PoleWzoru, tekst: str) -> tuple[PoleWzoru, str]:
    font = _font()
    szerokosc = pole.x1 - pole.x0
    linie = _wiersze_opisu(tekst, font, MIN_ROZMIAR, szerokosc)
    pojemnosc = int((pole.y1 - pole.y0) // (MIN_ROZMIAR * INTERLINIA))
    if len(linie) <= pojemnosc:
        if any(stringWidth(w, font, pole.rozmiar) > szerokosc for w in tekst.split()):
            return replace(pole, rozmiar=MIN_ROZMIAR), "\n".join(linie)
        return pole, tekst

    # wypelnij() dopisuje odsyłacz na dole pola, a kontynuację składa czcionką
    # 10 pt od x=70. Zostawiamy wiersz na odsyłacz i łamiemy resztę do marginesu A4.
    koniec = pojemnosc - 1
    dalsze = [w for linia in linie[koniec:] for w in _wiersze_opisu(linia, font, 10, A4[0] - 140)]
    return pole, "\n".join([*linie[:koniec], "", *dalsze])


def arkusz_pdf(
    wzor: Mapping[str, Any],
    wartosci: Mapping[str, str | None],
    *,
    drukuj_czesc_iii: bool,
    wersja: str,
    tylko_czesc_i: bool = False,
) -> bytes:
    """Nadrukuj dane na wybranych stronach załącznika nr 3 (B) lub 4 (C)."""
    litera = _LITERY[wzor["id"]]
    strony = (0,) if tylko_czesc_i else range(4 if drukuj_czesc_iii else 3)
    pola = _pola_wydruku(litera)
    kratki = _kratki_wydruku(litera, wzor)
    wpisy, zaznaczenia, nazwy = [], [], {}
    for sekcja in wzor["sekcje"]:
        for definicja in sekcja["pola"]:
            klucz = definicja["id"]
            tekst = wartosci.get(klucz)
            if not tekst:
                continue
            if klucz in pola and pola[klucz].strona in strony:
                if definicja["rodzaj"] == "data":
                    tekst = date.fromisoformat(tekst).strftime("%d.%m.%Y")
                if klucz.startswith(("oceniany.", "oceniajacy.")):
                    wpisy.extend(_wpisy_osoby(pola[klucz], tekst))
                elif definicja["rodzaj"] == "tekst_wielowierszowy":
                    wpisy.append(_wpis_opisu(pola[klucz], tekst))
                else:
                    wpisy.append((pola[klucz], tekst))
                nazwy[pola[klucz]] = definicja["etykieta"]
            elif klucz in kratki and tekst in kratki[klucz]:
                zaznaczenia.append(kratki[klucz][tekst])
    return wypelnij(f"arkusz_{litera}.pdf", wpisy, zaznaczenia, strony=strony, nazwy_pol=nazwy)
