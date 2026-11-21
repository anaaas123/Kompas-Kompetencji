"""Kontrakt modułu dostępu: konta demo, role, reguły dostępu, wpis dziennika zmian.

Konta, role i reguły podaje konfiguracja wersji, nie core. Klucze JSON/YAML są po
polsku (``hasło``, ``reguły_dostępu``), pola w Pythonie bez polskich znaków; oba
warianty są przyjmowane na wejściu.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, frozen=True, extra="forbid")


class Konto(_Model):
    """Konto demo z konfiguracji wersji."""

    login: str
    haslo: str = Field(alias="hasło")
    rola: str
    osoba_id: str | None = None


class RegulaDostepu(_Model):
    """Rekord zasobu jest dostępny dla roli, gdy ``rekord[pole]`` równa się polu
    użytkownika albo, gdy jest listą, je zawiera.

    Przykład: przełożony widzi tylko swoich podwładnych::

        zasób: pracownik
        rola: przelozony
        pole: przelozony_id
    """

    zasob: str = Field(alias="zasób")
    rola: str
    pole: str
    pole_uzytkownika: str = Field(default="osoba_id", alias="pole_użytkownika")


class KonfiguracjaRol(_Model):
    """Konta, uprawnienia ról do akcji (``"*"`` = wszystkie) i reguły dostępu."""

    konta: list[Konto]
    uprawnienia: dict[str, list[str]]
    reguly_dostepu: list[RegulaDostepu] = Field(default_factory=list, alias="reguły_dostępu")


class Uzytkownik(_Model):
    """Zalogowany użytkownik, zwracany przez zależność FastAPI."""

    login: str
    rola: str
    osoba_id: str | None = None


class WpisDziennika(_Model):
    """Wpis dziennika zmian: kto, kiedy, co i według której wersji reguł."""

    id: int
    czas: datetime
    autor: str
    zasob: str = Field(alias="zasób")
    zasob_id: str = Field(alias="zasób_id")
    roznica: dict[str, dict] = Field(alias="różnica")
    """``{pole: {"przed": x, "po": y}}``, tylko zmienione pola."""
    wersja_regul: str = Field(alias="wersja_reguł")
