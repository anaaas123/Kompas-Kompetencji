"""Położenie nadruku względem oryginalnych komórek załącznika nr 2."""

import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta

import pytest

from kompas_mc.arkusz_pierwszej_pdf import (
    arkusz_pierwszej_oceny_pdf,
    rozmowa_wstepna_pdf,
)
from kompas_mc.wzor_druk import WZORY


def _slowa(pdf):
    xml = subprocess.run(["pdftotext", "-bbox", "-", "-"], input=pdf, capture_output=True, check=True).stdout
    strony = []
    for strona in ET.fromstring(xml).findall(".//{*}page"):
        wys = float(strona.attrib["height"])
        strony.append(Counter(
            (w.text, (float(w.get("xMin")), wys - float(w.get("yMax")),
                      float(w.get("xMax")), wys - float(w.get("yMin"))))
            for w in strona.findall(".//{*}word")
        ))
    return strony


def _zawiera(pole, slowo):
    return pole[0] <= slowo[0] and pole[1] <= slowo[1] and slowo[2] <= pole[2] and slowo[3] <= pole[3]


def _nachodzi(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _komorki_wzoru():
    # Granice komórek odczytane z linii PDF, niezależne od marginesów generatora.
    pola = {
        "nazwa_urzedu": (0, (224, 640, 540, 655)),
        "oceniany.data_nawiazania_stosunku_pracy": (0, (300, 542, 540, 557)),
        "rozmowa_wstepna.data": (0, (300, 322, 540, 342)),
        "rozmowa_oceniajaca.data": (1, (301, 730, 541, 753)),
        "ocena_laczna": (1, (324, 450, 541, 466)),
        "uzasadnienie": (2, (54, 584, 541, 751)),
        "wnioski_rozwojowe": (2, (54, 459, 541, 545)),
    }
    for osoba, dol in [
        ("oceniany", (604, 589, 574, 558)),
        ("bezposredni_przelozony", (505, 490, 475, 459)),
        ("kierujacy_komorka", (424, 408, 393, 378)),
    ]:
        for pole, y in zip(("imie", "nazwisko", "komorka_organizacyjna", "stanowisko"), dol, strict=True):
            pola[f"{osoba}.{pole}"] = (0, (224, y, 540, y + 15))
    for pole, y0, y1 in [("termin_sprawozdania", 287, 320), ("okres_pierwszej_oceny", 262, 286)]:
        pola[f"{pole}.od"] = (0, (428, y0, 481, y1))
        pola[f"{pole}.do"] = (0, (486, y0, 540, y1))
    for osoba, strona, dol, gora in [
        ("potwierdzenie_rozmowy_wstepnej.przelozony", 0, 202, 222.4),
        ("potwierdzenie_rozmowy_wstepnej.oceniany", 0, 168, 188.5),
        ("potwierdzenie_rozmowy_oceniajacej.przelozony", 1, 687, 707.2),
        ("potwierdzenie_rozmowy_oceniajacej.oceniany", 1, 645, 665.2),
        ("dokonanie_oceny.przelozony", 2, 400, 420.4),
        ("dokonanie_oceny.kierujacy", 2, 358, 378.4),
        ("zapoznanie.oceniany", 2, 278, 298.4),
    ]:
        kolumny = [("miejscowosc", 58, 153), ("data", 154, 246), ("imie_nazwisko_lub_pieczatka", 250, 416)]
        if strona == 0:
            kolumny = [("miejscowosc", 58, 171), ("data", 173, 327)]
        for pole, lewa, prawa in kolumny:
            pola[f"{osoba}.{pole}"] = (strona, (lewa, dol, prawa, gora))
    return pola


@pytest.mark.parametrize("wariant", [0, 1, 2])
def test_nadruk_we_wlasciwych_komorkach(ustawienia, wariant):
    wzor = next(w for w in json.loads(ustawienia.wzory_arkuszy.read_text())["wzory"] if w["id"] == "pierwsza")
    komorki = _komorki_wzoru()
    wartosci = {}
    oczekiwane = [[] for _ in range(3)]
    for sekcja in wzor["sekcje"]:
        for pole in sekcja["pola"]:
            klucz = pole["id"]
            if klucz not in komorki:
                assert pole["rodzaj"] in {"tekst_staly", "miejsce_na_podpis_odreczny", "wybor", "wybor_punktow"}
                continue
            strona, ramka = komorki[klucz]
            numer = len(wartosci) + 1
            tekst = wartosc = f"Wpis{numer}"
            if pole["rodzaj"] == "data":
                dzien = date(2026, 1, 1) + timedelta(days=numer)
                tekst, wartosc = dzien.strftime("%d.%m.%Y"), dzien.isoformat()
            elif klucz == "oceniany.komorka_organizacyjna":
                tekst = wartosc = (
                    "Departament Cyberbezpieczeństwa / Wydział Zarządzania Kryzysowego, "
                    "Spraw Obronnych i Cyberbezpieczeństwa"
                )
            wartosci[klucz] = wartosc
            if klucz != "wnioski_rozwojowe" or wariant == 0:
                oczekiwane[strona].extend((slowo, ramka) for slowo in tekst.split())
    # Trzy przebiegi pokrywają każdą z 15 kratek skali oraz wszystkie warianty części V.
    kolumny = [(218, 325), (326, 433), (434, 541)]
    for nr, (dol, gora) in enumerate([(539, 555), (520, 538), (502, 520), (485, 501), (468, 484)], 1):
        indeks = (nr + wariant) % 3
        lewa, prawa = kolumny[indeks]
        wartosci[f"ocena_czastkowa.{nr}"] = ("3", "5", "7")[indeks]
        oczekiwane[1].append(("X", (lewa, dol, prawa, gora)))
    for klucz, opcje, kolumny, dol, gora in [
        ("egzamin", ["TAK", "NIE", "NIE DOTYCZY"], [(143, 196), (288, 343), (488, 541)], 393, 409),
        ("sprawozdanie_w_terminie", ["TAK", "NIE"], [(246, 299), (488, 541)], 350, 366),
        ("wynik", ["POZYTYWNA", "NEGATYWNA"], [(246, 299), (488, 541)], 306, 323),
    ]:
        indeks = wariant % len(opcje)
        wartosci[klucz] = opcje[indeks]
        lewa, prawa = kolumny[indeks]
        oczekiwane[1].append(("X", (lewa, dol, prawa, gora)))

    tlo = _slowa((WZORY / "arkusz_pierwszej.pdf").read_bytes())
    wydruk = _slowa(arkusz_pierwszej_oceny_pdf(wzor, wartosci, drukuj_wnioski=wariant == 0, wersja="test"))
    for oryginal, strona, pola in zip(tlo, wydruk, oczekiwane, strict=True):
        assert oryginal <= strona
        nadruk = list((strona - oryginal).elements())
        for tekst, ramka in pola:
            trafienia = [(w, box) for w, box in nadruk if w == tekst and _zawiera(ramka, box)]
            assert trafienia, (tekst, ramka)
            wpis = trafienia[0]
            assert not any(_nachodzi(wpis[1], box) for _, box in oryginal), wpis
            nadruk.remove(wpis)
            assert not any(_nachodzi(wpis[1], box) for _, box in nadruk), wpis
        assert not nadruk
    assert _slowa(rozmowa_wstepna_pdf(wzor, wartosci, wersja="test")) == wydruk[:1]
