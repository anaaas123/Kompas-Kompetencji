"""Kontrakt modułu źródeł: adnotacja źródłowa, fragment korpusu, rozbieżność.

Te typy są wspólnym kontraktem dla wszystkich modułów obu wersji. Klucze JSON/YAML
są po polsku, tak jak w specyfikacji (#2, #3), np. ``cytat_dosłowny``. W Pythonie
pola mają nazwy bez polskich znaków (``cytat_doslowny``); oba warianty są
przyjmowane na wejściu, a na wyjściu (``model_dump(by_alias=True)``) obowiązuje
wariant ze specyfikacji.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Kategoria(StrEnum):
    """Kategoria adnotacji źródłowej.

    ``FUNKCJA_APLIKACJI`` (wersja 1) i ``DECYZJA_PROJEKTOWA`` (wersja MC) to ta sama
    kategoria pod dwiema nazwami: obie wymagają uzasadnienia i zatwierdzającego.
    """

    PRZEPIS = "PRZEPIS"
    OBJASNIENIE_MATERIALU = "OBJAŚNIENIE_MATERIAŁU"
    FUNKCJA_APLIKACJI = "FUNKCJA_APLIKACJI"
    DECYZJA_PROJEKTOWA = "DECYZJA_PROJEKTOWA"
    BRAK_ZRODLA = "BRAK_ŹRÓDŁA"

    @property
    def wymaga_cytatu(self) -> bool:
        return self in (Kategoria.PRZEPIS, Kategoria.OBJASNIENIE_MATERIALU)

    @property
    def wymaga_zatwierdzenia(self) -> bool:
        return self in (Kategoria.FUNKCJA_APLIKACJI, Kategoria.DECYZJA_PROJEKTOWA)


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, frozen=True, extra="forbid")


class SourceRef(_Model):
    """Adnotacja źródłowa elementu treści.

    Reguły kategorii są sprawdzane przy tworzeniu obiektu (``ValueError``):

    - ``PRZEPIS`` i ``OBJAŚNIENIE_MATERIAŁU`` wymagają ``doc_id`` i niepustego
      ``cytat_dosłowny``;
    - ``FUNKCJA_APLIKACJI`` / ``DECYZJA_PROJEKTOWA`` wymagają ``uzasadnienie``
      i ``zatwierdził``;
    - ``BRAK_ŹRÓDŁA`` nie ma wymagań; ``uzasadnienie`` opisuje, czego brakuje.

    To, czy cytat występuje w korpusie, sprawdza dopiero walidator
    (``kompas_core.zrodla.walidator``).
    """

    doc_id: str | None = None
    doc_version: str | None = None
    lokalizator: str | None = Field(
        default=None, description='np. "rozp. § 11 ust. 1 pkt 3", "Arkusz1!B7"'
    )
    strona: int | None = None
    cytat_doslowny: str | None = Field(default=None, alias="cytat_dosłowny")
    kategoria: Kategoria
    uzasadnienie: str | None = None
    zatwierdzil: str | None = Field(default=None, alias="zatwierdził")
    data_zatwierdzenia: date | None = None

    @model_validator(mode="after")
    def _reguly_kategorii(self) -> SourceRef:
        k = self.kategoria
        if k.wymaga_cytatu:
            if not self.doc_id:
                raise ValueError(f"{k.value} wymaga doc_id")
            if not (self.cytat_doslowny and self.cytat_doslowny.strip()):
                raise ValueError(f"{k.value} wymaga cytat_dosłowny")
        if k.wymaga_zatwierdzenia:
            if not (self.uzasadnienie and self.uzasadnienie.strip()):
                raise ValueError(f"{k.value} wymaga uzasadnienia")
            if not (self.zatwierdzil and self.zatwierdzil.strip()):
                raise ValueError(f"{k.value} wymaga zatwierdzającego (zatwierdził)")
        return self


class Rozbieznosc(_Model):
    """Flaga ROZBIEŻNOŚĆ: element ma sprzeczne adnotacje.

    ``zastosowana`` to indeks adnotacji (w ``ElementAdnotowany.adnotacje``), według
    której system działa; ``None`` oznacza, że decyzja jeszcze nie zapadła.
    """

    opis: str
    zastosowana: int | None = None
    uzasadnienie: str | None = None


class ElementAdnotowany(_Model):
    """Dowolny element treści (reguła, kryterium, oświadczenie, węzeł) z adnotacjami.

    Element bez adnotacji nie przechodzi walidacji. ``rozbieznosc`` wolno ustawić
    tylko przy co najmniej dwóch adnotacjach.
    """

    id: str
    adnotacje: list[SourceRef] = Field(default_factory=list)
    rozbieznosc: Rozbieznosc | None = Field(default=None, alias="rozbieżność")

    @model_validator(mode="after")
    def _rozbieznosc(self) -> ElementAdnotowany:
        r = self.rozbieznosc
        if r is not None:
            if len(self.adnotacje) < 2:
                raise ValueError("ROZBIEŻNOŚĆ wymaga co najmniej dwóch adnotacji")
            if r.zastosowana is not None and not 0 <= r.zastosowana < len(self.adnotacje):
                raise ValueError("ROZBIEŻNOŚĆ.zastosowana wskazuje nieistniejącą adnotację")
        return self


class TypZmiany(StrEnum):
    WSTAWKA = "WSTAWKA"
    USUNIECIE = "USUNIĘCIE"


class ZmianaSledzona(_Model):
    """Śledzona zmiana w DOCX (w:ins / w:del), raportowana osobno od tekstu."""

    typ: TypZmiany
    tekst: str
    autor: str | None = None
    data: str | None = None


class Fragment(_Model):
    """Fragment korpusu: najmniejsza jednostka, do której odwołuje się cytat.

    ``id`` jest stabilne dla tego samego pliku: ``{doc_id}@{doc_version}#{nr}``
    (bez ``@...``, gdy wersja nie jest podana).

    ``tekst`` to tekst po przyjęciu śledzonych zmian (wstawki są, usunięć nie ma).
    ``zmiany`` wymienia śledzone zmiany osobno.
    """

    id: str
    doc_id: str
    doc_version: str | None = None
    lokalizator: str | None = None
    strona: int | None = None
    tekst: str
    zmiany: list[ZmianaSledzona] = Field(default_factory=list)


class StatusEkstrakcji(StrEnum):
    OK = "OK"
    BRAK_TEKSTU = "BRAK_TEKSTU"
    """PDF (lub jego strona) bez warstwy tekstowej. Nie ma OCR."""
    NIEOBSLUGIWANY = "NIEOBSŁUGIWANY"
    BLAD = "BŁĄD"


class WynikEkstrakcji(_Model):
    """Wynik ekstrakcji jednego pliku. Problemy nie są pomijane po cichu."""

    doc_id: str
    doc_version: str | None = None
    plik: str
    status: StatusEkstrakcji
    fragmenty: list[Fragment] = Field(default_factory=list)
    strony_bez_tekstu: list[int] = Field(default_factory=list)
    komunikat: str | None = None


class Trafienie(_Model):
    """Wynik wyszukiwania BM25."""

    fragment_id: str
    wynik: float
    fragment: Fragment
