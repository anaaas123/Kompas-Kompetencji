"""Syntetyczne pliki testowe. Testy core nie używają materiałów konkursowych."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

STRONA_1 = [
    "Art. 81. 1. Pracownik sluzby cywilnej zatrudnio-",
    "nego na czas nieokreslony podlega ocenie okresowej.",
    "2. Ocene sporzadza sie co 24 miesiace.",
    "Art. 83. 1. Odwolanie wnosi sie w terminie 7 dni.",
]
STRONA_2 = [
    "§ 11. 1. Ocena jest negatywna, gdy jedno kryterium ma 1 punkt.",
    "2. Srednia jest liczona ze wszystkich kryteriow.",
]

ZALACZNIK = ["Zalacznik nr 1", "WYKAZ KRYTERIOW", "1. KOMUNIKACJA - opis", "2. KREATYWNOSC - opis"]


def _pdf(sciezka: Path, strony: list[list[str] | None]) -> Path:
    c = canvas.Canvas(str(sciezka), pagesize=A4)
    for linie in strony:
        if linie is None:  # strona bez warstwy tekstowej (sama grafika)
            c.rect(100, 100, 300, 300, fill=1)
        else:
            y = 800
            for linia in linie:
                c.drawString(72, y, linia)
                y -= 16
        c.showPage()
    c.save()
    return sciezka


@pytest.fixture
def pdf_z_tekstem(tmp_path: Path) -> Path:
    return _pdf(tmp_path / "akt.pdf", [STRONA_1, None, STRONA_2, ZALACZNIK])


@pytest.fixture
def pdf_bez_tekstu(tmp_path: Path) -> Path:
    return _pdf(tmp_path / "skan.pdf", [None, None])


_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
DOCUMENT_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {_W}>
<w:body>
  <w:p><w:r><w:t>§ 4. Kryteria obowiązkowe są wspólne.</w:t></w:r></w:p>
  <w:p>
    <w:r><w:t xml:space="preserve">Data oceny: </w:t></w:r>
    <w:del w:id="1" w:author="Kadry" w:date="2024-06-14T10:00:00Z"><w:r><w:delText>14.046.2024</w:delText></w:r></w:del>
    <w:ins w:id="2" w:author="Kadry" w:date="2024-06-14T10:00:00Z"><w:r><w:t>14.06.2024</w:t></w:r></w:ins>
  </w:p>
  <w:tbl>
    <w:tr>
      <w:tc><w:p><w:r><w:t>Kryterium</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Zażółć gęślą jaźń</w:t></w:r></w:p></w:tc>
    </w:tr>
  </w:tbl>
  <w:p/>
</w:body>
</w:document>
"""

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


@pytest.fixture
def docx_ze_zmianami(tmp_path: Path) -> Path:
    sciezka = tmp_path / "arkusz.docx"
    with zipfile.ZipFile(sciezka, "w") as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", DOCUMENT_XML)
    return sciezka


@pytest.fixture
def xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Część II"
    ws["A1"] = "Kryterium"
    ws["B1"] = "Punkty"
    ws["A2"] = "Komunikacja"
    ws["B2"] = 7
    ws["B3"] = 3.3
    ws2 = wb.create_sheet("Wskaźniki")
    ws2["C5"] = "Rzetelność i terminowość"
    sciezka = tmp_path / "ocena.xlsx"
    wb.save(sciezka)
    return sciezka


@pytest.fixture
def manifest(tmp_path: Path, pdf_z_tekstem, docx_ze_zmianami, xlsx, pdf_bez_tekstu) -> Path:
    sciezka = tmp_path / "korpus.yaml"
    sciezka.write_text(
        """dokumenty:
  - {doc_id: ustawa, doc_version: "2024", plik: akt.pdf}
  - {doc_id: arkusz, plik: arkusz.docx}
  - {doc_id: excel, plik: ocena.xlsx}
  - {doc_id: skan, plik: skan.pdf}
""",
        encoding="utf-8",
    )
    return sciezka
