"""Prymitywy PDF (CORE-4, #7): polskie znaki, tabele z polami „X”, podpisy, stopka.

Core nie zna wzorów formularzy. Wersja składa formularz z tych prymitywów.
Silnik: ReportLab (pure Python). Font jest konfigurowalny, bo standardowe fonty
PDF nie mają polskich znaków.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

KANDYDACI_FONTOW = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def hash_tresci(tresc: Any) -> str:
    """sha256 (hex) kanonicznego JSON treści: klucze posortowane, UTF-8.
    Ta sama treść ⇒ ten sam hash, niezależnie od kolejności kluczy."""
    kanon = json.dumps(tresc, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(kanon.encode("utf-8")).hexdigest()


def znajdz_font() -> Path:
    """Pierwszy znaleziony TTF z polskimi znakami (zmienna ``KOMPAS_PDF_FONT``,
    potem DejaVu Sans / Arial w typowych katalogach). ``FileNotFoundError``, gdy brak."""
    env = os.environ.get("KOMPAS_PDF_FONT")
    for p in ([env] if env else []) + KANDYDACI_FONTOW:
        if Path(p).is_file():
            return Path(p)
    raise FileNotFoundError(
        "brak fontu TTF z polskimi znakami; ustaw KOMPAS_PDF_FONT albo przekaż font="
    )


def _zarejestruj(font: Path) -> str:
    nazwa = "Kompas-" + hashlib.sha1(str(font.resolve()).encode()).hexdigest()[:8]
    if nazwa not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(nazwa, str(font)))
    return nazwa


@dataclass(frozen=True)
class Stopka:
    wersja: str
    hash: str
    tekst: str | None = None
    """Dodatkowy tekst, np. „Wydruk do podpisu odręcznego”."""


@dataclass(frozen=True)
class Pole:
    """Komórka do zaznaczenia: kratka z „X”, gdy ``zaznaczone``."""

    zaznaczone: bool = False


Komorka = str | Pole


class _Podpis(Flowable):
    def __init__(self, etykieta: str, font: str, szerokosc: float = 70 * mm) -> None:
        super().__init__()
        self.etykieta, self.font, self.szer = etykieta, font, szerokosc
        self.height = 18 * mm

    def wrap(self, dostepna_szer, dostepna_wys):
        return self.szer, self.height

    def draw(self):
        c = self.canv
        c.setDash(1, 2)
        c.line(0, 6 * mm, self.szer, 6 * mm)
        c.setDash()
        c.setFont(self.font, 8)
        c.drawCentredString(self.szer / 2, 2 * mm, self.etykieta)


class DokumentPdf:
    """Budowniczy dokumentu. Metody dopisują elementy w kolejności wywołań.

        doc = DokumentPdf(stopka=Stopka(wersja="v3", hash=h))
        doc.naglowek("ARKUSZ OCENY")
        doc.akapit("zażółć gęślą jaźń")
        doc.tabela([["Kryterium", "1", "3"], ["Komunikacja", Pole(), Pole(True)]])
        doc.podpis("data i podpis oceniającego")
        doc.zapisz("ocena.pdf")
    """

    def __init__(self, stopka: Stopka, font: str | Path | None = None) -> None:
        self.stopka = stopka
        self.font = _zarejestruj(Path(font) if font else znajdz_font())
        self._elementy: list[Flowable] = []
        self._styl = ParagraphStyle("tekst", fontName=self.font, fontSize=10, leading=13)
        self._styl_komorki = ParagraphStyle("komorka", parent=self._styl, fontSize=9, leading=11)

    def _p(self, tekst: str, styl: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(tekst).replace("\n", "<br/>"), styl)

    def naglowek(self, tekst: str, poziom: int = 1) -> None:
        rozmiar = {1: 15, 2: 12}.get(poziom, 11)
        styl = ParagraphStyle(
            f"h{poziom}", parent=self._styl, fontSize=rozmiar, leading=rozmiar * 1.3,
            spaceBefore=6, spaceAfter=6,
        )
        self._elementy.append(self._p(tekst, styl))

    def akapit(self, tekst: str) -> None:
        self._elementy.append(self._p(tekst, self._styl))
        self._elementy.append(Spacer(1, 4))

    def tabela(
        self, wiersze: Sequence[Sequence[Komorka]], szerokosci: Sequence[float] | None = None
    ) -> None:
        """Pierwszy wiersz to nagłówek. ``szerokosci`` w punktach."""
        dane = []
        pola: list[tuple[int, int]] = []
        for r, wiersz in enumerate(wiersze):
            rzad = []
            for k, kom in enumerate(wiersz):
                if isinstance(kom, Pole):
                    pola.append((k, r))
                    rzad.append("X" if kom.zaznaczone else "")
                else:
                    rzad.append(self._p(str(kom), self._styl_komorki))
            dane.append(rzad)
        styl = [
            ("FONTNAME", (0, 0), (-1, -1), self.font),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ] + [("ALIGN", p, p, "CENTER") for p in pola]
        t = Table(dane, colWidths=list(szerokosci) if szerokosci else None, repeatRows=1)
        t.hAlign = "LEFT"
        t.setStyle(TableStyle(styl))
        self._elementy += [t, Spacer(1, 8)]

    def podpis(self, etykieta: str) -> None:
        """Linia na podpis odręczny z etykietą pod spodem."""
        self._elementy.append(_Podpis(etykieta, self.font))

    def _stopka(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(self.font, 7)
        s = self.stopka
        linia = f"Wersja {s.wersja} · SHA-256 {s.hash} · strona {doc.page}"
        canvas.drawString(doc.leftMargin, 10 * mm, linia)
        if s.tekst:
            canvas.drawString(doc.leftMargin, 13.5 * mm, s.tekst)
        canvas.restoreState()

    def bajty(self) -> bytes:
        bufor = io.BytesIO()
        doc = SimpleDocTemplate(
            bufor, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=18 * mm, bottomMargin=22 * mm,
        )
        doc.build(list(self._elementy), onFirstPage=self._stopka, onLaterPages=self._stopka)
        return bufor.getvalue()

    def zapisz(self, plik: str | Path) -> Path:
        plik = Path(plik)
        plik.write_bytes(self.bajty())
        return plik
