"""Pseudonimizacja kontekstu przed wysłaniem do zewnętrznego modelu."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from .qnt import MockQnt, Pracownik

_SAMOGLOSKI = "aąeęioóuy"
_DWUZNAKI = ("rz", "sz", "cz", "ch", "dz", "dż", "dź")
# Wymiana ostatniej spółgłoski tematu przed końcówką: Marta → Marcie, Piotr → Piotrze,
# Paweł → Pawle, Dominika → Dominice, Wiśniewski → Wiśniewscy, Staś → Stasia.
_WYMIANY = {
    "t": "(?:t|ci)", "d": "(?:d|dzi)", "r": "(?:r|rz)", "ł": "(?:ł|l)", "k": "(?:k|c)",
    "g": "(?:g|dz)", "ś": "(?:ś|si)", "ń": "(?:ń|ni)", "ź": "(?:ź|zi)", "ć": "(?:ć|ci)",
}
# Końcówki przypadków rzeczownika i przymiotnika. Lista zamknięta zamiast „dowolne litery”,
# żeby „Marta” nie zabierała słowa „martwy”, a „Julia” imienia „Julian”.
_KONCOWKI = (
    "(?:iego|iemu|owie|owej|ową|owa|ego|emu|owi|iem|iej|ich|ych|ami|ach|imi|ymi"
    "|ie|em|om|ów|ej|ym|im|a|ą|e|ę|i|o|u|y)"
)
_ODSTEP = r"[\s\-–]+"  # człony imienia i nazwiska: spacja albo łącznik
_KOLEJNOSC_ETYKIET = ("Oceniany", "Przełożony", "Osoba")


def _z_wymiana(temat: str) -> str:
    if not temat.endswith(_DWUZNAKI) and temat[-1] in _WYMIANY:
        return re.escape(temat[:-1]) + _WYMIANY[temat[-1]]
    return re.escape(temat)


def _wzorzec_odmiany(czlon: str) -> str:
    """Wzorzec jednego członu imienia albo nazwiska w dowolnym przypadku (małymi literami).

    Dąbrowski → Dąbrowskiego, Dąbrowskiemu, Dąbrowskim; Marta → Marty, Marcie, Martą;
    Paweł → Pawła, Pawłowi, Pawłem, Pawle („e” ruchome i wymiana ł → l); Kacper → Kacprze.
    Zdrobnień („Pawełek”) i przymiotników od nazwisk wzorzec nie obejmuje.
    """
    maly = czlon.lower()
    if maly[-1] in _SAMOGLOSKI:
        # Temat bez końcowej samogłoski zawsze ma końcówkę: „Ann” ani „Dąbrowsk” nie występują same.
        return _z_wymiana(maly[:-1]) + _KONCOWKI
    ruchome = re.fullmatch(rf"(.*[^{_SAMOGLOSKI}])(ie|e)([^{_SAMOGLOSKI}]+)", maly)
    if ruchome:
        poczatek, e, koniec = ruchome.groups()
        temat = re.escape(poczatek) + f"(?:{e})?" + _z_wymiana(koniec)
    else:
        temat = _z_wymiana(maly)
    return temat + _KONCOWKI + "?"


def _czlony(tekst: str) -> list[str]:
    return [c for c in re.split(_ODSTEP, tekst.strip()) if c]


def _wzorzec_nazwy(czlony: list[str]) -> str | None:
    """Wzorzec ciągu członów (np. imię i nazwisko dwuczłonowe) rozdzielonych spacją albo łącznikiem."""
    if not czlony or not all(len(c) > 1 and c.isalpha() for c in czlony):
        return None
    return r"\b" + _ODSTEP.join(_wzorzec_odmiany(c) for c in czlony) + r"\b"


def _tylko_wielka_litera(wzorzec: str, czlon: str) -> str:
    """Krótki człon nazwiska („Maj”) bywa zwykłym słowem („maja”), więc sam liczy się tylko z wielkiej litery."""
    return r"\b" + re.escape(czlon[0].upper()) + "(?i:" + wzorzec[len(r"\b") + 1 :] + ")"


def _zamien(tekst: str, wzorce: list[tuple[re.Pattern[str], str]]) -> str:
    for wzorzec, etykieta in wzorce:
        tekst = wzorzec.sub(etykieta, tekst)
    for etykieta in ("Oceniany", "Przełożony", "Osoba", "Komórka"):
        tekst = re.sub(rf"(?:{etykieta}\s+){{1,}}{etykieta}", etykieta, tekst)
    return tekst


class Pseudonimizator:
    """Usuwa identyfikatory wszystkich osób znanych mockowi QNT.

    Osoba, której dotyczy kontekst, otrzymuje etykietę ``Oceniany``, jej
    przełożony ``Przełożony``, a pozostałe osoby ``Osoba``. Nazwy komórek nie są
    potrzebne modelowi i zawsze zmieniają się w ``Komórka``.

    Imiona i nazwiska są rozpoznawane także w odmianie, małymi literami, w kolejności
    „nazwisko imię” oraz gdy człony nazwiska dzieli spacja zamiast łącznika. Sam człon nazwiska
    („Dąbrowskiego” bez „-Demo”) też jest zastępowany, chyba że nosi go ponad połowa osób:
    taki człon nie wskazuje nikogo, a bywa zwykłym słowem.
    """

    def __init__(self, qnt: MockQnt) -> None:
        self.qnt = qnt
        self._wzorce_osoby: dict[str, list[tuple[re.Pattern[str], str]]] = {}

    def _wzorce(self, osoba_id: str) -> list[tuple[re.Pattern[str], str]]:
        if osoba_id not in self._wzorce_osoby:
            self._wzorce_osoby[osoba_id] = self._zbuduj_wzorce(osoba_id)
        return self._wzorce_osoby[osoba_id]

    def _zbuduj_wzorce(self, osoba_id: str) -> list[tuple[re.Pattern[str], str]]:
        oceniany = self.qnt.pracownik(osoba_id)
        przelozony_id = oceniany.przelozony_id if oceniany else None
        osoby = [(o, self._etykieta(o, osoba_id, przelozony_id)) for o in self.qnt.pracownicy]

        # (długość źródła, wzorzec, flagi) → etykieta; przy wspólnym imieniu wygrywa ważniejsza etykieta.
        wpisy: dict[tuple[int, str, int], str] = {}

        def dodaj(zrodlo: str, wzorzec: str | None, etykieta: str, flagi: int = re.IGNORECASE) -> None:
            if not zrodlo:
                return
            klucz = (len(zrodlo), wzorzec or re.escape(zrodlo), flagi)
            poprzednia = wpisy.get(klucz)
            if poprzednia is None or _KOLEJNOSC_ETYKIET.index(etykieta) < _KOLEJNOSC_ETYKIET.index(poprzednia):
                wpisy[klucz] = etykieta

        nosiciele = Counter(c.lower() for o, _ in osoby for c in set(_czlony(o.nazwisko)))
        for osoba, etykieta in osoby:
            imie, nazwisko = _czlony(osoba.imie), _czlony(osoba.nazwisko)
            dodaj(f"{osoba.imie} {osoba.nazwisko}", _wzorzec_nazwy(imie + nazwisko), etykieta)
            dodaj(osoba.nazwisko, _wzorzec_nazwy(nazwisko), etykieta)
            dodaj(osoba.imie, _wzorzec_nazwy(imie), etykieta)
            if len(nazwisko) > 1:
                for czlon in nazwisko:
                    wzorzec = _wzorzec_nazwy([czlon])
                    wspolny = nosiciele[czlon.lower()] > 1 and nosiciele[czlon.lower()] * 2 > len(osoby)
                    if wzorzec is None or wspolny:
                        continue
                    if len(czlon) <= 3:
                        dodaj(czlon, _tylko_wielka_litera(wzorzec, czlon), etykieta, 0)
                    else:
                        dodaj(czlon, wzorzec, etykieta)
            dodaj(osoba.osoba_id, None, etykieta)
        komorki = {(len(o.komorka), re.escape(o.komorka), re.IGNORECASE) for o, _ in osoby if o.komorka}
        if przelozony_id and self.qnt.pracownik(przelozony_id) is None:
            dodaj(przelozony_id, None, "Przełożony")

        wszystkie = [(k, e) for k, e in wpisy.items()] + [(k, "Komórka") for k in komorki]
        # Najpierw pełne imiona, nazwiska i długie nazwy komórek, potem ich części.
        wszystkie.sort(key=lambda para: (-para[0][0], para[0][1]))
        return [(re.compile(wzorzec, flagi), etykieta) for (_, wzorzec, flagi), etykieta in wszystkie]

    @staticmethod
    def _etykieta(osoba: Pracownik, osoba_id: str, przelozony_id: str | None) -> str:
        if osoba.osoba_id == osoba_id:
            return "Oceniany"
        if osoba.osoba_id == przelozony_id:
            return "Przełożony"
        return "Osoba"

    def tekst(self, tekst: str, osoba_id: str) -> str:
        return _zamien(tekst, self._wzorce(osoba_id))

    def dane(self, dane: Any, osoba_id: str) -> Any:
        """Zwróć strukturę JSON bez danych identyfikujących."""
        if isinstance(dane, str):
            return self.tekst(dane, osoba_id)
        if isinstance(dane, dict):
            return {klucz: self.dane(wartosc, osoba_id) for klucz, wartosc in dane.items()}
        if isinstance(dane, (list, tuple)):
            return [self.dane(wartosc, osoba_id) for wartosc in dane]
        return dane

    def json(self, dane: Any, osoba_id: str) -> str:
        return json.dumps(self.dane(dane, osoba_id), ensure_ascii=False, sort_keys=True)
