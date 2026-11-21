"""Wersje metodyki sugestii i mapowania 5→3 (#39): tworzenie, zatwierdzanie, przypinanie do ocen.

- Wersja startowa (`sugestia-mc-1`) pochodzi z `konfiguracja/ocena.yaml`.
- Zmiana parametrów tworzy NOWĄ wersję (PROJEKT); istniejących wersji się nie edytuje.
- Zatwierdzenie zapisuje osobę i datę; poprzednia zatwierdzona wersja staje się ZASTĄPIONA.
- Aktywna = najnowsza ZATWIERDZONA, a gdy żadnej nie ma – wersja startowa (z etykietą
  „wymaga zatwierdzenia”). Projekty nie są używane do ocen.
- Proces przypina wersję przy pierwszym zapisie kroku 3 i dalej liczy tylko według niej.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .ocena import KonfiguracjaOceny

Status = Literal["PROJEKT", "ZATWIERDZONA", "ZASTĄPIONA"]
POZIOMY_MODELU = {1, 3, 5, 7, 9}
SKALA_PIERWSZEJ = {3, 5, 7}


class ParametryMetodyki(BaseModel):
    minimalny_udzial_ocenionych: float = Field(gt=0, le=1)
    mapowanie_pierwsza: dict[int, int]

    @field_validator("mapowanie_pierwsza")
    @classmethod
    def _mapowanie(cls, m: dict[int, int]) -> dict[int, int]:
        if set(m) != POZIOMY_MODELU:
            raise ValueError("mapowanie musi obejmować poziomy modelu 1, 3, 5, 7 i 9")
        if not set(m.values()) <= SKALA_PIERWSZEJ:
            raise ValueError("wartości mapowania muszą należeć do skali pierwszej oceny: 3, 5, 7")
        return dict(sorted(m.items()))


class NowaWersja(ParametryMetodyki):
    zmiana: str = Field(min_length=3, description="co i dlaczego się zmienia")


class WersjaMetodyki(ParametryMetodyki):
    id: str
    numer: int
    status: Status
    zmiana: str
    utworzyl: str
    utworzono: datetime
    zatwierdzil: str | None = None
    data_zatwierdzenia: date | None = None

    @property
    def status_etykiety(self) -> str:
        if self.status == "ZATWIERDZONA":
            return f"zatwierdzona: {self.zatwierdzil}, {self.data_zatwierdzenia.isoformat()}"
        return "DECYZJA_PROJEKTOWA – wymaga zatwierdzenia"


class BladMetodyki(ValueError):
    pass


class RejestrMetodyk:
    def __init__(self, baza: sqlite3.Connection, bazowa: KonfiguracjaOceny) -> None:
        self.baza = baza
        self.bazowa = bazowa
        self.prefiks = bazowa.metodyka.id.rsplit("-", 1)[0]  # „sugestia-mc”
        with baza:
            baza.execute(
                "CREATE TABLE IF NOT EXISTS metodyki (id TEXT PRIMARY KEY, numer INTEGER NOT NULL,"
                " dane TEXT NOT NULL)"
            )
            kolumny = {w[1] for w in baza.execute("PRAGMA table_info(procesy)")}
            if "metodyka" not in kolumny:
                baza.execute("ALTER TABLE procesy ADD COLUMN metodyka TEXT")
        if not self.lista():
            self._zapisz(
                WersjaMetodyki(
                    id=bazowa.metodyka.id,
                    numer=1,
                    status="PROJEKT",
                    minimalny_udzial_ocenionych=bazowa.metodyka.minimalny_udzial_ocenionych,
                    mapowanie_pierwsza=bazowa.mapowanie_pierwsza.wartosci,
                    zmiana="Wersja startowa z konfiguracja/ocena.yaml (#31).",
                    utworzyl="konfiguracja",
                    utworzono=datetime.now(UTC),
                )
            )

    # --- odczyt ------------------------------------------------------------------------

    def _zapisz(self, w: WersjaMetodyki) -> None:
        with self.baza:
            self.baza.execute(
                "INSERT OR REPLACE INTO metodyki (id, numer, dane) VALUES (?, ?, ?)",
                (w.id, w.numer, w.model_dump_json()),
            )

    def lista(self) -> list[WersjaMetodyki]:
        return [
            WersjaMetodyki.model_validate_json(d)
            for (d,) in self.baza.execute("SELECT dane FROM metodyki ORDER BY numer")
        ]

    def wersja(self, metodyka_id: str) -> WersjaMetodyki:
        w = self.baza.execute("SELECT dane FROM metodyki WHERE id = ?", (metodyka_id,)).fetchone()
        if w is None:
            raise KeyError(metodyka_id)
        return WersjaMetodyki.model_validate_json(w[0])

    def aktywna(self) -> WersjaMetodyki:
        wersje = self.lista()
        zatwierdzone = [w for w in wersje if w.status == "ZATWIERDZONA"]
        return zatwierdzone[-1] if zatwierdzone else wersje[0]

    # --- zmiany ------------------------------------------------------------------------

    def nowa(self, dane: NowaWersja, autor: str, teraz: datetime | None = None) -> WersjaMetodyki:
        numer = max(w.numer for w in self.lista()) + 1
        w = WersjaMetodyki(
            **dane.model_dump(),
            id=f"{self.prefiks}-{numer}",
            numer=numer,
            status="PROJEKT",
            utworzyl=autor,
            utworzono=teraz or datetime.now(UTC),
        )
        self._zapisz(w)
        return w

    def zatwierdz(self, metodyka_id: str, osoba: str, dzien: date) -> WersjaMetodyki:
        w = self.wersja(metodyka_id)
        if w.status != "PROJEKT":
            raise BladMetodyki(f"wersja {metodyka_id} ma status {w.status}; zatwierdza się tylko projekt")
        for poprzednia in self.lista():
            if poprzednia.status == "ZATWIERDZONA":
                self._zapisz(poprzednia.model_copy(update={"status": "ZASTĄPIONA"}))
        nowa = w.model_copy(update={"status": "ZATWIERDZONA", "zatwierdzil": osoba, "data_zatwierdzenia": dzien})
        self._zapisz(nowa)
        return nowa

    # --- procesy -----------------------------------------------------------------------

    def dla_procesu(self, proces_id: int) -> WersjaMetodyki:
        """Wersja przypięta do procesu, a jeśli jeszcze żadnej – aktywna (bez przypinania)."""
        (m,) = self.baza.execute("SELECT metodyka FROM procesy WHERE id = ?", (proces_id,)).fetchone()
        return self.wersja(m) if m else self.aktywna()

    def przypnij(self, proces_id: int) -> WersjaMetodyki:
        """Przypina aktywną wersję przy pierwszym zapisie; później nic nie zmienia."""
        w = self.dla_procesu(proces_id)
        with self.baza:
            self.baza.execute(
                "UPDATE procesy SET metodyka = ? WHERE id = ? AND metodyka IS NULL", (w.id, proces_id)
            )
        return w

    def konfiguracja(self, w: WersjaMetodyki) -> KonfiguracjaOceny:
        """Konfiguracja kroków 3–5 z parametrami i etykietą danej wersji."""
        b = self.bazowa
        return b.model_copy(
            update={
                "metodyka": b.metodyka.model_copy(
                    update={
                        "id": w.id,
                        "status": w.status_etykiety,
                        "minimalny_udzial_ocenionych": w.minimalny_udzial_ocenionych,
                    }
                ),
                "mapowanie_pierwsza": b.mapowanie_pierwsza.model_copy(
                    update={"wartosci": w.mapowanie_pierwsza}
                ),
            }
        )


def zrzut(w: WersjaMetodyki) -> dict:
    return json.loads(w.model_dump_json())
