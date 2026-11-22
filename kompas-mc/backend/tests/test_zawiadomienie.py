from datetime import date
from io import BytesIO

import pytest
from kompas_core.pdf import znajdz_font
from kompas_core.zrodla import SourceRef
from pypdf import PdfReader

from kompas_mc.qnt import MockQnt, Pracownik
from kompas_mc.terminy_pierwszej import (
    DaneTerminowPierwszej, KonfiguracjaTerminowPierwszej, PrzedluzeniePierwszej, oblicz_terminy_pierwszej,
)
from kompas_mc.zawiadomienie import zawiadomienie_pdf, zawiadomienie_pierwszej_pdf


@pytest.fixture(autouse=True)
def font_pdf():
    try:
        znajdz_font()
    except FileNotFoundError:
        pytest.skip("brak fontu TTF z polskimi znakami")


def tekst_strony(dokument):
    reader = PdfReader(BytesIO(dokument))
    assert len(reader.pages) == 1
    return " ".join(reader.pages[0].extract_text().split())


def test_zawiadomienie_pdf_pokazuje_zmiane_terminu_i_podstawe():
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
    oceniajacy = pracownik.model_copy(update={
        "osoba_id": pracownik.przelozony_id, "imie": "Jan", "nazwisko": "Król", "stanowisko": "Naczelnik",
    })
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
        nazwa_urzedu="Urząd Testowy", oceniajacy=oceniajacy,
    )

    tekst = tekst_strony(dokument)
    assert tekst.startswith("Urząd Testowy Zawiadomienie o zmianie terminu oceny okresowej")
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
    assert tekst.endswith("Podpis oceniającego Jan Król Naczelnik")
    assert all(fragment not in tekst for fragment in ("Wydruk do podpisu", "Wersja", "SHA-256", "nie są podpisem"))


def test_zawiadomienie_pierwszej_pokazuje_urzad_i_przelozonego(ustawienia):
    qnt = MockQnt.z_pliku(ustawienia.qnt)
    pracownik = qnt.pracownik("P-204")
    konf = KonfiguracjaTerminowPierwszej.z_pliku(ustawienia.terminy_pierwszej)
    zmiana = PrzedluzeniePierwszej(
        przyczyna="usprawiedliwiona_nieobecnosc", data_zawiadomienia=date(2026, 9, 20), nowy_termin=date(2026, 10, 29),
    )
    terminy = oblicz_terminy_pierwszej(pracownik, DaneTerminowPierwszej(
        data_konca_zatrudnienia=pracownik.data_konca_zatrudnienia,
        wyznaczony_termin_sprawozdania=date(2026, 10, 10), przedluzenie=zmiana,
    ), konf)
    tekst = tekst_strony(zawiadomienie_pierwszej_pdf(
        pracownik, zmiana, terminy, konf, konf.wersja,
        nazwa_urzedu="Urząd Testowy", oceniajacy=qnt.pracownik(pracownik.przelozony_id),
    ))
    assert tekst.startswith("Urząd Testowy Zawiadomienie o zmianie terminu złożenia sprawozdania")
    assert tekst.endswith("Podpis bezpośredniego przełożonego Tomasz Wiśniewski-Demo naczelnik wydziału")
