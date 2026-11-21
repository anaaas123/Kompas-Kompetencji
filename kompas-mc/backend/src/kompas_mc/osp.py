"""Opis stanowiska pracy (OSP) odczytany z fragmentów korpusu MC.

Pliki OSP mają te same nagłówki („CEL ISTNIENIA STANOWISKA PRACY”, „ZADANIA DOMINUJĄCE”…),
ale różne numery tabel, więc parser szuka nagłówków, a nie pozycji. Każde pole niesie
adnotację z dosłownym cytatem fragmentu, z którego pochodzi.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from kompas_core.zrodla import Fragment, Kategoria, SourceRef
from pydantic import BaseModel

from .korpus_mc import KorpusMC

ZAZNACZONE = "☒"


class Pole(BaseModel):
    tekst: str
    adnotacja: SourceRef


class Zadanie(BaseModel):
    nr: int
    tekst: str
    adnotacja: SourceRef


class OpisIPrzyklady(BaseModel):
    opis: Pole | None = None
    przyklady: Pole | None = None


class Podlegli(BaseModel):
    zaznaczone: list[str]
    """Zaznaczone opcje pola „LICZBA PODLEGŁYCH PRACOWNIKÓW” (poprawny OSP ma jedną)."""
    adnotacja: SourceRef | None = None


class KompetencjeMiekkie(BaseModel):
    lista: list[str]
    adnotacja: SourceRef


class OpisStanowiska(BaseModel):
    doc_id: str
    symbol: str | None
    nazwa: str
    komorka: list[str]
    cel: Pole | None = None
    zadania_dominujace: list[Zadanie] = []
    zadania_pozostale: list[Zadanie] = []
    podlegli: Podlegli
    zlozonosc: OpisIPrzyklady = OpisIPrzyklady()
    samodzielnosc: OpisIPrzyklady = OpisIPrzyklady()
    kompetencje_miekkie: KompetencjeMiekkie | None = None


_ZADANIE = re.compile(r"^Zadanie\s*(\d+)\s*[:.]\s*", re.IGNORECASE)
_KOMPETENCJE = "Kompetencje miękkie:"
_TABELA = re.compile(r"^tabela (\d+) w(\d+) k(\d+)$")


def _czysty(tekst: str) -> str:
    """Tekst do wyświetlenia: twarde spacje i łamania wierszy jako zwykłe spacje."""
    return " ".join(tekst.split())


def _adnotacja(f: Fragment, cytat: str | None = None) -> SourceRef:
    return SourceRef(
        doc_id=f.doc_id,
        doc_version=f.doc_version,
        lokalizator=f.lokalizator,
        strona=f.strona,
        cytat_doslowny=(cytat or f.tekst).strip(),
        kategoria=Kategoria.OBJASNIENIE_MATERIALU,
    )


def _pole(f: Fragment) -> Pole:
    return Pole(tekst=f.tekst.strip(), adnotacja=_adnotacja(f))


def _komorka(f: Fragment) -> tuple[int, int, int] | None:
    m = _TABELA.match(f.lokalizator or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _naglowek(f: Fragment, tekst: str) -> bool:
    return f.tekst.strip().upper().startswith(tekst.upper())


def _indeks(fr: Sequence[Fragment], naglowek: str, od: int = 0) -> int | None:
    return next((i for i in range(od, len(fr)) if _naglowek(fr[i], naglowek)), None)


def _po_naglowku(fr: Sequence[Fragment], naglowek: str) -> Fragment | None:
    i = _indeks(fr, naglowek)
    return fr[i + 1] if i is not None and i + 1 < len(fr) else None


def _zadania(fr: Sequence[Fragment], od: str, do: str) -> list[Zadanie]:
    i = _indeks(fr, od)
    if i is None:
        return []
    koniec = _indeks(fr, do, i + 1) or len(fr)
    wynik = []
    for f in fr[i + 1 : koniec]:
        m = _ZADANIE.match(f.tekst.strip())
        if m:
            wynik.append(
                Zadanie(nr=int(m.group(1)), tekst=f.tekst.strip()[m.end() :], adnotacja=_adnotacja(f))
            )
    return wynik


def _opis_i_przyklady(fr: Sequence[Fragment], sekcja: str) -> OpisIPrzyklady:
    """Sekcja z wierszem nagłówków „OPIS | PRZYKŁADY” i wierszem treści pod nim."""
    i = _indeks(fr, sekcja)
    if i is None:
        return OpisIPrzyklady()
    j = _indeks(fr, "PRZYKŁADY", i + 1)
    if j is None or j + 1 >= len(fr):
        return OpisIPrzyklady()
    naglowek = _komorka(fr[j])
    wynik: dict[str, Pole] = {}
    for f in fr[j + 1 : j + 3]:
        k = _komorka(f)
        if not (k and naglowek and k[0] == naglowek[0] and k[1] == naglowek[1] + 1):
            break
        wynik["opis" if k[2] == 1 else "przyklady"] = _pole(f)
    return OpisIPrzyklady(**wynik)


def _podlegli(fr: Sequence[Fragment]) -> Podlegli:
    f = _po_naglowku(fr, "LICZBA PODLEGŁYCH PRACOWNIKÓW")
    if f is None:
        return Podlegli(zaznaczone=[])
    zaznaczone = [
        w.strip()[len(ZAZNACZONE) :].strip()
        for w in f.tekst.splitlines()
        if w.strip().startswith(ZAZNACZONE)
    ]
    cytat = next((w.strip() for w in f.tekst.splitlines() if w.strip().startswith(ZAZNACZONE)), None)
    return Podlegli(zaznaczone=zaznaczone, adnotacja=_adnotacja(f, cytat) if cytat else None)


def _kompetencje_miekkie(fr: Sequence[Fragment]) -> KompetencjeMiekkie | None:
    for f in fr:
        poz = f.tekst.find(_KOMPETENCJE)
        if poz < 0:
            continue
        cytat = f.tekst[poz:]
        tresc = cytat[len(_KOMPETENCJE) :]
        lista = [
            _czysty(re.sub(r"^[-–•\s]+", "", c)).rstrip(".").strip()
            for c in re.split(r"[,\n]", tresc)
        ]
        return KompetencjeMiekkie(lista=[c for c in lista if c], adnotacja=_adnotacja(f, cytat))
    return None


def _symbol(fr: Sequence[Fragment]) -> str | None:
    i = _indeks(fr, "SYMBOL STANOWISKA PRACY")
    if i is None:
        return None
    naglowek = _komorka(fr[i])
    if i + 1 < len(fr):
        k = _komorka(fr[i + 1])
        if k and naglowek and k[:2] == naglowek[:2]:
            return fr[i + 1].tekst.strip()
    return None


def _komorka_organizacyjna(fr: Sequence[Fragment]) -> list[str]:
    i = _indeks(fr, "NAZWA KOMÓRKI ORGANIZACYJNEJ URZĘDU")
    j = _indeks(fr, "NAZWA STANOWISKA PRACY", (i or 0) + 1)
    if i is None or j is None:
        return []
    return [_czysty(f.tekst) for f in fr[i + 1 : j]]


def odczytaj(fragmenty: Sequence[Fragment], doc_id: str, nazwa: str) -> OpisStanowiska:
    """OSP z fragmentów jednego dokumentu (w kolejności z korpusu)."""
    fr = list(fragmenty)
    return OpisStanowiska(
        doc_id=doc_id,
        symbol=_symbol(fr),
        nazwa=nazwa,
        komorka=_komorka_organizacyjna(fr),
        cel=(lambda f: _pole(f) if f else None)(_po_naglowku(fr, "CEL ISTNIENIA STANOWISKA PRACY")),
        zadania_dominujace=_zadania(fr, "ZADANIA DOMINUJĄCE", "POZOSTAŁE ZADANIA"),
        zadania_pozostale=_zadania(fr, "POZOSTAŁE ZADANIA", "UPOWAŻNIENIA I PEŁNOMOCNICTWA"),
        podlegli=_podlegli(fr),
        zlozonosc=_opis_i_przyklady(fr, "ZŁOŻONOŚĆ I KREATYWNOŚĆ"),
        samodzielnosc=_opis_i_przyklady(fr, "NIEZBĘDNA SAMODZIELNOŚĆ I INICJATYWA"),
        kompetencje_miekkie=_kompetencje_miekkie(fr),
    )


class KatalogOsp:
    """Wszystkie OSP z korpusu MC (dokumenty o ``doc_id`` z prefiksem ``osp-``), po symbolu.

    Korpus powstaje przy starcie aplikacji, więc katalog wypełnia ``wczytaj``.
    """

    def __init__(self, korpus: KorpusMC | None = None) -> None:
        self._po_symbolu: dict[str, OpisStanowiska] = {}
        if korpus is not None:
            self.wczytaj(korpus)

    def wczytaj(self, korpus: KorpusMC) -> None:
        po_doc: dict[str, list[Fragment]] = {}
        for f in korpus.korpus.fragmenty:
            if f.doc_id.startswith("osp-"):
                po_doc.setdefault(f.doc_id, []).append(f)
        self._po_symbolu = {}
        for doc_id, fr in po_doc.items():
            osp = odczytaj(fr, doc_id, korpus.dokumenty[doc_id].nazwa)
            if osp.symbol:
                self._po_symbolu[osp.symbol] = osp

    def po_symbolu(self, symbol: str | None) -> OpisStanowiska | None:
        return self._po_symbolu.get(symbol) if symbol else None

    @property
    def symbole(self) -> list[str]:
        return sorted(self._po_symbolu)
