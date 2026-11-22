"""Ekstrakcja tekstu z PDF, DOCX i XLSX do fragmentów korpusu."""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .model import (
    Fragment,
    StatusEkstrakcji,
    TypZmiany,
    WynikEkstrakcji,
    ZmianaSledzona,
)

ROZSZERZENIA = {".pdf", ".docx", ".xlsx"}


def ekstrahuj(
    plik: str | Path, doc_id: str, doc_version: str | None = None, od_strony: int = 1
) -> WynikEkstrakcji:
    """Wyciąga fragmenty z jednego pliku.

    - PDF z warstwą tekstową: strona po stronie; fragment = jednostka redakcyjna
      (Art./§/ustęp/Załącznik albo akapit), ``strona`` ustawiona, ``lokalizator`` z
      ostatnio widzianych oznaczeń. Strony bez tekstu trafiają do
      ``strony_bez_tekstu``; gdy żadna strona nie ma tekstu, ``status = BRAK_TEKSTU``.
      ``od_strony`` pomija wcześniejsze strony (np. obwieszczenie przed tekstem jednolitym),
      także w lokalizatorze.
    - DOCX: fragment = akapit lub komórka tabeli; śledzone zmiany w ``Fragment.zmiany``.
    - XLSX: fragment = niepusta komórka, ``lokalizator = "Arkusz!A1"``.
    - Inne rozszerzenia: ``status = NIEOBSŁUGIWANY`` (``Thumbs.db`` itp.).
    """
    sciezka = Path(plik)
    baza = dict(doc_id=doc_id, doc_version=doc_version, plik=str(sciezka))
    rozszerzenie = sciezka.suffix.lower()
    if rozszerzenie not in ROZSZERZENIA:
        return WynikEkstrakcji(
            **baza,
            status=StatusEkstrakcji.NIEOBSLUGIWANY,
            komunikat=f"pominięto plik typu {rozszerzenie or sciezka.name}",
        )
    nowy = _Numerator(doc_id, doc_version)
    try:
        if rozszerzenie == ".pdf":
            return _pdf(sciezka, baza, nowy, od_strony)
        if rozszerzenie == ".docx":
            return _docx(sciezka, baza, nowy)
        return _xlsx(sciezka, baza, nowy)
    except Exception as e:  # noqa: BLE001 - błąd pliku raportujemy, nie przerywamy korpusu
        return WynikEkstrakcji(
            **baza, status=StatusEkstrakcji.BLAD, komunikat=f"{type(e).__name__}: {e}"
        )


class _Numerator:
    """Nadaje fragmentom stabilne ID ``{doc_id}@{doc_version}#{nr}``."""

    def __init__(self, doc_id: str, doc_version: str | None) -> None:
        self.doc_id, self.doc_version = doc_id, doc_version
        self.prefiks = f"{doc_id}@{doc_version}" if doc_version else doc_id
        self.nr = 0

    def __call__(self, tekst: str, **pola) -> Fragment:
        self.nr += 1
        return Fragment(
            id=f"{self.prefiks}#{self.nr}",
            doc_id=self.doc_id,
            doc_version=self.doc_version,
            tekst=tekst,
            **pola,
        )


# --- lokalizator jednostek redakcyjnych (Art., §, ust., Załącznik) ---------------

_RE_ZAL = re.compile(r"^Za[łl][ąa]cznik(?:\s+nr)?\s+(\d+[a-z]?)", re.IGNORECASE)
_RE_ART = re.compile(r"^Art\.\s*(\d+[a-z]*)\.?\s*(.*)$")
_RE_PAR = re.compile(r"^§\s*(\d+[a-z]*)\.?\s*(.*)$")
_RE_UST = re.compile(r"^(\d+[a-z]*)\.\s+\S")


class _Lokalizator:
    """Śledzi bieżącą jednostkę redakcyjną na podstawie początków wierszy."""

    def __init__(self) -> None:
        self.zal: str | None = None
        self.art: str | None = None
        self.par: str | None = None
        self.ust: str | None = None

    def wiersz(self, linia: str) -> bool:
        """Aktualizuje stan; zwraca True, gdy wiersz rozpoczyna nową jednostkę."""
        linia = linia.strip()
        if m := _RE_ZAL.match(linia):
            self.zal, self.art, self.par, self.ust = m.group(1), None, None, None
            return True
        if m := _RE_ART.match(linia):
            self.art, self.par, self.ust = m.group(1), None, None
            self._ust_w_reszcie(m.group(2))
            return True
        if m := _RE_PAR.match(linia):
            self.par, self.ust = m.group(1), None
            self._ust_w_reszcie(m.group(2))
            return True
        if (self.art or self.par or self.zal) and (m := _RE_UST.match(linia)):
            self.ust = m.group(1)
            return True
        return False

    def _ust_w_reszcie(self, reszta: str) -> None:
        if m := _RE_UST.match(reszta):
            self.ust = m.group(1)

    @property
    def tekst(self) -> str | None:
        czesci = []
        if self.zal:
            czesci.append(f"zał. {self.zal}")
        if self.art:
            czesci.append(f"art. {self.art}")
        if self.par:
            czesci.append(f"§ {self.par}")
        if self.ust and (self.art or self.par):
            czesci.append(f"ust. {self.ust}")
        elif self.ust and self.zal:
            czesci.append(f"poz. {self.ust}")
        return " ".join(czesci) or None


# --- PDF ---------------------------------------------------------------------------


def _pdf(sciezka: Path, baza: dict, nowy: _Numerator, od_strony: int = 1) -> WynikEkstrakcji:
    from pypdf import PdfReader

    czytnik = PdfReader(str(sciezka))
    lok = _Lokalizator()
    fragmenty: list[Fragment] = []
    bez_tekstu: list[int] = []
    for nr_strony, strona in enumerate(czytnik.pages, start=1):
        if nr_strony < od_strony:
            continue
        tekst = strona.extract_text() or ""
        if not tekst.strip():
            bez_tekstu.append(nr_strony)
            continue
        biezace: list[str] = []
        biezacy_lok = lok.tekst

        def zamknij() -> None:
            if any(l.strip() for l in biezace):
                fragmenty.append(
                    nowy("\n".join(biezace).strip(), lokalizator=biezacy_lok, strona=nr_strony)
                )

        for linia in tekst.splitlines():
            if lok.wiersz(linia):
                zamknij()
                biezace, biezacy_lok = [], lok.tekst
            biezace.append(linia)
        zamknij()

    liczba = max(len(czytnik.pages) - od_strony + 1, 0)
    if liczba and len(bez_tekstu) == liczba:
        return WynikEkstrakcji(
            **baza,
            status=StatusEkstrakcji.BRAK_TEKSTU,
            strony_bez_tekstu=bez_tekstu,
            komunikat="brak tekstu: PDF nie ma warstwy tekstowej (OCR nie jest wykonywany)",
        )
    komunikat = None
    if bez_tekstu:
        komunikat = f"brak tekstu na stronach: {', '.join(map(str, bez_tekstu))}"
    return WynikEkstrakcji(
        **baza,
        status=StatusEkstrakcji.OK,
        fragmenty=fragmenty,
        strony_bez_tekstu=bez_tekstu,
        komunikat=komunikat,
    )


# --- DOCX --------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx(sciezka: Path, baza: dict, nowy: _Numerator) -> WynikEkstrakcji:
    with zipfile.ZipFile(sciezka) as z:
        korzen = ET.fromstring(z.read("word/document.xml"))
    cialo = korzen.find(f"{_W}body")
    lok = _Lokalizator()
    fragmenty: list[Fragment] = []
    nr_tabeli = 0
    for el in list(cialo) if cialo is not None else []:
        if el.tag == f"{_W}p":
            tekst, zmiany = _akapit(el)
            if not tekst.strip() and not zmiany:
                continue
            lok.wiersz(tekst.strip().split("\n", 1)[0])
            fragmenty.append(nowy(tekst.strip(), lokalizator=lok.tekst, zmiany=zmiany))
        elif el.tag == f"{_W}tbl":
            nr_tabeli += 1
            for w, wiersz in enumerate(el.iter(f"{_W}tr"), start=1):
                for k, komorka in enumerate(wiersz.findall(f"{_W}tc"), start=1):
                    teksty, zmiany = [], []
                    for p in komorka.iter(f"{_W}p"):
                        t, zm = _akapit(p)
                        teksty.append(t)
                        zmiany.extend(zm)
                    tekst = "\n".join(t for t in teksty if t.strip()).strip()
                    if not tekst and not zmiany:
                        continue
                    fragmenty.append(
                        nowy(tekst, lokalizator=f"tabela {nr_tabeli} w{w} k{k}", zmiany=zmiany)
                    )
    return WynikEkstrakcji(**baza, status=StatusEkstrakcji.OK, fragmenty=fragmenty)


def _akapit(p: ET.Element) -> tuple[str, list[ZmianaSledzona]]:
    """Tekst akapitu po przyjęciu zmian i lista śledzonych zmian."""
    tekst: list[str] = []
    zmiany: list[ZmianaSledzona] = []

    def zmiana(el: ET.Element, typ: TypZmiany) -> None:
        tag_tekstu = f"{_W}delText" if typ is TypZmiany.USUNIECIE else f"{_W}t"
        tresc = "".join(t.text or "" for t in el.iter(tag_tekstu))
        if tresc:
            zmiany.append(
                ZmianaSledzona(
                    typ=typ, tekst=tresc, autor=el.get(f"{_W}author"), data=el.get(f"{_W}date")
                )
            )

    def idz(el: ET.Element, usuniete: bool) -> None:
        for dziecko in el:
            tag = dziecko.tag
            if tag == f"{_W}ins":
                zmiana(dziecko, TypZmiany.WSTAWKA)
                idz(dziecko, usuniete)
            elif tag == f"{_W}del":
                zmiana(dziecko, TypZmiany.USUNIECIE)
                idz(dziecko, True)
            elif tag == f"{_W}t" and not usuniete:
                tekst.append(dziecko.text or "")
            elif tag == f"{_W}tab" and not usuniete:
                tekst.append("\t")
            elif tag in (f"{_W}br", f"{_W}cr") and not usuniete:
                tekst.append("\n")
            elif tag in (f"{_W}pPr", f"{_W}rPr"):
                continue  # właściwości (w tym zmiany formatowania) nie są tekstem
            else:
                idz(dziecko, usuniete)

    idz(p, False)
    return "".join(tekst), zmiany


# --- XLSX --------------------------------------------------------------------------


def _xlsx(sciezka: Path, baza: dict, nowy: _Numerator) -> WynikEkstrakcji:
    from openpyxl import load_workbook

    formuly = load_workbook(sciezka, data_only=False)
    wartosci = load_workbook(sciezka, data_only=True)
    fragmenty: list[Fragment] = []
    for arkusz in formuly.worksheets:
        arkusz_w = wartosci[arkusz.title]
        for wiersz in arkusz.iter_rows():
            for komorka in wiersz:
                if komorka.value is None:
                    continue
                wartosc = arkusz_w[komorka.coordinate].value
                if wartosc is None:  # formuła bez zapisanej wartości
                    wartosc = komorka.value
                tekst = _jako_tekst(wartosc)
                if not tekst.strip():
                    continue
                fragmenty.append(nowy(tekst, lokalizator=f"{arkusz.title}!{komorka.coordinate}"))
    return WynikEkstrakcji(**baza, status=StatusEkstrakcji.OK, fragmenty=fragmenty)


def _jako_tekst(wartosc: object) -> str:
    if isinstance(wartosc, datetime):
        return wartosc.date().isoformat() if wartosc.time() == datetime.min.time() else wartosc.isoformat()
    if isinstance(wartosc, date):
        return wartosc.isoformat()
    if isinstance(wartosc, float) and wartosc.is_integer():
        return str(int(wartosc))
    return str(wartosc)
