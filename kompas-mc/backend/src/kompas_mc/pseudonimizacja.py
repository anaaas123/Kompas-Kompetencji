"""Pseudonimizacja kontekstu przed wysłaniem do zewnętrznego modelu."""

from __future__ import annotations

import json
import re
from typing import Any

from .qnt import MockQnt, Pracownik


def _zamien(tekst: str, wzorce: list[tuple[str, str]]) -> str:
    for wartosc, etykieta in wzorce:
        if wartosc:
            if wartosc.isalpha() and len(wartosc) > 3:
                # Imiona w swobodnym opisie mogą być odmienione (Marta → Martą,
                # Piotr → Piotra). Krótki wariant fleksyjny usuwa również te formy.
                rdzen = wartosc[:-1] if wartosc[-1].lower() in "aąeęioóuy" else wartosc
                wzorzec = rf"\b{re.escape(rdzen)}[a-ząćęłńóśźż]{{0,3}}\b"
            else:
                wzorzec = re.escape(wartosc)
            tekst = re.sub(wzorzec, etykieta, tekst, flags=re.IGNORECASE)
    for etykieta in ("Oceniany", "Przełożony", "Osoba", "Komórka"):
        tekst = re.sub(rf"(?:{etykieta}\s+){{1,}}{etykieta}", etykieta, tekst)
    return tekst


class Pseudonimizator:
    """Usuwa identyfikatory wszystkich osób znanych mockowi QNT.

    Osoba, której dotyczy kontekst, otrzymuje etykietę ``Oceniany``, jej
    przełożony ``Przełożony``, a pozostałe osoby ``Osoba``. Nazwy komórek nie są
    potrzebne modelowi i zawsze zmieniają się w ``Komórka``.
    """

    def __init__(self, qnt: MockQnt) -> None:
        self.qnt = qnt

    def _wzorce(self, osoba_id: str) -> list[tuple[str, str]]:
        oceniany = self.qnt.pracownik(osoba_id)
        przelozony_id = oceniany.przelozony_id if oceniany else None
        wzorce: list[tuple[str, str]] = []
        for osoba in self.qnt.pracownicy:
            etykieta = self._etykieta(osoba, osoba_id, przelozony_id)
            wzorce.extend(
                [
                    (f"{osoba.imie} {osoba.nazwisko}", etykieta),
                    (osoba.nazwisko, etykieta),
                    (osoba.imie, etykieta),
                    (osoba.osoba_id, etykieta),
                    (osoba.komorka, "Komórka"),
                ]
            )
        if przelozony_id and self.qnt.pracownik(przelozony_id) is None:
            wzorce.append((przelozony_id, "Przełożony"))
        # Najpierw pełne imiona, nazwiska i długie nazwy komórek, potem ich części.
        return sorted(set(wzorce), key=lambda para: len(para[0]), reverse=True)

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
