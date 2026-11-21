"""Kontrakt LLM: zapytanie z fragmentami korpusu, odpowiedź z cytatami, wpis logu.

Zasada: wejście to wyłącznie fragmenty korpusu z ID, a wyjście musi wskazywać ID
fragmentów i dosłowne cytaty z nich. Odpowiedź z cytatem bez pokrycia jest
odrzucana i system przechodzi do następnego dostawcy (fallback).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ..zrodla.model import Fragment


class Tryb(StrEnum):
    """Znacznik pokazywany użytkownikowi przy każdej odpowiedzi."""

    NA_ZYWO = "NA_ŻYWO"
    ZAPISANE = "ZAPISANE"
    EKSTRAKCYJNE = "EKSTRAKCYJNE"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Zapytanie(_Model):
    """Wejście dla dostawcy.

    ``operacja`` to nazwa dozwolonej operacji ustalona przez wersję (np.
    ``"mapowanie"``, ``"cytaty_dowody"``, ``"diff_przepisow"``, ``"asystent"``).
    ``katalog`` to dozwolone ID wyboru (np. ID kryteriów); pusty = bez wyboru.
    """

    operacja: str
    prompt_wersja: str
    pytanie: str
    fragmenty: list[Fragment]
    katalog: list[str] = Field(default_factory=list)


class Cytat(_Model):
    fragment_id: str
    cytat: str


class Odpowiedz(_Model):
    """Wyjście dostawcy.

    ``tresc`` to opcjonalny tekst ułożony wyłącznie z cytowanych fragmentów
    (np. odpowiedź asystenta). ``wybor`` to ID z ``Zapytanie.katalog``.
    """

    cytaty: list[Cytat]
    wybor: list[str] = Field(default_factory=list)
    tresc: str | None = None


class WynikLlm(_Model):
    """Odpowiedź po walidacji, z informacją, kto ją dał i w jakim trybie."""

    odpowiedz: Odpowiedz
    dostawca: str
    model: str | None
    tryb: Tryb
    odrzuceni: list[str] = Field(
        default_factory=list, description="dostawcy, których odpowiedź odrzucono przed tą"
    )


class WpisLogu(_Model):
    """Log każdego wywołania (także odrzuconego i zakończonego błędem)."""

    czas: datetime
    operacja: str
    dostawca: str
    model: str | None
    prompt_wersja: str
    fragment_ids: list[str]
    tryb: Tryb
    walidacja_ok: bool
    bledy: list[str] = Field(default_factory=list)
    odpowiedz: Odpowiedz | None = None
