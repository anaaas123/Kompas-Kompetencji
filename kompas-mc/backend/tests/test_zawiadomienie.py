from datetime import date
from io import BytesIO
import re

import pytest
from kompas_core.pdf import znajdz_font
from kompas_core.zrodla import SourceRef
from pypdf import PdfReader

from kompas_mc.qnt import Pracownik
from kompas_mc.zawiadomienie import zawiadomienie_pdf


def test_zawiadomienie_pdf_pokazuje_zmiane_terminu_i_podstawe():
    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")
    pracownik = Pracownik(
        osoba_id="P-TEST",
        imie="Łucja",
        nazwisko="Żuk",
        stanowisko="Specjalistka",
        komorka="Wydział Organizacji",
        przelozony_id="P-TEST-PRZELOZONY",
        kieruje_pracownikami=False,
        korpus="pracownik_sc",
        data_zatrudnienia=date(2020, 12, 3),
        rodzaj_umowy="nieokreslony",
    )
    cytat = "Kopię pisma dołącza się do arkusza."
    zrodlo = SourceRef(
        doc_id="rozp-2016-okresowe",
        doc_version="2016",
        lokalizator="§ 8",
        strona=2,
        kategoria="PRZEPIS",
        cytat_doslowny=cytat,
    )

    dokument = zawiadomienie_pdf(
        pracownik,
        date(2026, 11, 30),
        date(2026, 12, 14),
        date(2026, 11, 17),
        "Uzasadniony wniosek osoby ocenianej.",
        zrodlo,
        "mc-okresowa-1",
    )

    reader = PdfReader(BytesIO(dokument))
    assert len(reader.pages) == 1
    tekst = " ".join(reader.pages[0].extract_text().split())
    assert "Zawiadomienie o zmianie terminu oceny okresowej" in tekst
    assert "Łucja Żuk" in tekst
    assert "Specjalistka" in tekst
    assert "Wydział Organizacji" in tekst
    assert "Data pisma 17.11.2026" in tekst
    assert "Dotychczasowy termin Nowy termin 30.11.2026 14.12.2026" in tekst
    assert "Uzasadniony wniosek osoby ocenianej." in tekst
    assert "§ 8 rozporządzenia" in tekst
    assert "poz. 470" in tekst
    assert cytat in tekst
    assert "Kopię zawiadomienia dołącza się do arkusza oceny okresowej." in tekst
    assert "Podpis oceniającego" in tekst
    assert "Wydruk do podpisu odręcznego" in tekst
    assert re.search(r"Wersja mc-okresowa-1 · SHA-256 [0-9a-f]{64}", tekst)
