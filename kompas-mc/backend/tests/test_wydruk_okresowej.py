"""Geometria nadruku względem oryginalnych ramek i słów załączników nr 3 i 4."""

import subprocess
from collections import Counter, defaultdict
from datetime import date, timedelta
from shutil import which
from xml.etree import ElementTree

import pytest
from pypdf import PdfReader

from kompas_mc.arkusz_pdf import arkusz_pdf
from kompas_mc.arkusze import WzoryArkuszy
from kompas_mc.wzor_druk import WZORY


def _slowa(pdf):
    xml = ElementTree.fromstring(subprocess.check_output(["pdftotext", "-bbox", pdf, "-"]))
    for strona in xml.findall(".//{*}page"):
        wys = float(strona.get("height"))
        yield Counter(
            (w.text, (float(w.get("xMin")), wys - float(w.get("yMax")),
                      float(w.get("xMax")), wys - float(w.get("yMin"))))
            for w in strona.findall(".//{*}word")
        )


def _komorki(strona):
    """Krawędzie pionowe z wektorowego tła tworzą kolejne wiersze i kolumny."""
    krawedzie = defaultdict(list)
    szary = None
    for args, op in strona.get_contents().operations:
        if op == b"g":
            szary = float(args[0])
        if op == b"re" and szary == 0:
            x, y, szer, wys = map(float, args)
            if szer < 2 and wys > 4:
                krawedzie[round(y + wys, 1)].append((x, y))
    wynik = []
    for gora, brzegi in sorted(krawedzie.items(), reverse=True):
        brzegi.sort()
        wynik.append([(lewy, dol, prawy, gora) for (lewy, dol), (prawy, _) in zip(brzegi, brzegi[1:])])
    return wynik


def _adresy(tabele, dane, wzor, litera):
    """Adresy z formularza: strona, wiersz i kolumna. Brak zależności od mapy nadruku."""
    adresy = {}

    def pole(klucz, s, w, k, zakres_x=None):
        x0, y0, x1, y1 = tabele[s][w][k]
        if zakres_x:
            x0, x1 = zakres_x
        adresy[klucz] = (s, (x0, y0, x1, y1))

    def osoba(klucz, s, w):
        for i, p in enumerate(("imie", "nazwisko", "komorka_organizacyjna", "stanowisko")):
            pole(f"{klucz}.{p}", s, w + i, 1)

    def podpis(klucz, s, w, kolumny):
        for p, granice in zip(("miejscowosc", "data", "imie_nazwisko_lub_pieczatka"), kolumny):
            pole(f"{klucz}.{p}", s, w, 0, granice)

    pole("nazwa_urzedu", 0, 0, 1)
    osoba("oceniany", 0, 1)
    osoba("oceniajacy.czesc_I", 0, 5)
    for i in range(3):
        pole(f"kryterium_dodatkowe.{i + 1}", 0, 10 + i, 1)
    pole("termin_sporzadzenia_oceny", 0, 13, 2)
    podpis("potwierdzenie_kryteriow.oceniajacy", 0, 16, [(99, 198), (250, 349)])
    podpis("potwierdzenie_kryteriow.oceniany", 0, 19, [(99, 198), (250, 349)])
    pole("rozmowa_oceniajaca.data", 1, 0, 1)
    pole("okres_oceny.od", 1, 1, 2)
    pole("okres_oceny.do", 1, 1, 4)
    skala = list(map(str, wzor.zakres_punktow))
    for i in range(5):
        klucz = f"ocena_obowiazkowa.{i + 1}"
        pole(klucz, 1, 5 + i, 1 + skala.index(dane[klucz]))
    for i in range(3):
        klucz = f"ocena_dodatkowa.{i + 1}"
        pole(f"{klucz}.kryterium", 1, 11 + i, 0)
        pole(f"{klucz}.punkty", 1, 11 + i, 1 + skala.index(dane[f"{klucz}.punkty"]))
    pole("srednia", 1, 14, 1)
    poziomy = next(p.warianty for s in wzor.sekcje for p in s.pola if p.id == "poziom")
    pole("poziom", 1, 16 + poziomy.index(dane["poziom"]), 0)
    pole("wynik", 1, 21, 2 if dane["wynik"] == "POZYTYWNA" else 4)
    pole("uzasadnienie", 2, 0, 0)
    pole("wnioski_iprz", 2, 1, 0)
    for k, p in enumerate(("wynik", "poziom", "data")):
        pole(f"poprzednia_ocena.{p}", 2, 2, 2 * k + 1)
    pole("wniosek_o_stopien.status", 2, 3, {"TAK": 1, "NIE": 3, "NIE DOTYCZY": 5}[dane["wniosek_o_stopien.status"]])
    osoba("oceniajacy.czesc_II", 2, 4)
    podpis("dokonanie_oceny.oceniajacy", 2, 8, [(99, 198), (250, 349)])
    podpis("zapoznanie.oceniany", 2, 11, [(80, 179), (193, 292), (305, 404)])
    for i, p in enumerate(("imie", "nazwisko", "rok_mianowania", "stopien_sluzbowy", "data_przyznania_stopnia")):
        pole(f"urzednik.{p}", 3, i, 1)
    pole("wniosek_o_stopien.imie_nazwisko", 3, 6, 0)
    pole("wniosek_o_stopien.stopien", 3, 6, 0, (77, 104))
    pole("wniosek_o_stopien.umotywowanie", 3, 8, 0)
    kolumny = [(87, 181), (206, 301), (319, 414)] if litera == "B" else [(92, 187), (226, 320), (346, 441)]
    podpis("wniosek_o_stopien.oceniajacy", 3, 9, kolumny)
    return adresy


@pytest.mark.skipif(which("pdftotext") is None, reason="Test geometrii wymaga pdftotext (Poppler)")
@pytest.mark.parametrize("litera,przesuniecie", [("B", 0), ("C", 1), ("C", 2)])
def test_wpisy_i_krzyzyki_w_komorkach_wzoru(ustawienia, tmp_path, litera, przesuniecie):
    wzor = WzoryArkuszy.z_pliku(ustawienia.wzory_arkuszy).dla(litera)
    tlo = WZORY / f"arkusz_{litera}.pdf"
    dane, oczekiwane = {}, {}
    for i, p in enumerate(p for s in wzor.sekcje for p in s.pola):
        if p.rodzaj in {"tekst_staly", "miejsce_na_podpis_odreczny"}:
            dane[p.id] = "NIEDRUKOWANE"
        elif p.rodzaj == "wybor_punktow" or p.id in {"poziom", "wynik", "wniosek_o_stopien.status"}:
            dane[p.id] = str(p.warianty[(i + przesuniecie) % len(p.warianty)])
            oczekiwane[p.id] = "X"
        elif p.rodzaj == "data":
            dzien = date(2026, 1, 1) + timedelta(days=i)
            dane[p.id] = dzien.isoformat()
            oczekiwane[p.id] = dzien.strftime("%d.%m.%Y")
        else:
            dane[p.id] = oczekiwane[p.id] = "IV" if p.id == "wniosek_o_stopien.stopien" else f"Pole{i}"
    wynik = tmp_path / "wydruk.pdf"
    wynik.write_bytes(arkusz_pdf(wzor.model_dump(), dane, drukuj_czesc_iii=True, wersja="demo"))
    adresy = _adresy([_komorki(p) for p in PdfReader(tlo).pages], dane, wzor, litera)
    assert adresy.keys() == oczekiwane.keys()
    for nr, (zrodlo, wydruk) in enumerate(zip(_slowa(tlo), _slowa(wynik), strict=True)):
        assert not (zrodlo - wydruk), "Zniknęły słowa wzoru"
        pozostale = list((wydruk - zrodlo).elements())
        for klucz, (s, (x0, y0, x1, y1)) in adresy.items():
            if s != nr:
                continue
            pasujace = [(t, box) for t, box in pozostale if t == oczekiwane[klucz]
                        and x0 <= box[0] < box[2] <= x1 and y0 <= box[1] < box[3] <= y1]
            assert len(pasujace) == 1, (klucz, oczekiwane[klucz], (x0, y0, x1, y1), pozostale)
            slowo = pasujace[0]
            pozostale.remove(slowo)
            lewy, dol, prawy, gora = slowo[1]
            for etykieta, (a, b, c, d) in zrodlo:
                # W zdaniu wniosku stopień wpisuje się bezpośrednio na wykropkowanej linii.
                if klucz == "wniosek_o_stopien.stopien" and not etykieta.strip("…."):
                    continue
                assert prawy <= a or lewy >= c or gora <= b or dol >= d, (klucz, etykieta)
        assert pozostale == []


@pytest.mark.skipif(which("pdftotext") is None, reason="Test geometrii wymaga pdftotext (Poppler)")
def test_dlugi_opis_miesci_sie_na_stronie_kontynuacji(ustawienia, tmp_path):
    wzor = WzoryArkuszy.z_pliku(ustawienia.wzory_arkuszy).dla("C")
    slowa = [f"Zadanie{nr:03d}" for nr in range(395)]
    wynik = tmp_path / "dlugi-opis.pdf"
    wynik.write_bytes(arkusz_pdf(wzor.model_dump(), {"uzasadnienie": " ".join(slowa)},
                                 drukuj_czesc_iii=False, wersja="demo"))
    strony = list(_slowa(wynik))
    assert len(strony) == 4
    wszystkie = Counter()
    for strona in strony[2:]:
        wszystkie.update(t for t, _ in strona.elements() if t.startswith("Zadanie"))
    assert wszystkie == Counter(slowa)
    for _, (lewy, _, prawy, _) in strony[3]:
        assert 69 <= lewy < prawy <= 526
