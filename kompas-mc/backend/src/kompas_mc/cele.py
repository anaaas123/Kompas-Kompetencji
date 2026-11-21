"""Cele rozwojowe pracownika (#10, spec #2).

Cele należą do pracownika, nie do procesu oceny. Cel zaczyna się jako ``propozycja`` i obowiązuje
po zatwierdzeniu przez przełożonego. Przełącznik ``pracownik_moze_edytowac`` (``konfiguracja/cele.yaml``)
decyduje, czy pracownik sam tworzy i zmienia cele; akceptację zawsze daje przełożony.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.llm import Tryb
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field

from .rozwoj import WynikRozwoju

Status = Literal["propozycja", "zatwierdzony", "w_realizacji", "osiągnięty", "porzucony", "odrzucony"]
StatusPostepu = Literal["w_realizacji", "osiągnięty", "porzucony"]
"""Statusy ustawiane przez ``POST /api/cele/{id}/status``; akceptacja ma osobne endpointy."""
Aktor = Literal["pracownik", "przelozony"]


class Regula(BaseModel):
    id: str
    opis: str
    adnotacje: list[SourceRef]


class KonfiguracjaLlmCelow(BaseModel):
    wersja: str
    """Wersja promptu (``prompt_wersja`` w logu LLM)."""
    maks_celow: int = 3
    zrodla: list[str]
    """ID fragmentów poradników o wnioskach rozwojowych i IPRZ, dołączanych do każdego zapytania."""
    adnotacje: list[SourceRef]


class KonfiguracjaCelow(BaseModel):
    pracownik_moze_edytowac: bool
    regula: Regula
    llm: KonfiguracjaLlmCelow

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaCelow:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))


class TrescCelu(BaseModel):
    """Treść celu podawana przy tworzeniu i zmianie."""

    nazwa: str = Field(min_length=1, max_length=200)
    opis: str = Field(default="", max_length=4000)
    wskaznik_id: str | None = None
    """Wskaźnik z modelu kompetencji (opcjonalnie)."""
    miernik: str = Field(min_length=1, max_length=500)
    termin: date


class Cel(TrescCelu):
    id: int
    osoba_id: str
    status: Status
    komentarz: str | None
    """Komentarz przełożonego przy odrzuceniu."""
    zgloszono_osiagniecie: bool
    """Pracownik zgłosił osiągnięcie; status ``osiągnięty`` potwierdza przełożony."""
    autor: str
    utworzono: datetime
    zmieniono: datetime


OZNACZENIE = "Sugestia asystenta – do edycji"


class CytatCelu(BaseModel):
    """Cytat ze źródła, na którym opiera się podpowiedź z LLM (sprawdzony w korpusie)."""

    fragment_id: str
    doc_id: str
    lokalizator: str | None
    strona: int | None
    cytat: str


class PodpowiedzCelu(BaseModel):
    """Propozycja celu do przyjęcia albo odrzucenia. Nigdy nie zapisuje się sama."""

    nazwa: str
    opis: str
    wskaznik_id: str | None
    wskaznik: str | None
    kompetencja: str | None
    miernik: str
    termin: date | None
    """None: termin ustala pracownik z przełożonym."""
    status: Literal["propozycja"] = "propozycja"
    zrodlo: Literal["reguly", "llm"]
    regula: str | None = None
    formy: list[str] = Field(default_factory=list)
    cytat: CytatCelu | None = None
    """Tylko podpowiedzi z LLM: źródło z pokryciem w korpusie."""
    oznaczenie: str = OZNACZENIE


class WynikPodpowiedzi(BaseModel):
    osoba_id: str
    proces_id: int | None
    """Proces oceny, z którego pochodzą wskaźniki (ostatni oceniony)."""
    komunikat: str | None = None
    podpowiedzi: list[PodpowiedzCelu]
    zrodlo: Literal["llm", "reguly"] = "reguly"
    """Skąd pochodzą podpowiedzi: z LLM po walidacji albo z reguł (także gdy LLM zawiódł)."""
    dostawca: str | None = None
    tryb: Tryb | None = None
    """Znacznik trybu odpowiedzi LLM; None dla reguł."""
    odrzucone: list[str] = Field(default_factory=list)
    """Powody odrzucenia celów z LLM albo informacja, który dostawca zawiódł (szczegóły w ``llm.jsonl``)."""


def podpowiedzi_regulowe(wynik: WynikRozwoju, poziom_oczekiwan: int) -> list[PodpowiedzCelu]:
    """Obszary rozwojowe (wskaźniki poniżej poziomu oczekiwań, reguły ``rozwoj.yaml``) jako szkice celów."""
    return [
        PodpowiedzCelu(
            nazwa=f"Rozwój: {p.wskaznik}",
            opis=(
                f"Obszar rozwojowy z ostatniej oceny ({p.kompetencja}, poziom {p.poziom})."
                + (f" Proponowane formy: {', '.join(f.nazwa for f in p.formy)}." if p.formy else "")
            ),
            wskaznik_id=p.wskaznik_id,
            wskaznik=p.wskaznik,
            kompetencja=p.kompetencja,
            miernik=f"Wskaźnik oceniony co najmniej na poziomie oczekiwań ({poziom_oczekiwan}) w następnej ocenie.",
            termin=None,
            zrodlo="reguly",
            regula=p.regula,
            formy=[f.nazwa for f in p.formy],
        )
        for p in wynik.propozycje
        if p.typ == "OBSZAR_ROZWOJOWY"
    ]


class BladCelu(Exception):
    """Zakazana operacja. ``kod``: 403 (rola), 409 (status), 422 (dane)."""

    def __init__(self, kod: int, komunikat: str) -> None:
        super().__init__(komunikat)
        self.kod = kod
        self.komunikat = komunikat


# ---------------------------------------------------------------- reguły


KONCOWE: frozenset[str] = frozenset({"osiągnięty", "porzucony"})


def moze_tworzyc(aktor: Aktor, konf: KonfiguracjaCelow) -> None:
    if aktor == "pracownik" and not konf.pracownik_moze_edytowac:
        raise BladCelu(403, "Cele tworzy i zmienia przełożony.")


def zmien_tresc(cel: Cel, tresc: TrescCelu, aktor: Aktor, konf: KonfiguracjaCelow) -> Cel:
    """Zmiana treści przez pracownika przywraca ``propozycja`` (wymaga ponownej akceptacji);
    zmiana przez przełożonego zostawia status. Zamkniętego celu nie zmienia nikt."""
    moze_tworzyc(aktor, konf)
    if cel.status in KONCOWE:
        raise BladCelu(409, f"Cel ma status „{cel.status}” i nie można go zmienić.")
    nowy = cel.model_copy(update=tresc.model_dump())
    # Odrzucona propozycja po poprawce (także bez zmian) wraca do akceptacji z komentarzem przełożonego.
    if cel.status == "odrzucony" or (aktor == "pracownik" and _tresc(nowy) != _tresc(cel)):
        nowy.status, nowy.zgloszono_osiagniecie = "propozycja", False
    return nowy


def zatwierdz(cel: Cel, aktor: Aktor) -> Cel:
    _tylko_przelozony(aktor, "Cel zatwierdza przełożony.")
    if cel.status != "propozycja":
        raise BladCelu(409, f"Zatwierdzić można tylko propozycję, a cel ma status „{cel.status}”.")
    return cel.model_copy(update={"status": "zatwierdzony", "komentarz": None})


def odrzuc(cel: Cel, aktor: Aktor, komentarz: str) -> Cel:
    """Przełożony odrzuca propozycję z komentarzem; pracownik może ją poprawić (wraca ``propozycja``)."""
    _tylko_przelozony(aktor, "Propozycję odrzuca przełożony.")
    if not komentarz.strip():
        raise BladCelu(422, "Odrzucenie wymaga komentarza.")
    if cel.status != "propozycja":
        raise BladCelu(409, f"Odrzucić można tylko propozycję, a cel ma status „{cel.status}”.")
    return cel.model_copy(update={"status": "odrzucony", "komentarz": komentarz.strip()})


def ustaw_status(cel: Cel, aktor: Aktor, docelowy: StatusPostepu) -> Cel:
    """Postęp zatwierdzonego celu. ``w_realizacji`` ustawia każdy z nich. ``osiągnięty``: pracownik
    tylko zgłasza, przełożony potwierdza (także bez zgłoszenia). ``porzucony`` ustawia przełożony."""
    if cel.status in KONCOWE:
        raise BladCelu(409, f"Cel ma status „{cel.status}” i jest zamknięty.")
    if docelowy == "porzucony":
        _tylko_przelozony(aktor, "Cel porzuca przełożony.")
        if cel.status not in ("zatwierdzony", "w_realizacji"):
            raise BladCelu(409, f"Porzucić można cel zatwierdzony, a cel ma status „{cel.status}”.")
        return cel.model_copy(update={"status": "porzucony", "zgloszono_osiagniecie": False})
    if docelowy == "w_realizacji":
        if cel.status != "zatwierdzony":
            raise BladCelu(409, f"„W realizacji” może być tylko cel zatwierdzony, a ma status „{cel.status}”.")
        return cel.model_copy(update={"status": "w_realizacji"})
    if cel.status not in ("zatwierdzony", "w_realizacji"):
        raise BladCelu(409, f"Osiągnięcie dotyczy celu zatwierdzonego, a cel ma status „{cel.status}”.")
    if aktor == "pracownik":
        return cel.model_copy(update={"zgloszono_osiagniecie": True})
    return cel.model_copy(update={"status": "osiągnięty", "zgloszono_osiagniecie": False})


def _tylko_przelozony(aktor: Aktor, komunikat: str) -> None:
    if aktor != "przelozony":
        raise BladCelu(403, komunikat)


def _tresc(cel: Cel) -> dict:
    return TrescCelu.model_validate(cel.model_dump()).model_dump()


# ---------------------------------------------------------------- baza

_KOLUMNY = (
    "id, osoba_id, nazwa, opis, wskaznik_id, miernik, termin, status, komentarz,"
    " zgloszono_osiagniecie, autor, utworzono, zmieniono"
)


def _z_wiersza(w: tuple) -> Cel:
    i, o, n, op, wid, m, t, st, kom, zg, a, ut, zm = w
    return Cel(
        id=i, osoba_id=o, nazwa=n, opis=op, wskaznik_id=wid, miernik=m, termin=date.fromisoformat(t),
        status=st, komentarz=kom, zgloszono_osiagniecie=bool(zg), autor=a,
        utworzono=datetime.fromisoformat(ut), zmieniono=datetime.fromisoformat(zm),
    )


def lista(baza: sqlite3.Connection, osoba_id: str) -> list[Cel]:
    return [
        _z_wiersza(w)
        for w in baza.execute(f"SELECT {_KOLUMNY} FROM cele WHERE osoba_id = ? ORDER BY id", (osoba_id,))
    ]


def wczytaj(baza: sqlite3.Connection, cel_id: int) -> Cel | None:
    w = baza.execute(f"SELECT {_KOLUMNY} FROM cele WHERE id = ?", (cel_id,)).fetchone()
    return _z_wiersza(w) if w else None


def utworz(baza: sqlite3.Connection, osoba_id: str, tresc: TrescCelu, autor: str, teraz: datetime) -> Cel:
    with baza:
        kursor = baza.execute(
            "INSERT INTO cele (osoba_id, nazwa, opis, wskaznik_id, miernik, termin, status, komentarz,"
            " zgloszono_osiagniecie, autor, utworzono, zmieniono)"
            " VALUES (?, ?, ?, ?, ?, ?, 'propozycja', NULL, 0, ?, ?, ?)",
            (
                osoba_id, tresc.nazwa, tresc.opis, tresc.wskaznik_id, tresc.miernik, tresc.termin.isoformat(),
                autor, teraz.isoformat(), teraz.isoformat(),
            ),
        )
    return wczytaj(baza, kursor.lastrowid)


def zapisz(baza: sqlite3.Connection, cel: Cel, teraz: datetime) -> Cel:
    with baza:
        baza.execute(
            "UPDATE cele SET nazwa = ?, opis = ?, wskaznik_id = ?, miernik = ?, termin = ?, status = ?,"
            " komentarz = ?, zgloszono_osiagniecie = ?, zmieniono = ? WHERE id = ?",
            (
                cel.nazwa, cel.opis, cel.wskaznik_id, cel.miernik, cel.termin.isoformat(), cel.status,
                cel.komentarz, int(cel.zgloszono_osiagniecie), teraz.isoformat(), cel.id,
            ),
        )
    return wczytaj(baza, cel.id)


def zrzut(cel: Cel | None) -> dict:
    """Postać do dziennika zmian (bez znaczników czasu, które zmieniają się zawsze)."""
    if cel is None:
        return {}
    return cel.model_dump(mode="json", exclude={"utworzono", "zmieniono"})
