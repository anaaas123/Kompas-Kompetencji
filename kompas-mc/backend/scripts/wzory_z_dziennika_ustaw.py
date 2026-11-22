"""Wycina strony wzorów arkuszy z rozporządzeń (Dz. U. 2016 poz. 470, Dz. U. 2015 poz. 1144) do kompas_mc/wzory/.

Strona wzoru zostaje taka, jak w Dzienniku Ustaw; usuwane są tylko elementy dziennika, nie wzoru:
nagłówek „Dziennik Ustaw – N – Poz. …” z linią, znak wodny rcl.gov.pl (adnotacja /Watermark) i słowo „WZÓR”
nad wypełnianym arkuszem. Uruchomienie z katalogu repo: uv run python kompas-mc/backend/scripts/wzory_z_dziennika_ustaw.py
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject

REPO = Path(__file__).resolve().parents[3]
MATERIALY = REPO / "materialy mc"
CEL = Path(__file__).resolve().parents[1] / "src" / "kompas_mc" / "wzory"

# (plik wynikowy, rozporządzenie, strony wzoru w PDF Dziennika Ustaw liczone od 1)
WZORY = [
    ("arkusz_B.pdf", MATERIALY / "Ocena okresowa w służbie cywilnej/Rozporządzenie o ocenach okresowych z 2016 r. (3).pdf", range(12, 16)),
    ("arkusz_C.pdf", MATERIALY / "Ocena okresowa w służbie cywilnej/Rozporządzenie o ocenach okresowych z 2016 r. (3).pdf", range(16, 20)),
    ("arkusz_pierwszej.pdf", MATERIALY / "Pierwsza ocena w służbie cywilnej/Rozporządzenie o pierwszej ocenie z 2015 r. (1).pdf", range(5, 8)),
]
# Treść wzoru zaczyna się od białego tła wklejonej strony; wszystko przed nim to nagłówek dziennika.
POCZATEK_WZORU = b"0 0 0 0 k\n/GS1 gs"
SLOWO_WZOR = b"(WZ\\323R)Tj"


def oczysc(writer: PdfWriter, strona) -> None:
    dane = strona.get_contents().get_data()
    start = dane.find(POCZATEK_WZORU)
    if start < 0:
        raise ValueError("Nie znaleziono początku wzoru na stronie Dziennika Ustaw.")
    dane = dane[start:].replace(SLOWO_WZOR, b"")
    tresc = ContentStream(None, writer)
    tresc.set_data(dane)
    strona[NameObject("/Contents")] = writer._add_object(tresc)
    if "/Annots" in strona:
        del strona["/Annots"]


def main() -> None:
    CEL.mkdir(parents=True, exist_ok=True)
    for nazwa, plik, strony in WZORY:
        reader = PdfReader(plik)
        writer = PdfWriter()
        for nr in strony:
            strona = writer.add_page(reader.pages[nr - 1])
            oczysc(writer, strona)
        writer.compress_identical_objects()
        with open(CEL / nazwa, "wb") as f:
            writer.write(f)
        print(nazwa, len(strony), "str.,", (CEL / nazwa).stat().st_size, "B")


if __name__ == "__main__":
    main()
