"""Opis osoby na karcie pracownika (#55): 2–4 zdania z faktów, które użytkownik może widzieć.

Każde zdanie wskazuje fakty, na których się opiera. Opis nie ustala oceny ani poziomu, niczego nie
zapisuje i zawsze nosi oznaczenie sugestii. Domyślnie składa go szablon; na żądanie model przez łańcuch
dostawców z core (``wywolaj``, jak ``cele_llm``). Fakty idą do modelu jako fragmenty (ID fragmentu = ID
faktu), bez stanowiska (``NIE_DO_MODELU``) i po pseudonimizacji; imienia, nazwiska, komórki ani
``osoba_id`` fakty nie zawierają. Zdanie z modelu przechodzi osobną walidację (``waliduj_opis``),
bo ``sprawdz_odpowiedz`` w core nie sprawdza ``tresc``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime

from kompas_core.llm import BrakOdpowiedzi, Dziennik, LlmProvider, Tryb, Zapytanie, wywolaj
from kompas_core.zrodla import Fragment
from pydantic import BaseModel

from .cele import Cel
from .cykl import EtapOsoby
from .qnt import Pracownik

OPERACJA = "opis_osoby"
WERSJA = "opis-osoby@1"
MAKS_ZDAN = 4
NIE_DO_MODELU = {"kadry.stanowisko"}
"""Stanowisko nie jest pseudonimizowane, a w małej komórce identyfikuje osobę (minimalizacja danych)."""

POLECENIE = """Napisz od 2 do 4 krótkich zdań po polsku o Ocenianym do karty pracownika: kim jest w pracy,
gdzie jest w cyklu oceny, co wynika z ostatniej oceny oraz (jeśli są fakty) z samooceny i celów.
Używaj wyłącznie podanych fragmentów: każdy fragment to jeden fakt, ID fragmentu jest ID faktu.
Nie ustalaj ani nie proponuj oceny, poziomu, awansu, nagrody ani szkoleń; nie wartościuj.
Liczby i daty przepisuj z faktów.
W polu "tresc" zwróć tekst z obiektem JSON:
{"zdania": [{"tekst": "...", "fakty": ["<ID faktu>", ...]}]}
Każde zdanie wymienia w "fakty" wszystkie fakty, z których korzysta. Dosłowne fragmenty tych faktów
dopisz do "cytaty"."""

KADRY = "kadry (QNT)"
CYKL = "cykl oceny"
_KORPUS = {"urzednik_sc": "urzędnik służby cywilnej", "pracownik_sc": "pracownik służby cywilnej"}
_SCIEZKA = {"okresowa": "ocena okresowa", "pierwsza": "pierwsza ocena", None: "ścieżka oceny nieustalona"}

_LICZBA = re.compile(r"\d+(?:,\d+)?")
# ponytail: lista słów, nie klasyfikator; liczebniki słowne i werdykty spoza listy przejdą.
_WERDYKT = re.compile(
    r"zasługuj|powin(?:ien|na|no|ni|ny)\b|należy (?:mu|jej|go)\b|rekomend|zalec|awans|podwyżk|nagrod"
    r"|premi[aięoy]|zwolni|ocena (?:będzie|wyniesie)",
    re.IGNORECASE,
)


class Fakt(BaseModel):
    id: str
    tekst: str
    zrodlo: str


class Zdanie(BaseModel):
    tekst: str
    fakty: list[str]
    """ID faktów, na których opiera się zdanie."""


class WynikOpisuModelu(BaseModel):
    zdania: list[Zdanie]
    odrzucone: list[str]
    """Powody odrzucenia zdań albo całej odpowiedzi (bez szczegółów błędów dostawcy)."""
    dostawca: str | None = None
    tryb: Tryb | None = None


def _lata(n: int) -> str:
    if n == 0:
        return "krócej niż rok"
    if n == 1:
        return "1 rok"
    return f"{n} lata" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else f"{n} lat"


def _data(d: date) -> str:
    """Data jak na ekranie i w arkuszu: 15.10.2027."""
    return d.strftime("%d.%m.%Y")


def _dni(n: int) -> str:
    return "1 dzień" if n == 1 else f"{n} dni"


def fakty(
    p: Pracownik,
    etap: EtapOsoby,
    dzis: date,
    nazwy: dict[str, str],
    *,
    oceny_czastkowe: bool,
    biezace: tuple[int, dict[str, int]] | None = None,
    samoocena: tuple[datetime, int] | None = None,
    cele: list[Cel] | None = None,
) -> list[Fakt]:
    """Fakty o osobie. Router przekazuje tylko to, co użytkownik może widzieć: ``oceny_czastkowe``
    i ``biezace`` (liczba kryteriów, punkty decyzji) przy ``ocena.tresc``, ``samoocena`` (data
    przekazania, liczba rozbieżności) przy ``samoocena.czytaj``, ``cele`` przy ``cele.czytaj``.
    ``nazwy``: kompetencja_id → nazwa z modelu kompetencji."""
    d = p.data_zatrudnienia
    staz = dzis.year - d.year - ((dzis.month, dzis.day) < (d.month, d.day))
    umowa = "umowa na czas nieokreślony"
    if p.rodzaj_umowy == "okreslony":
        umowa = "umowa na czas określony" + (f" do {_data(p.data_konca_zatrudnienia)}" if p.data_konca_zatrudnienia else "")
    w = [
        Fakt(id="kadry.stanowisko", tekst=p.stanowisko, zrodlo=KADRY),
        Fakt(id="kadry.korpus", tekst=_KORPUS[p.korpus], zrodlo=KADRY),
        Fakt(id="kadry.staz", tekst=f"w urzędzie od {d.year} r. ({_lata(max(staz, 0))})", zrodlo=KADRY),
        Fakt(id="kadry.umowa", tekst=umowa, zrodlo=KADRY),
        Fakt(
            id="kadry.kierowanie",
            tekst="kieruje pracownikami" if p.kieruje_pracownikami else "nie kieruje pracownikami",
            zrodlo=KADRY,
        ),
        Fakt(id="cykl.etap", tekst=f"{_SCIEZKA[etap.sciezka]}, teraz: {etap.czynnosc.lower()}", zrodlo=CYKL),
    ]
    if etap.termin is not None and etap.dni_do_terminu is not None:
        n = etap.dni_do_terminu
        kiedy = "dziś" if n == 0 else f"za {_dni(n)}" if n > 0 else f"{_dni(-n)} po terminie"
        w.append(Fakt(id="cykl.termin", tekst=f"{etap.termin.nazwa} do {_data(etap.termin.data)} ({kiedy})", zrodlo=CYKL))

    o = p.ostatnia_ocena_okresowa
    if o is not None:
        w.append(Fakt(id="ocena.ostatnia", tekst=f"ostatnia ocena okresowa z {_data(o.data)}: {o.wynik}", zrodlo=KADRY))
        if oceny_czastkowe:
            # Od najwyżej do najniżej ocenionej kompetencji; szablon bierze pierwszą i ostatnią.
            for kid, pkt in sorted(o.oceny_czastkowe.items(), key=lambda x: -x[1]):
                w.append(Fakt(
                    id=f"oceny_czastkowe.{kid}", tekst=f"{nazwy.get(kid, kid)} – {pkt} pkt",
                    zrodlo="ostatnia ocena okresowa, ocena cząstkowa (kartoteka QNT)",
                ))
    if biezace is not None:
        liczba, punkty = biezace
        szczegoly = ", ".join(f"{nazwy.get(k, k)} – {v} pkt" for k, v in punkty.items())
        w.append(Fakt(
            id="biezaca.decyzje",
            tekst=f"bieżąca ocena: decyzje przełożonego w {len(punkty)} z {liczba} kryteriów ({szczegoly})",
            zrodlo="bieżąca ocena w aplikacji",
        ))
    if samoocena is not None:
        kiedy_s, rozb = samoocena
        w.append(Fakt(
            id="samoocena",
            tekst=f"samoocena przekazana {_data(kiedy_s.date())}; wskaźniki z rozbieżnością samooceny i oceny przełożonego: {rozb}",
            zrodlo="samoocena",
        ))
    if cele is not None:
        statusy = Counter(c.status for c in cele)
        tekst = (
            f"cele rozwojowe: {len(cele)} (" + ", ".join(f"{s}: {n}" for s, n in statusy.items()) + ")"
            if cele else "cele rozwojowe: brak zapisanych"
        )
        w.append(Fakt(id="cele", tekst=tekst, zrodlo="cele rozwojowe"))
    return w


def opis_z_szablonu(fakty: Sequence[Fakt]) -> list[Zdanie]:
    """2–3 zdania bez modelu: kadry, ostatnia ocena, bieżąca ocena z samooceną i celami. Etapu i terminu
    szablon nie powtarza, bo karta pokazuje je tuż pod opisem („Teraz: …”); model dostaje je w faktach."""
    po_id = {f.id: f for f in fakty}
    czastkowe = [f for f in fakty if f.id.startswith("oceny_czastkowe.")]
    zdania: list[Zdanie] = []

    def zdanie(czesci: list[tuple[str, Fakt | None]], sep: str = "; ") -> None:
        czesci = [(przed, f) for przed, f in czesci if f is not None]
        if czesci:
            t = sep.join(przed + f.tekst for przed, f in czesci)
            zdania.append(Zdanie(tekst=t[0].upper() + t[1:] + ".", fakty=[f.id for _, f in czesci]))

    kadry = ["kadry.stanowisko", "kadry.korpus", "kadry.staz", "kadry.umowa"]
    if po_id.get("kadry.kierowanie") and po_id["kadry.kierowanie"].tekst == "kieruje pracownikami":
        kadry.append("kadry.kierowanie")
    zdanie([("", po_id.get(i)) for i in kadry], ", ")
    ostatnia: list[tuple[str, Fakt | None]] = [("", po_id.get("ocena.ostatnia"))]
    if czastkowe:
        ostatnia.append(("najwyżej: ", czastkowe[0]))
    if len(czastkowe) > 1:
        ostatnia.append(("najniżej: ", czastkowe[-1]))
    zdanie(ostatnia)
    zdanie([("", po_id.get(i)) for i in ("biezaca.decyzje", "samoocena", "cele")])
    return zdania


def opis_z_modelu(fakty: Sequence[Fakt], dostawcy: Sequence[LlmProvider], dziennik: Dziennik) -> WynikOpisuModelu:
    """``fakty`` muszą być już bez ``NIE_DO_MODELU`` i po pseudonimizacji. Dostawca ekstrakcyjny
    nie układa zdań, więc jest pomijany. Pusta lista zdań = użyj szablonu."""
    dostawcy = [d for d in dostawcy if d.tryb != Tryb.EKSTRAKCYJNE]
    if not dostawcy:
        return WynikOpisuModelu(zdania=[], odrzucone=["brak skonfigurowanego dostawcy LLM"])
    zapytanie = Zapytanie(
        operacja=OPERACJA,
        prompt_wersja=WERSJA,
        pytanie=POLECENIE,
        fragmenty=[Fragment(id=f.id, doc_id=OPERACJA, lokalizator=f.zrodlo, tekst=f.tekst) for f in fakty],
    )
    try:
        wynik = wywolaj(zapytanie, dostawcy, dziennik)
    except BrakOdpowiedzi as e:
        # Szczegóły błędów (np. brak klucza, adres usługi) są w llm.jsonl; użytkownik widzi tylko dostawcę.
        return WynikOpisuModelu(zdania=[], odrzucone=[f"{w.dostawca}: brak poprawnej odpowiedzi" for w in e.wpisy])
    zdania, odrzucone = waliduj_opis(wynik.odpowiedz.tresc, fakty)
    return WynikOpisuModelu(zdania=zdania, odrzucone=odrzucone, dostawca=wynik.dostawca, tryb=wynik.tryb)


def _liczby(tekst: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in _LICZBA.findall(tekst)}


def _powod(z: Zdanie, po_id: dict[str, Fakt]) -> str | None:
    if not z.tekst.strip():
        return "puste zdanie"
    if not z.fakty:
        return "brak podstawy w faktach"
    if nieznane := [i for i in z.fakty if i not in po_id]:
        return f"fakty spoza listy: {', '.join(nieznane)}"
    znane = _liczby(" ".join(po_id[i].tekst for i in z.fakty))
    if obce := [n for n in _LICZBA.findall(z.tekst) if float(n.replace(",", ".")) not in znane]:
        return f"liczby bez pokrycia w cytowanych faktach: {', '.join(obce)}"
    if m := _WERDYKT.search(z.tekst):
        return f"werdykt („{m.group(0)}”)"
    return None


def waliduj_opis(tresc: str | None, fakty: Sequence[Fakt]) -> tuple[list[Zdanie], list[str]]:
    """Zdania z odpowiedzi modelu, które przeszły walidację, i powody odrzucenia pozostałych.

    Zdanie odpada, gdy nie cytuje żadnego faktu albo cytuje fakt spoza listy, zawiera liczbę, której
    nie ma w cytowanych faktach (daty liczą się jako liczby), zawiera słowo werdyktu albo przekracza
    limit ``MAKS_ZDAN``."""
    try:
        surowe = json.loads(tresc or "")["zdania"]
        if not isinstance(surowe, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        return [], ["odpowiedź modelu nie zawiera listy zdań w formacie JSON"]

    po_id = {f.id: f for f in fakty}
    przyjete: list[Zdanie] = []
    odrzucone: list[str] = []
    for i, s in enumerate(surowe, start=1):
        try:
            z = Zdanie.model_validate(s)
        except ValueError:
            odrzucone.append(f"zdanie {i}: niepełne dane")
            continue
        powod = _powod(z, po_id) or (f"ponad limit {MAKS_ZDAN} zdań" if len(przyjete) >= MAKS_ZDAN else None)
        if powod:
            odrzucone.append(f"zdanie {i} („{z.tekst[:60]}”): {powod}")
        else:
            przyjete.append(z)
    return przyjete, odrzucone
