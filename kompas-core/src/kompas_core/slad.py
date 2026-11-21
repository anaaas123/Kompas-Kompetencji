"""Reguły źródłowe i ślad wspólny dla kalendarza i skali ocen."""

from dataclasses import dataclass

from .zrodla import SourceRef


@dataclass(frozen=True, slots=True)
class Regula:
    """Identyfikator reguły w konfiguracji wersji i jej adnotacja."""

    id: str
    zrodlo: SourceRef


@dataclass(frozen=True, slots=True)
class KrokObliczenia:
    """Opis wykonanego kroku razem ze źródłem użytej reguły."""

    regula: Regula
    opis: str
