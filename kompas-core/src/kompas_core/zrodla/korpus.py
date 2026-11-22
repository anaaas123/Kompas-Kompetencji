"""Korpus źródeł: zbiór fragmentów z wielu dokumentów i wyszukiwanie BM25."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from .ekstrakcja import ekstrahuj
from .model import Fragment, Trafienie, WynikEkstrakcji


@dataclass(frozen=True)
class OpisDokumentu:
    """Pozycja manifestu korpusu: który plik ma które ``doc_id`` i wersję."""

    doc_id: str
    plik: Path
    doc_version: str | None = None
    od_strony: int = 1


class Korpus:
    """Korpus zbudowany z dowolnego zestawu plików. Core nie zna żadnych materiałów:
    listę plików podaje konfiguracja wersji (manifest).
    """

    def __init__(self, wyniki: Iterable[WynikEkstrakcji]) -> None:
        self._wyniki = list(wyniki)
        self._fragmenty: list[Fragment] = [f for w in self._wyniki for f in w.fragmenty]
        self._po_id: dict[str, Fragment] = {}
        for f in self._fragmenty:
            if f.id in self._po_id:
                raise ValueError(f"powtórzone ID fragmentu: {f.id}")
            self._po_id[f.id] = f
        self._bm25: _Bm25 | None = None

    @classmethod
    def z_plikow(cls, dokumenty: Iterable[OpisDokumentu]) -> Korpus:
        """Ekstrahuje każdy plik i buduje korpus."""
        return cls(ekstrahuj(d.plik, d.doc_id, d.doc_version, d.od_strony) for d in dokumenty)

    @classmethod
    def z_manifestu(cls, manifest: str | Path) -> Korpus:
        """Manifest YAML::

            dokumenty:
              - doc_id: rozp-oceny
                doc_version: "2021"
                plik: ścieżka/względem/manifestu.pdf
                od_strony: 3        # opcjonalnie: PDF od tej strony
        """
        sciezka = Path(manifest)
        dane = yaml.safe_load(sciezka.read_text(encoding="utf-8")) or {}
        pozycje = dane.get("dokumenty")
        if not isinstance(pozycje, list):
            raise ValueError(f"{sciezka}: manifest musi mieć listę 'dokumenty'")
        opisy = []
        for i, p in enumerate(pozycje):
            if not isinstance(p, dict) or not p.get("doc_id") or not p.get("plik"):
                raise ValueError(f"{sciezka}: dokumenty[{i}] wymaga 'doc_id' i 'plik'")
            wersja = p.get("doc_version")
            opisy.append(
                OpisDokumentu(
                    doc_id=str(p["doc_id"]),
                    plik=(sciezka.parent / p["plik"]),
                    doc_version=None if wersja is None else str(wersja),
                    od_strony=int(p.get("od_strony", 1)),
                )
            )
        return cls.z_plikow(opisy)

    @property
    def raport(self) -> list[WynikEkstrakcji]:
        """Wyniki ekstrakcji wszystkich plików, w tym BRAK_TEKSTU i NIEOBSŁUGIWANY."""
        return list(self._wyniki)

    @property
    def fragmenty(self) -> list[Fragment]:
        return list(self._fragmenty)

    def fragment(self, fragment_id: str) -> Fragment:
        """``KeyError``, gdy fragmentu nie ma."""
        return self._po_id[fragment_id]

    def wersje(self, doc_id: str) -> list[str | None]:
        """Wersje dokumentu obecne w korpusie (pusta lista: nieznany dokument)."""
        return list(dict.fromkeys(w.doc_version for w in self._wyniki if w.doc_id == doc_id))

    def tekst_dokumentu(self, doc_id: str, doc_version: str | None = None) -> str:
        """Pełny tekst dokumentu (fragmenty złączone znakiem nowej linii).

        Bez ``doc_version`` dokument musi mieć w korpusie jedną wersję.
        """
        if doc_version is None:
            wersje = self.wersje(doc_id)
            if len(wersje) > 1:
                raise ValueError(f"dokument {doc_id} ma kilka wersji: {wersje}")
            doc_version = wersje[0] if wersje else None
        return "\n".join(
            f.tekst
            for f in self._fragmenty
            if f.doc_id == doc_id and f.doc_version == doc_version
        )

    def wyszukaj(
        self,
        zapytanie: str,
        k: int = 5,
        doc_ids: Iterable[str] | None = None,
    ) -> list[Trafienie]:
        """BM25 z prostą normalizacją polskich form. Wyniki malejąco wg trafności;
        fragmenty z wynikiem 0 są pomijane. ``doc_ids`` zawęża wyszukiwanie.
        """
        if self._bm25 is None:
            self._bm25 = _Bm25([tokeny(f.tekst) for f in self._fragmenty])
        dozwolone = set(doc_ids) if doc_ids is not None else None
        wyniki = self._bm25.wyniki(tokeny(zapytanie))
        trafienia = [
            Trafienie(fragment_id=f.id, wynik=round(w, 6), fragment=f)
            for f, w in zip(self._fragmenty, wyniki, strict=True)
            if w > 0 and (dozwolone is None or f.doc_id in dozwolone)
        ]
        trafienia.sort(key=lambda t: -t.wynik)
        return trafienia[:k]


# --- normalizacja polskich form ------------------------------------------------------

_KONCOWKI = sorted(
    """owaniami owaniach owaniem owania owanie osciami osciach oscia osci osc
    ami ach ego emu iej ych ymi imi owi om ow em ie ia ej ym im a e i o u y""".split(),
    key=len,
    reverse=True,
)


def _bez_ogonkow(s: str) -> str:
    s = s.replace("ł", "l").replace("Ł", "L")
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def rdzen(slowo: str) -> str:
    """Prosta normalizacja polskiej formy: małe litery, bez ogonków, bez końcówki."""
    s = _bez_ogonkow(slowo.lower())
    for k in _KONCOWKI:
        if s.endswith(k) and len(s) - len(k) >= 3:
            return s[: -len(k)]
    return s


_DZIELENIE = re.compile(r"(\w)-[ \t\u00a0]*\r?\n\s*(\w)")


def tokeny(tekst: str) -> list[str]:
    """Tokeny do BM25. Wyraz podzielony na końcu wiersza (``wstęp-\\nną``) jest
    łączony przed tokenizacją, tak jak w walidatorze cytatów."""
    tekst = _DZIELENIE.sub(r"\1\2", tekst.replace("\u00ad", ""))
    return [rdzen(t) for t in re.findall(r"\w+", tekst)]


class _Bm25:
    def __init__(self, dokumenty: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in dokumenty]
        self.dl = [len(d) for d in dokumenty]
        self.avgdl = (sum(self.dl) / len(self.dl)) if self.dl else 0.0
        n = len(dokumenty)
        df: Counter[str] = Counter()
        for d in self.tf:
            df.update(d.keys())
        self.idf = {t: math.log((n - c + 0.5) / (c + 0.5) + 1) for t, c in df.items()}

    def wyniki(self, zapytanie: list[str]) -> list[float]:
        wyniki = []
        for tf, dl in zip(self.tf, self.dl, strict=True):
            s = 0.0
            for t in set(zapytanie):
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf[t] * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                )
            wyniki.append(s)
        return wyniki
