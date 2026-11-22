"""Zawiadomienie o zmianie terminu sporządzenia oceny okresowej."""

from __future__ import annotations

from datetime import date

from kompas_core.pdf import DokumentPdf
from kompas_core.zrodla import SourceRef
from reportlab.pdfbase import pdfmetrics

from .qnt import Pracownik
from .terminy_pierwszej import (
    KonfiguracjaTerminowPierwszej,
    PrzedluzeniePierwszej,
    TerminyPierwszej,
)
from .wzor_druk import _font


class _Pismo(DokumentPdf):
    def __init__(self, nazwa_urzedu: str) -> None:
        super().__init__(stopka=None, font=pdfmetrics.getFont(_font()).face.filename)
        self.akapit(nazwa_urzedu)

    def podpis_oceniajacego(self, etykieta: str, oceniajacy: Pracownik | None) -> None:
        self.podpis(etykieta)
        if oceniajacy:
            self._elementy[-1].keepWithNext = True
            self.akapit(f"{oceniajacy.imie} {oceniajacy.nazwisko}\n{oceniajacy.stanowisko}")

    def _stopka(self, canvas, doc) -> None:
        """Pismo kończy się miejscem na podpis."""


def zawiadomienie_pdf(
    pracownik: Pracownik,
    poprzedni_termin: date,
    nowy_termin: date,
    data_zawiadomienia: date,
    przyczyna: str,
    zrodlo: SourceRef,
    wersja: str,
    *,
    nazwa_urzedu: str,
    oceniajacy: Pracownik | None,
) -> bytes:
    """Przygotuj pismo o zmianie terminu do przekazania ocenianemu."""
    oceniany = {
        "imie_nazwisko": f"{pracownik.imie} {pracownik.nazwisko}",
        "stanowisko": pracownik.stanowisko,
        "komorka": pracownik.komorka,
    }
    pdf = _Pismo(nazwa_urzedu)
    pdf.naglowek("Zawiadomienie o zmianie terminu oceny okresowej")
    pdf.akapit(f"Data pisma {data_zawiadomienia:%d.%m.%Y}")
    pdf.naglowek("Osoba oceniana", poziom=2)
    pdf.akapit("\n".join(oceniany.values()))

    pdf.naglowek("Termin sporządzenia oceny na piśmie", poziom=2)
    pdf.tabela([
        ["Dotychczasowy termin", "Nowy termin"],
        [f"{poprzedni_termin:%d.%m.%Y}", f"{nowy_termin:%d.%m.%Y}"],
    ])
    pdf.naglowek("Przyczyna zmiany", poziom=2)
    pdf.akapit(przyczyna)

    pdf.naglowek("Podstawa zawiadomienia", poziom=2)
    pdf.akapit(
        f"{zrodlo.lokalizator or '§ 8'} rozporządzenia Prezesa Rady Ministrów z dnia "
        "4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych "
        "urzędników służby cywilnej i pracowników służby cywilnej (Dz. U. z 2016 r. poz. 470)."
    )
    if zrodlo.cytat_doslowny:
        cytat = " ".join(zrodlo.cytat_doslowny.split())
        pdf.akapit(f"„{cytat}”")
    pdf.akapit("Kopię zawiadomienia dołącza się do arkusza oceny okresowej.")
    pdf.podpis_oceniajacego("Podpis oceniającego", oceniajacy)
    return pdf.bajty()


_PRZYCZYNY_PIERWSZEJ = {
    "usprawiedliwiona_nieobecnosc": "Usprawiedliwiona nieobecność w pracy ocenianego.",
    "obowiazki_poza_miejscem_pracy": "Wykonywanie obowiązków służbowych poza miejscem pracy.",
    "przedluzenie_umowy": "Przedłużenie okresu trwania umowy o pracę.",
}


def zawiadomienie_pierwszej_pdf(
    pracownik: Pracownik,
    zmiana: PrzedluzeniePierwszej,
    terminy: TerminyPierwszej,
    konf: KonfiguracjaTerminowPierwszej,
    wersja: str,
    *,
    nazwa_urzedu: str,
    oceniajacy: Pracownik | None,
) -> bytes:
    """Pismo do ocenianego i kopia do pierwszego arkusza zgodnie z § 5 ust. 4."""
    stare = terminy.termin_sprawozdania_bazowy_od.data, terminy.termin_sprawozdania_bazowy_do.data
    nowe = terminy.termin_sprawozdania_od.data, terminy.termin_sprawozdania_do.data
    zrodlo = konf.zrodlo_przedluzenia
    przyczyna = konf.zrodlo_przyczyny(zmiana.przyczyna)
    pdf = _Pismo(nazwa_urzedu)
    pdf.naglowek("Zawiadomienie o zmianie terminu złożenia sprawozdania")
    pdf.akapit(f"Data pisma {zmiana.data_zawiadomienia:%d.%m.%Y}")
    pdf.naglowek("Osoba oceniana", poziom=2)
    pdf.akapit(f"{pracownik.imie} {pracownik.nazwisko}\n{pracownik.stanowisko}\n{pracownik.komorka}")
    pdf.tabela([
        ["Okno złożenia sprawozdania", "Od", "Do"],
        ["Dotychczasowe", f"{stare[0]:%d.%m.%Y}", f"{stare[1]:%d.%m.%Y}"],
        ["Nowe", f"{nowe[0]:%d.%m.%Y}", f"{nowe[1]:%d.%m.%Y}"],
    ])
    pdf.naglowek("Przyczyna zmiany", poziom=2)
    opis = _PRZYCZYNY_PIERWSZEJ[zmiana.przyczyna]
    if zmiana.okres_od and zmiana.okres_do:
        opis += f" Okres od {zmiana.okres_od:%d.%m.%Y} do {zmiana.okres_do:%d.%m.%Y}."
    pdf.akapit(opis)
    pdf.akapit(
        f"Podstawa: {przyczyna.lokalizator} oraz {zrodlo.lokalizator} rozporządzenia Prezesa Rady Ministrów "
        "z dnia 23 lipca 2015 r. w sprawie szczegółowych warunków i sposobu dokonywania pierwszej oceny "
        "w służbie cywilnej (Dz. U. z 2015 r. poz. 1144)."
    )
    pdf.akapit("Kopię niniejszego pisma dołącza się do arkusza pierwszej oceny.")
    pdf.podpis_oceniajacego("Podpis bezpośredniego przełożonego", oceniajacy)
    return pdf.bajty()
