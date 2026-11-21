"""Asystent formalny: odpowiedź wyłącznie cytatami z korpusu MC (#27 tracer → #37 pełny zakres).

Przebieg ``odpowiedz(pytanie, sciezka)``:

1. Słownik z konfiguracji dopisuje do pytania słowa z przepisów („zwolnienie lekarskie”
   → „usprawiedliwiona nieobecność”, „kiedy” → „termin”).
2. Przygotowany zestaw pytań i odpowiedzi (``faq.yaml``, pkt 5 treści zadania): gdy pytanie
   jest dość podobne (``prog_faq``) do pozycji dla tej ścieżki, ``tresc`` = odpowiedź napisana
   przez człowieka, a pierwszy cytat = fragment z cytatem tej pozycji (sprawdzanym w CI
   przez ``kompas-waliduj``). Dalsze cytaty z rankingu.
3. Pojęcia pytania, których nie ma ani w korpusie, ani w FAQ ⇒ „brak informacji” z ich
   listą (``nieznane_pojecia``).
4. Ranking BM25 na rdzeniach ``kompas_core`` skróconych do ``dlugosc_rdzenia`` znaków, tylko
   w dokumentach ścieżki, z wagą dokumentu (przepis przed objaśnieniem). Wynik najlepszego
   fragmentu poniżej ``minimalny_wynik`` ⇒ „brak informacji”.
5. Wybrane fragmenty idą przez łańcuch ``LlmProvider`` (domyślnie ekstrakcyjny); core odrzuca
   cytaty bez pokrycia w korpusie i loguje wywołanie.

Każdy cytat ma wyróżnione zdanie (dosłowny podciąg fragmentu) i flagę, gdy objaśnienie
powołuje ustawę, której tekstu nie ma w bazie.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from kompas_core.llm import (
    BrakOdpowiedzi,
    Dziennik,
    LlmProvider,
    Tryb,
    Zapytanie,
    wywolaj,
    z_konfiguracji,
)
from kompas_core.zrodla import Fragment, Kategoria
from kompas_core.zrodla.korpus import tokeny
from pydantic import BaseModel

from .korpus_mc import KorpusMC

Sciezka = Literal["pierwsza", "okresowa"]


class CytatAsystenta(BaseModel):
    fragment_id: str
    doc_id: str
    dokument: str
    lokalizator: str | None
    strona: int | None
    kategoria: Kategoria
    cytat: str
    wyrozniony: str | None = None
    """Najlepiej pasujące zdanie fragmentu (dosłowny podciąg ``cytat``)."""
    powoluje_ustawe: bool = False


class OdpowiedzAsystenta(BaseModel):
    pytanie: str
    sciezka: Sciezka | None
    znaleziono: bool
    komunikat: str | None = None
    tresc: str | None = None
    cytaty: list[CytatAsystenta] = []
    tryb: Tryb | None = None
    dostawca: str | None = None
    odrzuceni: list[str] = []
    pokrycie: float = 0.0
    """Podobieństwo do pozycji FAQ albo udział pojęć pytania w najlepszym fragmencie."""
    faq_id: str | None = None
    nieznane_pojecia: list[str] = []
    uwagi: list[str] = []


@dataclass
class KonfiguracjaAsystenta:
    wersja: str
    cytaty: int
    komunikat_brak: str
    llm: dict[str, Any]
    dlugosc_rdzenia: int = 5
    minimalny_wynik: float = 0.0
    prog_faq: float = 1.0
    udzial_nieznanych: float = 0.0
    slowa_pomijane: str = ""
    slownik: dict[str, str] | None = None
    wagi_kategorii: dict[str, float] | None = None
    wagi_dokumentow: dict[str, float] | None = None
    wzorzec_ustawy: str = r"(?!)"
    komunikaty: dict[str, str] | None = None
    faq: list[dict] | None = None

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaAsystenta:
        plik = Path(plik)
        d = yaml.safe_load(plik.read_text(encoding="utf-8"))
        faq = None
        if d.get("faq"):
            faq = yaml.safe_load((plik.parent / d["faq"]).read_text(encoding="utf-8"))["pozycje"]
        return cls(
            wersja=str(d["wersja"]),
            cytaty=int(d.get("cytaty", 3)),
            komunikat_brak=d["komunikat_brak"],
            llm=d["llm"],
            dlugosc_rdzenia=int(d.get("dlugosc_rdzenia", 5)),
            minimalny_wynik=float(d.get("minimalny_wynik", 0.0)),
            prog_faq=float(d.get("prog_faq", 1.0)),
            udzial_nieznanych=float(d.get("udzial_nieznanych", 0.0)),
            slowa_pomijane=str(d.get("slowa_pomijane", "")),
            slownik={str(k).lower(): str(v) for k, v in (d.get("slownik") or {}).items()},
            wagi_kategorii=d.get("wagi_kategorii") or {},
            wagi_dokumentow=d.get("wagi_dokumentow") or {},
            wzorzec_ustawy=d.get("wzorzec_ustawy", r"(?!)"),
            komunikaty=d.get("komunikaty") or {},
            faq=faq,
        )


@dataclass(frozen=True)
class _PozycjaFaq:
    id: str
    sciezka: str
    odpowiedz: str
    warianty: tuple[frozenset[str], ...]
    fragment: Fragment
    cytat: str


def _bez_dzielenia(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s)).strip()


class Asystent:
    def __init__(
        self,
        korpus: KorpusMC,
        konfiguracja: KonfiguracjaAsystenta,
        dziennik: Dziennik,
        dostawcy: list[LlmProvider] | None = None,
    ) -> None:
        self.korpus = korpus
        self.konf = konfiguracja
        self.dziennik = dziennik
        self.dostawcy = dostawcy if dostawcy is not None else z_konfiguracji(konfiguracja.llm)
        self._wzorzec_ustawy = re.compile(konfiguracja.wzorzec_ustawy, re.IGNORECASE)
        self._pomijane = set(self._tokeny(konfiguracja.slowa_pomijane))

        # Indeks BM25 na rdzeniach skróconych (core nie ma porównania po prefiksie).
        self._fragmenty = korpus.korpus.fragmenty
        self._tf = [Counter(self._tokeny(f.tekst)) for f in self._fragmenty]
        self._dl = [sum(c.values()) for c in self._tf]
        n = len(self._fragmenty)
        self._avgdl = (sum(self._dl) / n) if n else 1.0
        self._df: Counter[str] = Counter()
        for c in self._tf:
            self._df.update(c.keys())
        self._idf = {t: math.log((n - c + 0.5) / (c + 0.5) + 1) for t, c in self._df.items()}
        self._idf_max = math.log((n + 0.5) / 0.5 + 1)

        self._faq = [self._pozycja(p) for p in (konfiguracja.faq or [])]
        self._slownictwo_faq = {t for p in self._faq for w in p.warianty for t in w}

    # --- API --------------------------------------------------------------------------

    def odpowiedz(
        self, pytanie: str, sciezka: Sciezka | None = None, kontekst: str | None = None
    ) -> OdpowiedzAsystenta:
        brak = OdpowiedzAsystenta(
            pytanie=pytanie, sciezka=sciezka, znaleziono=False, komunikat=self.konf.komunikat_brak
        )
        rozwiniete, pokryte = self._rozwin(pytanie)
        zapytanie = self._tresc(rozwiniete)
        if not zapytanie:
            return brak
        dozwolone = set(self.korpus.doc_ids_dla(sciezka))

        faq, podob = self._dopasuj_faq(zapytanie, sciezka)
        if faq is None:
            nieznane = self._nieznane_pojecia(pytanie, pokryte)
            if nieznane:
                kom = self._kom("nieznane_pojecia").format(pojecia=", ".join(nieznane))
                return brak.model_copy(update={"nieznane_pojecia": nieznane, "uwagi": [kom]})

        ranking = self._ranking(zapytanie, dozwolone)
        if faq is None and (not ranking or ranking[0][0] < self.konf.minimalny_wynik):
            return brak

        wybrane: list[Fragment] = [faq.fragment] if faq else []
        for _, f in ranking:
            if len(wybrane) >= self.konf.cytaty:
                break
            if all(f.id != w.id for w in wybrane):
                wybrane.append(f)

        try:
            wynik = wywolaj(
                Zapytanie(
                    operacja="asystent_formalny",
                    prompt_wersja=self.konf.wersja,
                    pytanie=(
                        f"{rozwiniete}\n\nKONTEKST PROCESU (dane pseudonimizowane):\n{kontekst}"
                        if kontekst
                        else rozwiniete
                    ),
                    fragmenty=wybrane,
                ),
                self.dostawcy,
                self.dziennik,
            )
        except BrakOdpowiedzi:
            if faq is None:
                return brak
            wynik = None

        kolejnosc = {f.id: i for i, f in enumerate(wybrane)}
        po_id = {f.id: f for f in wybrane}
        teksty: dict[str, str] = {}
        if wynik is not None:
            for c in sorted(wynik.odpowiedz.cytaty, key=lambda c: kolejnosc[c.fragment_id]):
                teksty.setdefault(c.fragment_id, c.cytat)
        if faq is not None and faq.fragment.id not in teksty:
            # Dostawca pominął fragment FAQ (np. brak wspólnych słów); jego cytat jest
            # sprawdzany w CI (kompas-waliduj), więc pokazujemy fragment w całości.
            teksty = {faq.fragment.id: faq.fragment.tekst, **teksty}
        cytaty = [
            self._cytat(po_id[fid], tekst, zapytanie, faq if faq and fid == faq.fragment.id else None)
            for fid, tekst in sorted(teksty.items(), key=lambda kv: kolejnosc[kv[0]])
        ]

        uwagi = [self._kom("sugestia")]
        if faq is not None:
            uwagi.append(self._kom("faq"))
        if any(c.powoluje_ustawe for c in cytaty):
            uwagi.append(self._kom("ustawa"))
        pokrycie = podob if faq else self._pokrycie(zapytanie, cytaty[0].cytat if cytaty else "")
        return OdpowiedzAsystenta(
            pytanie=pytanie,
            sciezka=sciezka,
            znaleziono=True,
            tresc=faq.odpowiedz if faq else (wynik.odpowiedz.tresc if wynik else None),
            cytaty=cytaty,
            tryb=wynik.tryb if wynik else Tryb.EKSTRAKCYJNE,
            dostawca=wynik.dostawca if wynik else "faq",
            odrzuceni=wynik.odrzuceni if wynik else [],
            pokrycie=round(pokrycie, 3),
            faq_id=faq.id if faq else None,
            uwagi=uwagi,
        )

    # --- słowa ------------------------------------------------------------------------

    def _kom(self, klucz: str) -> str:
        return (self.konf.komunikaty or {}).get(klucz, "")

    def _tokeny(self, tekst: str) -> list[str]:
        return [t[: self.konf.dlugosc_rdzenia] for t in tokeny(tekst)]

    def _tresc(self, tekst: str) -> list[str]:
        """Tokeny niosące treść: bez słów pomijanych, liczb i powtórzeń."""
        widziane: dict[str, None] = {}
        for t in self._tokeny(tekst):
            if t not in self._pomijane and not t.isdigit():
                widziane[t] = None
        return list(widziane)

    def _rozwin(self, pytanie: str) -> tuple[str, set[str]]:
        """Dopisuje zamienniki ze słownika. Całe słowa; dłuższe wyrażenie wygrywa
        i zajmuje swój fragment pytania („ile dni” nie uruchamia też krótszych haseł)."""
        slownik = self.konf.slownik or {}
        maly = pytanie.lower()
        zajete = [False] * len(maly)
        dopiski, pokryte = [], set()
        for wyrazenie in sorted(slownik, key=len, reverse=True):
            for m in re.finditer(rf"(?<!\w){re.escape(wyrazenie)}(?!\w)", maly):
                if any(zajete[m.start() : m.end()]):
                    continue
                zajete[m.start() : m.end()] = [True] * (m.end() - m.start())
                dopiski.append(slownik[wyrazenie])
                pokryte.update(self._tokeny(wyrazenie))
        return " ".join([pytanie, *dopiski]), pokryte

    def _nieznane_pojecia(self, pytanie: str, pokryte: set[str]) -> list[str]:
        """Słowa pytania, których rdzenia nie ma w korpusie ani w FAQ, jeśli stanowią
        co najmniej ``udzial_nieznanych`` pojęć treściowych; inaczej pusta lista."""
        wynik: list[str] = []
        tresc = 0
        for slowo in re.findall(r"\w+", pytanie):
            t = self._tokeny(slowo)
            if not t:
                continue
            r = t[0]
            if r in self._pomijane or r in pokryte or r.isdigit() or len(r) < 3:
                continue
            tresc += 1
            znane = self._df.get(r, 0) > 0 or r in self._slownictwo_faq
            if not znane and slowo.lower() not in (w.lower() for w in wynik):
                wynik.append(slowo)
        return wynik if tresc and len(wynik) / tresc >= self.konf.udzial_nieznanych else []

    # --- FAQ --------------------------------------------------------------------------

    def _pozycja(self, p: dict) -> _PozycjaFaq:
        ref = p["adnotacje"][0]
        cel = _bez_dzielenia(ref["cytat_dosłowny"])
        fragment = next(
            (f for f in self._fragmenty
             if f.doc_id == ref["doc_id"] and cel in _bez_dzielenia(f.tekst)),
            None,
        )
        if fragment is None:
            raise ValueError(f"{p['id']}: cytatu nie ma w korpusie ({ref['doc_id']})")
        return _PozycjaFaq(
            id=p["id"],
            sciezka=p["sciezka"],
            odpowiedz=p["odpowiedz"],
            warianty=tuple(frozenset(self._tresc(self._rozwin(w)[0])) for w in p["pytania"]),
            fragment=fragment,
            cytat=ref["cytat_dosłowny"],
        )

    def _waga(self, t: str) -> float:
        return self._idf.get(t, self._idf_max)

    def _podobienstwo(self, a: set[str], b: frozenset[str]) -> float:
        """Kosinus zbiorów ważonych idf; pojęcia spoza korpusu mają wagę maksymalną."""
        if not a or not b:
            return 0.0
        wspolne = sum(self._waga(t) ** 2 for t in a & b)
        return wspolne / (
            math.sqrt(sum(self._waga(t) ** 2 for t in a))
            * math.sqrt(sum(self._waga(t) ** 2 for t in b))
        )

    def _dopasuj_faq(
        self, zapytanie: list[str], sciezka: Sciezka | None
    ) -> tuple[_PozycjaFaq | None, float]:
        q = set(zapytanie)
        najlepsza, najwyzej = None, 0.0
        for p in self._faq:
            if sciezka is not None and p.sciezka not in (sciezka, "wspolne"):
                continue
            s = max(self._podobienstwo(q, w) for w in p.warianty)
            if s > najwyzej:
                najlepsza, najwyzej = p, s
        if najlepsza is None or najwyzej < self.konf.prog_faq:
            return None, najwyzej
        return najlepsza, najwyzej

    # --- ranking ----------------------------------------------------------------------

    def _bm25(self, zapytanie: list[str], i: int, k1: float = 1.2, b: float = 0.5) -> float:
        tf, dl, s = self._tf[i], self._dl[i], 0.0
        for t in zapytanie:
            f = tf.get(t)
            if f:
                s += self._idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self._avgdl))
        return s

    def _waga_dokumentu(self, doc_id: str) -> float:
        w = (self.konf.wagi_dokumentow or {}).get(doc_id)
        if w is not None:
            return float(w)
        kat = self.korpus.dokumenty[doc_id].kategoria.value
        return float((self.konf.wagi_kategorii or {}).get(kat, 1.0))

    def _ranking(self, zapytanie: list[str], dozwolone: set[str]) -> list[tuple[float, Fragment]]:
        wyniki = []
        for i, f in enumerate(self._fragmenty):
            if f.doc_id not in dozwolone:
                continue
            s = self._bm25(zapytanie, i)
            if s > 0:
                wyniki.append((s * self._waga_dokumentu(f.doc_id), f))
        wyniki.sort(key=lambda x: (-x[0], x[1].id))
        return wyniki

    def _pokrycie(self, zapytanie: list[str], tekst: str) -> float:
        return len(set(zapytanie) & set(self._tokeny(tekst))) / len(zapytanie) if zapytanie else 0.0

    # --- cytat ------------------------------------------------------------------------

    def _cytat(
        self, f: Fragment, tekst: str, zapytanie: list[str], faq: _PozycjaFaq | None
    ) -> CytatAsystenta:
        dok = self.korpus.dokumenty[f.doc_id]
        if faq is not None and faq.cytat in tekst:
            wyrozniony = faq.cytat
        else:
            wyrozniony = self._najlepsze_zdanie(tekst, zapytanie)
        return CytatAsystenta(
            fragment_id=f.id,
            doc_id=f.doc_id,
            dokument=dok.nazwa,
            lokalizator=f.lokalizator,
            strona=f.strona,
            kategoria=dok.kategoria,
            cytat=tekst,
            wyrozniony=wyrozniony,
            powoluje_ustawe=dok.kategoria is not Kategoria.PRZEPIS
            and bool(self._wzorzec_ustawy.search(tekst)),
        )

    def _najlepsze_zdanie(self, tekst: str, zapytanie: list[str]) -> str:
        """Zdanie lub punkt z największą wagą wspólnych pojęć (dosłowny podciąg tekstu)."""
        granice = [0]
        for m in re.finditer(r"(?<=[.;:])\s+(?=\S)|\n(?=\s*(?:\d+\)|[a-z]\)|−|-|•))", tekst):
            granice.append(m.end())
        granice.append(len(tekst))
        zbior = set(zapytanie)
        najlepsze, najwyzej = tekst.strip(), -1.0
        for a, b in zip(granice, granice[1:]):
            kawalek = tekst[a:b].strip()
            if not kawalek:
                continue
            w = sum(self._idf.get(t, 0) for t in set(self._tokeny(kawalek)) & zbior)
            if w > najwyzej:
                najlepsze, najwyzej = kawalek, w
        return najlepsze
