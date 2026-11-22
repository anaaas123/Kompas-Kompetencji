"""Zakończenie oceny okresowej (#72): zapis w procesie, kartoteka (mock QNT) i widok zakończonego procesu."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from .procesy import ProcesOceny
from .qnt import MockQnt, OstatniaOcenaOkresowa, Pracownik


class ZakonczenieOceny(BaseModel):
    """Zakończona ocena okresowa (#72): po zapoznaniu ocenianego z oceną sporządzoną na piśmie (§ 12 rozp. 2016)."""

    proces_id: int
    data_sporzadzenia_oceny: date
    data_zapoznania_z_ocena: date
    wynik: Literal["pozytywna", "negatywna"]
    srednia: str
    oceny_czastkowe: dict[str, int]
    zakonczyl: str
    zakonczono: datetime
    poprzednia_ocena: OstatniaOcenaOkresowa | None = None
    """Kartoteka sprzed zapisu tej oceny: arkusz i wynik zakończonego procesu pokazują ją jako „poprzednią”."""


def zastosuj_zakonczone(baza, qnt: MockQnt) -> None:
    """Przy starcie: zakończone oceny z aplikacji wracają do mocka QNT jako ostatnia ocena (kolejno od najstarszej)."""
    for osoba_id, zapis in baza.execute(
        "SELECT osoba_id, zakonczenie FROM procesy WHERE status = 'ZAKONCZONY' AND sciezka = 'okresowa'"
        " AND zakonczenie IS NOT NULL ORDER BY id"
    ):
        z = ZakonczenieOceny.model_validate_json(zapis)
        qnt.zapisz_ocene_okresowa(osoba_id, OstatniaOcenaOkresowa(
            data=z.data_sporzadzenia_oceny, wynik=z.wynik, oceny_czastkowe=z.oceny_czastkowe,
            data_zapoznania=z.data_zapoznania_z_ocena,
        ))



def pracownik_procesu(baza, pracownik: Pracownik, proces: ProcesOceny) -> Pracownik:
    """Zakończony proces widzi kartotekę z chwili zakończenia: „poprzednia ocena” to ta sprzed tej oceny,
    a nie ona sama (po zakończeniu kartoteka ma już nową ocenę). Proces w toku – kartoteka bieżąca."""
    if proces.status != "ZAKONCZONY":
        return pracownik
    wiersz = baza.execute("SELECT zakonczenie FROM procesy WHERE id = ?", (proces.id,)).fetchone()
    if not wiersz or not wiersz[0]:
        return pracownik
    z = ZakonczenieOceny.model_validate_json(wiersz[0])
    if "poprzednia_ocena" not in z.model_fields_set:
        return pracownik  # zakończenie sprzed zapisu migawki
    return pracownik.model_copy(update={"ostatnia_ocena_okresowa": z.poprzednia_ocena})
