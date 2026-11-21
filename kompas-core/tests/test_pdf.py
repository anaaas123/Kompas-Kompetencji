import io

import pytest
from pypdf import PdfReader

from kompas_core.pdf import DokumentPdf, Pole, Stopka, hash_tresci, znajdz_font

try:
    znajdz_font()
    MA_FONT = True
except FileNotFoundError:
    MA_FONT = False

wymaga_fontu = pytest.mark.skipif(not MA_FONT, reason="brak fontu TTF z polskimi znakami")


def test_hash_tresci_kanoniczny():
    assert hash_tresci({"a": 1, "b": "ż"}) == hash_tresci({"b": "ż", "a": 1})
    assert hash_tresci({"a": 1}) != hash_tresci({"a": 2})
    assert len(hash_tresci([])) == 64


def test_brak_fontu_daje_czytelny_blad(monkeypatch, tmp_path):
    monkeypatch.setenv("KOMPAS_PDF_FONT", str(tmp_path / "brak.ttf"))
    monkeypatch.setattr("kompas_core.pdf.KANDYDACI_FONTOW", [])
    with pytest.raises(FileNotFoundError, match="KOMPAS_PDF_FONT"):
        znajdz_font()


@wymaga_fontu
def test_pdf_z_polskimi_znakami_tabela_podpisem_i_stopka():
    tresc = {"pracownik": "fikcyjny", "kryteria": {"komunikacja": 7}}
    h = hash_tresci(tresc)
    doc = DokumentPdf(stopka=Stopka(wersja="v3", hash=h, tekst="Wydruk do podpisu odręcznego"))
    doc.naglowek("ARKUSZ OCENY — próba")
    doc.akapit("zażółć gęślą jaźń")
    doc.tabela(
        [["Kryterium", "1", "3", "5", "7", "9"],
         ["Komunikacja", Pole(), Pole(), Pole(), Pole(True), Pole()]],
        szerokosci=[200, 30, 30, 30, 30, 30],
    )
    doc.podpis("data i podpis oceniającego")

    czytnik = PdfReader(io.BytesIO(doc.bajty()))
    tekst = "\n".join(s.extract_text() for s in czytnik.pages)
    assert "zażółć gęślą jaźń" in tekst
    assert "ARKUSZ OCENY — próba" in tekst
    assert "Wersja v3" in tekst and h in tekst
    assert "Wydruk do podpisu odręcznego" in tekst
    assert "data i podpis oceniającego" in tekst
    assert "X" in tekst.split("Komunikacja", 1)[1]


@wymaga_fontu
def test_stopka_na_kazdej_stronie(tmp_path):
    doc = DokumentPdf(stopka=Stopka(wersja="v1", hash="abc123"))
    for i in range(120):
        doc.akapit(f"akapit {i}")
    czytnik = PdfReader(doc.zapisz(tmp_path / "dlugi.pdf"))
    assert len(czytnik.pages) > 1
    for s in czytnik.pages:
        assert "SHA-256 abc123" in s.extract_text()
