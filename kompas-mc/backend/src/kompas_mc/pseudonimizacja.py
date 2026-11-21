"""Pseudonimizacja danych wysyłanych do zewnętrznego modelu (#6).

Do dostawców ``na_zywo`` działających poza maszyną (``anthropic``, ``openai_zgodny``)
nie trafiają dane identyfikujące osoby z mocka QNT: imię, nazwisko (także w formach
odmienionych), ``osoba_id`` ani nazwa komórki.

Dwa poziomy ochrony:

* ``Pseudonimizator.pseudonimizuj(tekst, oceniany_id)`` – miejsce budujące zapytanie
  z kontekstem osoby (czat kroku 6, podpowiedzi celów) zamienia osobę ocenianą na
  „Oceniany”, jej przełożonego na „Przełożony”, a pozostałe osoby na „[osoba]”;
* ``chron_zewnetrznych(dostawcy, ...)`` – bezpiecznik w łańcuchu dostawców: każde
  pytanie wysyłane poza maszynę jest dodatkowo oczyszczane (bez ról).

Fragmenty korpusu nie są zmieniane: to teksty korpusu MC bez danych osób z QNT, a ich
dosłowny tekst jest potrzebny do walidacji cytatów. Kontekst osoby należy więc
przekazywać w ``Zapytanie.pytanie``, nie we fragmentach.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from kompas_core.llm import LlmProvider, Odpowiedz, Zapytanie

from .qnt import MockQnt, Pracownik

ZEWNETRZNI = frozenset({"anthropic", "openai_zgodny"})
"""Nazwy dostawców, którzy wysyłają zapytanie poza maszynę."""

DOMYSLNE_PSEUDONIMY = {
    "oceniany": "Oceniany",
    "przelozony": "Przełożony",
    "inna_osoba": "[osoba]",
    "komorka": "[komórka]",
    "osoba_id": "[id]",
}

_SAMOGLOSKI_KONCOWE = re.compile(r"[aeiouyąęó]+$")


def _wzorzec_slowa(slowo: str) -> str:
    """Rdzeń słowa z miejscem na polską końcówkę: Anna → Annie, Zielińska →
    Zielińskiej, Paweł → Pawła, Kacper → Kacpra, Nowak → Nowakiem."""
    rdzen = _SAMOGLOSKI_KONCOWE.sub("", slowo)
    if rdzen == slowo and len(slowo) >= 3 and slowo[-2] == "e":
        wzorzec = re.escape(slowo[:-2]) + "e?" + re.escape(slowo[-1])  # e ruchome
    else:
        wzorzec = re.escape(rdzen or slowo)
    return wzorzec + r"\w{0,4}"


def _calosc(wzorzec: str) -> re.Pattern[str]:
    # Bez IGNORECASE: imiona i nazwiska piszemy wielką literą, a „maj” czy „marta”
    # małą literą to zwykłe słowa.
    return re.compile(rf"(?<!\w){wzorzec}(?!\w)")


class Pseudonimizator:
    def __init__(
        self,
        qnt: MockQnt,
        pseudonimy: Mapping[str, str] | None = None,
        pomijane_czlony: Iterable[str] = ("Demo",),
    ) -> None:
        self.qnt = qnt
        self.pseudonimy = {**DOMYSLNE_PSEUDONIMY, **(pseudonimy or {})}
        pomijane = set(pomijane_czlony)

        # Kolejność ma znaczenie: najpierw pełne imię i nazwisko, potem samo nazwisko,
        # na końcu samo imię – żeby z „Anna Zielińska” nie zostało „Oceniany Oceniany”.
        pelne: list[tuple[re.Pattern[str], str]] = []
        nazwiska: list[tuple[re.Pattern[str], str]] = []
        imiona: list[tuple[re.Pattern[str], str]] = []
        for p in qnt.pracownicy:
            czlony = p.nazwisko.split("-")
            nazwisko = _wzorzec_slowa(czlony[0]) + "".join(
                f"(?:-{_wzorzec_slowa(c)})?" for c in czlony[1:]
            )
            imie = _wzorzec_slowa(p.imie)
            pelne.append((_calosc(rf"{imie}\s+{nazwisko}"), p.osoba_id))
            pelne.append((_calosc(rf"{nazwisko}\s+{imie}"), p.osoba_id))
            nazwiska.append((_calosc(nazwisko), p.osoba_id))
            for c in czlony[1:]:
                if c not in pomijane:
                    nazwiska.append((_calosc(_wzorzec_slowa(c)), p.osoba_id))
            imiona.append((_calosc(imie), p.osoba_id))
        self._osoby = pelne + nazwiska + imiona

        komorki = {p.komorka for p in qnt.pracownicy}
        czlony_komorek = {c.strip() for k in komorki for c in k.split("/") if c.strip()}
        # Dłuższe najpierw: pełna ścieżka komórki przed departamentem i wydziałem.
        self._komorki = [
            re.compile(re.escape(k))
            for k in sorted(komorki | czlony_komorek, key=len, reverse=True)
        ]

        identyfikatory = set()
        for p in qnt.pracownicy:
            identyfikatory |= {p.osoba_id, p.przelozony_id}
            if p.zmiana_oceniajacego:
                identyfikatory.add(p.zmiana_oceniajacego.poprzedni_przelozony)
        self._identyfikatory = _calosc(
            "(?:" + "|".join(re.escape(i) for i in sorted(identyfikatory, key=len, reverse=True)) + ")"
        )

    def _etykieta(self, osoba_id: str, oceniany: Pracownik | None) -> str:
        if oceniany is not None:
            if osoba_id == oceniany.osoba_id:
                return self.pseudonimy["oceniany"]
            if osoba_id == oceniany.przelozony_id:
                return self.pseudonimy["przelozony"]
        return self.pseudonimy["inna_osoba"]

    def pseudonimizuj(self, tekst: str, oceniany_id: str | None = None) -> str:
        """Zamienia dane identyfikujące osoby z QNT w ``tekst``. Z ``oceniany_id``
        osoba oceniana i jej przełożony dostają role, bez niego wszyscy są „[osoba]”."""
        oceniany = self.qnt.pracownik(oceniany_id) if oceniany_id else None
        for wzorzec in self._komorki:
            tekst = wzorzec.sub(self.pseudonimy["komorka"], tekst)
        for wzorzec, osoba_id in self._osoby:
            tekst = wzorzec.sub(self._etykieta(osoba_id, oceniany), tekst)
        return self._identyfikatory.sub(self.pseudonimy["osoba_id"], tekst)


class ChronionyDostawca:
    """Opakowanie dostawcy spoza maszyny: pytanie jest pseudonimizowane przed wysłaniem.
    Nazwa, model i tryb są te same, więc dziennik i odpowiedź API się nie zmieniają."""

    def __init__(self, dostawca: LlmProvider, pseudonimizator: Pseudonimizator) -> None:
        self.dostawca = dostawca
        self.pseudonimizator = pseudonimizator
        self.nazwa = dostawca.nazwa
        self.model = dostawca.model
        self.tryb = dostawca.tryb

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz:
        czyste = zapytanie.model_copy(
            update={"pytanie": self.pseudonimizator.pseudonimizuj(zapytanie.pytanie)}
        )
        return self.dostawca.odpowiedz(czyste)


def chron_zewnetrznych(
    dostawcy: Sequence[LlmProvider], pseudonimizator: Pseudonimizator
) -> list[LlmProvider]:
    """Opakowuje w ``ChronionyDostawca`` każdego dostawcę z ``ZEWNETRZNI``."""
    return [
        ChronionyDostawca(d, pseudonimizator) if d.nazwa in ZEWNETRZNI else d for d in dostawcy
    ]
