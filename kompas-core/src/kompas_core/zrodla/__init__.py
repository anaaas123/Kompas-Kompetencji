"""Moduł źródeł: adnotacje, korpus, ekstrakcja, wyszukiwanie i walidator cytatów."""

from .ekstrakcja import ekstrahuj
from .korpus import Korpus, OpisDokumentu
from .model import (
    ElementAdnotowany,
    Fragment,
    Kategoria,
    Rozbieznosc,
    SourceRef,
    StatusEkstrakcji,
    Trafienie,
    TypZmiany,
    WynikEkstrakcji,
    ZmianaSledzona,
)
from .walidator import (
    BladWalidacji,
    KodBledu,
    WynikWalidacji,
    cytat_w_korpusie,
    cytat_w_tekscie,
    normalizuj,
    waliduj_adnotacje,
    waliduj_elementy,
)

__all__ = [
    "BladWalidacji",
    "ElementAdnotowany",
    "Fragment",
    "Kategoria",
    "KodBledu",
    "Korpus",
    "OpisDokumentu",
    "Rozbieznosc",
    "SourceRef",
    "StatusEkstrakcji",
    "Trafienie",
    "TypZmiany",
    "WynikEkstrakcji",
    "WynikWalidacji",
    "ZmianaSledzona",
    "cytat_w_korpusie",
    "cytat_w_tekscie",
    "ekstrahuj",
    "normalizuj",
    "waliduj_adnotacje",
    "waliduj_elementy",
]
