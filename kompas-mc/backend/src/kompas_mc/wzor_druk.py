"""Wydruk na oryginalnym wzorze z Dziennika Ustaw: strona wzoru jako tło, dane nadrukowane w jego polach.

Wzory (kompas_mc/wzory/*.pdf) wycina scripts/wzory_z_dziennika_ustaw.py. Wygląd arkusza jest więc 1:1 ze
wzorem z rozporządzenia; aplikacja dopisuje wyłącznie treść pól. Tekst dłuższy niż pole zmniejsza się do
MIN_ROZMIAR, a reszta przechodzi na stronę „ciąg dalszy” na końcu (nic nie jest ucinane).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from kompas_core.pdf import znajdz_font
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

WZORY = Path(__file__).with_name("wzory")
MIN_ROZMIAR = 7.0
INTERLINIA = 1.2

# Krój jak we wzorach (Times New Roman); Liberation Serif ma te same metryki.
KANDYDACI_SZERYF = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "C:/Windows/Fonts/times.ttf",
]


def _font() -> str:
    env = os.environ.get("KOMPAS_PDF_FONT_SZERYF")
    sciezka = next((Path(p) for p in ([env] if env else []) + KANDYDACI_SZERYF if Path(p).is_file()), None)
    sciezka = sciezka or znajdz_font()
    nazwa = "Wzor-" + sciezka.stem.replace(" ", "")
    if nazwa not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(nazwa, str(sciezka)))
    return nazwa


@dataclass(frozen=True)
class Pole:
    """Prostokąt pola na stronie wzoru w punktach PDF (początek układu w lewym dolnym rogu strony)."""

    strona: int
    x0: float
    y0: float
    x1: float
    y1: float
    rozmiar: float = 10.0
    srodek: bool = False


@dataclass(frozen=True)
class Krzyzyk:
    """Znak „X” wstawiany w kratkę wyboru (środek kratki)."""

    strona: int
    x: float
    y: float
    rozmiar: float = 10.0


def _wiersze(tekst: str, font: str, rozmiar: float, szerokosc: float) -> list[str]:
    return [w for akapit in tekst.splitlines() or [""] for w in (simpleSplit(akapit, font, rozmiar, szerokosc) or [""])]


def _wpisz(c: Canvas, pole: Pole, tekst: str, font: str) -> list[str]:
    """Wpisuje tekst w pole; zwraca wiersze, które się nie zmieściły."""
    szer, wys = pole.x1 - pole.x0, pole.y1 - pole.y0
    rozmiar = pole.rozmiar
    wiersze = _wiersze(tekst, font, rozmiar, szer)
    while len(wiersze) * rozmiar * INTERLINIA > wys and rozmiar > MIN_ROZMIAR:
        rozmiar = max(MIN_ROZMIAR, rozmiar - 0.5)
        wiersze = _wiersze(tekst, font, rozmiar, szer)
    miesci = max(1, int(wys // (rozmiar * INTERLINIA)))
    c.setFont(font, rozmiar)
    y = pole.y1 - rozmiar if len(wiersze) > 1 or wys > 2 * rozmiar * INTERLINIA else pole.y0 + (wys - rozmiar) / 2 + 1.5
    for w in wiersze[:miesci]:
        if pole.srodek:
            c.drawCentredString((pole.x0 + pole.x1) / 2, y, w)
        else:
            c.drawString(pole.x0, y, w)
        y -= rozmiar * INTERLINIA
    return wiersze[miesci:]


def wypelnij(
    wzor: str,
    wpisy: Iterable[tuple[Pole, str | None]],
    krzyzyki: Iterable[Krzyzyk] = (),
    *,
    strony: Sequence[int] | None = None,
    nazwy_pol: dict[Pole, str] | None = None,
) -> bytes:
    """Składa wydruk z pliku wzoru ``wzor`` (np. "arkusz_C.pdf"): wybrane ``strony`` (domyślnie wszystkie)
    z nadrukiem ``wpisy`` i ``krzyzyki``. Puste wartości zostają puste, jak niewypełniony wzór."""
    font = _font()
    tlo = PdfReader(WZORY / wzor)
    numery = list(strony) if strony is not None else list(range(len(tlo.pages)))
    wpisy = [(p, t) for p, t in wpisy if t and str(t).strip()]
    krzyzyki = list(krzyzyki)
    nakladka = BytesIO()
    c = Canvas(nakladka, pagesize=A4)
    reszta: list[tuple[str, list[str]]] = []
    for nr in numery:
        for pole, tekst in wpisy:
            if pole.strona == nr:
                nie_zmiescilo = _wpisz(c, pole, str(tekst), font)
                if nie_zmiescilo:
                    c.setFont(font, MIN_ROZMIAR)
                    c.drawRightString(pole.x1, pole.y0 + 1, "(ciąg dalszy na końcu arkusza)")
                    reszta.append(((nazwy_pol or {}).get(pole, "Ciąg dalszy pola"), nie_zmiescilo))
        for k in krzyzyki:
            if k.strona == nr:
                c.setFont(font, k.rozmiar)
                c.drawCentredString(k.x, k.y - k.rozmiar * 0.35, "X")
        c.showPage()
    for nazwa, wiersze in reszta:
        c.setFont(font, 11)
        c.drawString(70, 770, f"{nazwa} (ciąg dalszy)")
        c.setFont(font, 10)
        y = 745
        for w in wiersze:
            if y < 50:
                c.showPage()
                c.setFont(font, 10)
                y = 770
            c.drawString(70, y, w)
            y -= 12
        c.showPage()
    c.save()
    nadruk = PdfReader(BytesIO(nakladka.getvalue()))
    wynik = PdfWriter()
    for i, nr in enumerate(numery):
        strona = wynik.add_page(tlo.pages[nr])
        strona.merge_page(nadruk.pages[i])
    for i in range(len(numery), len(nadruk.pages)):
        wynik.add_page(nadruk.pages[i])
    bufor = BytesIO()
    wynik.write(bufor)
    return bufor.getvalue()


if __name__ == "__main__":
    # Samosprawdzenie: krótki tekst mieści się w polu, długi przechodzi na stronę ciągu dalszego.
    p = Pole(0, 230, 700, 520, 712)
    krotki = wypelnij("arkusz_C.pdf", [(p, "Ministerstwo Cyfryzacji")], strony=[0])
    assert len(PdfReader(BytesIO(krotki)).pages) == 1
    dlugi = wypelnij("arkusz_C.pdf", [(p, "słowo " * 400)], strony=[0], nazwy_pol={p: "Nazwa urzędu"})
    assert len(PdfReader(BytesIO(dlugi)).pages) >= 2
    print("wzor_druk: OK")
