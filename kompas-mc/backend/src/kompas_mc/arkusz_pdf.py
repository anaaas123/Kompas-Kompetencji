"""Wydruk arkuszy oceny okresowej B i C według załączników nr 3 i 4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from io import BytesIO
from typing import Any

from kompas_core.pdf import DokumentPdf, Pole, Stopka, hash_tresci
from reportlab.lib.colors import black
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, TableStyle

from .arkusze import KOMUNIKAT_PODPIS


_LITERY = {"okresowa_b": "B", "okresowa_c": "C"}
_PRZEDZIALY_SREDNIEJ = (
    "od 1 punktu do 2 punktów",
    "powyżej 2 punktów do 4 punktów",
    "powyżej 4 punktów do 6 punktów",
    "powyżej 6 punktów do 8 punktów",
    "powyżej 8 punktów do 9 punktów",
)
_LINIA = "........................"
_PUSTE_POLE = "\N{NO-BREAK SPACE}"


class _Arkusz(DokumentPdf):
    def __init__(
        self, wzor: Mapping[str, Any], wartosci: Mapping[str, str | None], stopka: Stopka
    ) -> None:
        super().__init__(stopka)
        self.wartosci = wartosci
        self.pola = {pole["id"]: pole for sekcja in wzor["sekcje"] for pole in sekcja["pola"]}
        self.przypisy = wzor["przypisy"]
        self.punkty = wzor["zakres_punktow"]
        self._styl_przypisu = ParagraphStyle(
            "przypis_arkusza", parent=self._styl, fontSize=7.5, leading=9, spaceAfter=2
        )
        self._styl_opisu = ParagraphStyle(
            "opis_arkusza", parent=self._styl, leftIndent=3, rightIndent=3,
            borderColor=black, borderWidth=0.5, borderPadding=3,
        )

    def naglowek(self, tekst: str, poziom: int = 1) -> None:
        super().naglowek(tekst, poziom)
        self._elementy[-1].keepWithNext = True

    def tabela(
        self,
        wiersze: Sequence[Sequence[str | Pole]],
        szerokosci: Sequence[float] | None = None,
    ) -> None:
        # Puste wiersze pozostawiają miejsce na wpis. Odstępy mieszczą przypisy na tej samej stronie.
        dane = [[komorka if komorka != "" else _PUSTE_POLE for komorka in wiersz] for wiersz in wiersze]
        super().tabela(dane, szerokosci)
        tabela = self._elementy[-2]
        tabela.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        self._elementy[-1] = Spacer(1, 5)

    def nowa_strona(self) -> None:
        self._elementy.append(PageBreak())

    def bajty(self) -> bytes:
        # Dokument pobrany przed rejestracją i zapisany przez mock EZD ma te same bajty.
        bufor = BytesIO()
        pdf = SimpleDocTemplate(
            bufor, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=18 * mm, bottomMargin=22 * mm, invariant=True,
        )
        pdf.build(list(self._elementy), onFirstPage=self._stopka, onLaterPages=self._stopka)
        return bufor.getvalue()

    def etykieta(self, klucz: str) -> str:
        pole = self.pola[klucz]
        przypisy = "".join(f" [{nr}]" for nr in pole.get("przypisy", ()))
        return pole["etykieta"] + przypisy

    def wartosc(self, klucz: str) -> str:
        wartosc = self.wartosci.get(klucz) or ""
        if wartosc and self.pola[klucz]["rodzaj"] == "data":
            return date.fromisoformat(wartosc).strftime("%d.%m.%Y")
        return wartosc

    def przypisy_strony(self, od: int, do: int) -> None:
        self._elementy.append(Spacer(1, 9))
        for numer in range(od, do + 1):
            tresc = self.przypisy[str(numer)]
            self._elementy.append(self._p(f"{numer}) {tresc}", self._styl_przypisu))

    def pola_osoby(self, tytul: str, prefiks: str, pola: tuple[str, ...]) -> None:
        klucze = [f"{prefiks}.{pole}" for pole in pola]
        self.tabela(
            [[tytul, ""], *[[self.etykieta(klucz), self.wartosc(klucz)] for klucz in klucze]],
            (175, 305),
        )

    def dane_osoby(self, tytul: str, prefiks: str) -> None:
        self.pola_osoby(tytul, prefiks, ("imie", "nazwisko", "komorka_organizacyjna", "stanowisko"))

    def podpis_osoby(self, prefiks: str) -> None:
        klucze = [f"{prefiks}.miejscowosc", f"{prefiks}.data"]
        imie_lub_pieczatka = f"{prefiks}.imie_nazwisko_lub_pieczatka"
        if imie_lub_pieczatka in self.pola:
            klucze.append(imie_lub_pieczatka)
        podpis = f"{prefiks}.podpis"
        szerokosci = (112, 80, 168, 120) if len(klucze) == 3 else (168, 144, 168)
        self.tabela(
            [
                [self.etykieta(klucz) for klucz in (*klucze, podpis)],
                [*["\n" + (self.wartosc(klucz) or _LINIA) for klucz in klucze], "\n" + _LINIA],
            ],
            szerokosci,
        )

    def opis(self, klucz: str, puste_wiersze: int) -> None:
        self.naglowek(self.etykieta(klucz), 3)
        tresc = self.wartosc(klucz) or "\n".join([_PUSTE_POLE] * puste_wiersze)
        self._elementy.append(self._p(tresc, self._styl_opisu))
        self._elementy.append(Spacer(1, 5))

    def wybor(self, klucz: str, *, etykiety: list[str] | None = None) -> None:
        warianty = self.pola[klucz]["warianty"]
        wybrany = self.wartosc(klucz)
        self.tabela(
            [etykiety or warianty, [Pole(wybrany == wariant) for wariant in warianty]],
            [480 / len(warianty)] * len(warianty),
        )

    def czesc_i(self, litera: str, zalacznik: int) -> None:
        self.akapit(f"Załącznik nr {zalacznik} · Dz. U. z 2016 r. poz. 470")
        self.naglowek(f"ARKUSZ {litera} · OCENA OKRESOWA")
        self.akapit("Urzędnika służby cywilnej lub pracownika służby cywilnej [1]")
        self.naglowek("Część I", 2)
        self.tabela([["Nazwa urzędu", self.wartosc("nazwa_urzedu")]], (175, 305))
        self.dane_osoby("Dane ocenianego", "oceniany")
        self.dane_osoby("Dane oceniającego", "oceniajacy.czesc_I")

        self.naglowek("Kryteria oceny i termin sporządzenia oceny", 3)
        termin = "termin_sporzadzenia_oceny"
        dodatkowe = [self.wartosc(f"kryterium_dodatkowe.{nr}") for nr in range(1, 4)]
        prawa_kolumna = [*dodatkowe, self.etykieta(termin), self.wartosc(termin)]
        self.tabela(
            [
                ["Kryteria obowiązkowe", "Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 3) [3]"],
                *[
                    [self.etykieta(f"kryterium_obowiazkowe.{nr}"), pole]
                    for nr, pole in enumerate(prawa_kolumna, 1)
                ],
            ],
            (240, 240),
        )
        oswiadczenie = self.pola["potwierdzenie_kryteriow.oswiadczenie"]["etykieta"]
        self.akapit(oswiadczenie.replace("zagadnień),", "zagadnień [4],"))
        self.podpis_osoby("potwierdzenie_kryteriow.oceniajacy")
        self.podpis_osoby("potwierdzenie_kryteriow.oceniany")
        self.przypisy_strony(1, 4)

    def czesc_ii_ocena(self) -> None:
        self.naglowek("Część II", 2)
        daty = ("rozmowa_oceniajaca.data", "okres_oceny.od", "okres_oceny.do")
        self.tabela(
            [[self.etykieta(klucz) for klucz in daty], [self.wartosc(klucz) for klucz in daty]],
            (240, 120, 120),
        )
        poziomy = self.pola["poziom"]["warianty"]
        wiersze = [[
            "Kryteria obowiązkowe\nOcena cząstkowa [8]",
            *[f"{punkty} pkt\n{poziom}" for punkty, poziom in zip(self.punkty, poziomy, strict=True)],
        ]]
        for nr in range(1, 6):
            klucz = f"ocena_obowiazkowa.{nr}"
            wiersze.append([self.pola[klucz]["etykieta"], *self.punkty_kryterium(klucz)])
        wiersze.append(["Kryteria dodatkowe wybrane przez oceniającego [9]", *[""] * len(self.punkty)])
        for nr in range(1, 4):
            klucz = f"ocena_dodatkowa.{nr}"
            wiersze.append([self.wartosc(f"{klucz}.kryterium"), *self.punkty_kryterium(f"{klucz}.punkty")])
        self.tabela(wiersze, (175, 61, 61, 61, 61, 61))
        self.tabela([[self.etykieta("srednia"), self.wartosc("srednia")]], (365, 115))

        self.naglowek("Przyznanie oceny", 3)
        poziom = self.wartosc("poziom")
        self.tabela(
            [
                ["Znak X", "Średnia arytmetyczna", self.etykieta("poziom")],
                *[
                    [Pole(poziom == etykieta), przedzial, etykieta]
                    for przedzial, etykieta in zip(_PRZEDZIALY_SREDNIEJ, poziomy, strict=True)
                ],
            ],
            (55, 195, 230),
        )
        self.naglowek(self.pola["wynik"]["etykieta"], 3)
        self.wybor("wynik", etykiety=["POZYTYWNA [10]", "NEGATYWNA [11]"])
        self.przypisy_strony(5, 11)

    def punkty_kryterium(self, klucz: str) -> list[Pole]:
        wybrane = self.wartosc(klucz)
        return [Pole(wybrane == str(punkty)) for punkty in self.punkty]

    def czesc_ii_potwierdzenie(self) -> None:
        self.naglowek("Część II · ciąg dalszy", 2)
        self.opis("uzasadnienie", 5)
        self.opis("wnioski_iprz", 4)
        self.naglowek("Dane dotyczące poprzedniej oceny okresowej urzędnika służby cywilnej", 3)
        poprzednia = ("poprzednia_ocena.wynik", "poprzednia_ocena.poziom", "poprzednia_ocena.data")
        self.tabela(
            [[self.etykieta(klucz) for klucz in poprzednia], [self.wartosc(klucz) for klucz in poprzednia]],
            (115, 200, 165),
        )
        self.naglowek(self.etykieta("wniosek_o_stopien.status"), 3)
        self.wybor("wniosek_o_stopien.status", etykiety=[
            "TAK", "NIE", "NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)",
        ])
        self.dane_osoby("Dane oceniającego", "oceniajacy.czesc_II")
        self.podpis_osoby("dokonanie_oceny.oceniajacy")
        self.akapit(self.etykieta("zapoznanie.oswiadczenie"))
        self.podpis_osoby("zapoznanie.oceniany")
        self.naglowek("Pouczenie", 3)
        pouczenie = self.pola["pouczenie"]["etykieta"]
        self.akapit(pouczenie.removesuffix(").") + " [17].")
        self.przypisy_strony(12, 17)

    def czesc_iii(self) -> None:
        self.naglowek("Część III", 2)
        self.akapit(
            "Wniosek jest wypełniany i dołączany do arkusza oceny okresowej ocenianego tylko "
            "w sytuacji skorzystania przez oceniającego z możliwości przewidzianej w art. 89 ust. 1 "
            "ustawy z dnia 21 listopada 2008 r. o służbie cywilnej. [18]"
        )
        self.pola_osoby("Dane urzędnika służby cywilnej", "urzednik", (
            "imie", "nazwisko", "rok_mianowania", "stopien_sluzbowy", "data_przyznania_stopnia",
        ))
        self.naglowek("Wniosek o przyznanie urzędnikowi służby cywilnej kolejnego stopnia służbowego", 3)
        nazwisko = self.wartosc("wniosek_o_stopien.imie_nazwisko") or _LINIA
        stopien = self.wartosc("wniosek_o_stopien.stopien") or _LINIA
        self.akapit(
            f"W związku z uzyskaniem przez Panią/Pana {nazwisko} pozytywnej oceny okresowej, "
            "na podstawie art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej "
            f"wnioskuję o przyznanie {stopien} stopnia służbowego."
        )
        self.opis("wniosek_o_stopien.umotywowanie", 12)
        self.podpis_osoby("wniosek_o_stopien.oceniajacy")
        self.przypisy_strony(18, 18)


def arkusz_pdf(
    wzor: Mapping[str, Any],
    wartosci: Mapping[str, str | None],
    *,
    drukuj_czesc_iii: bool,
    wersja: str,
) -> bytes:
    """Składa druk B albo C z wartości przygotowanych przez proces oceny."""
    litera = _LITERY[wzor["id"]]
    sekcje = wzor["sekcje"] if drukuj_czesc_iii else wzor["sekcje"][:2]
    pola = {
        pole["id"]: wartosci.get(pole["id"])
        for sekcja in sekcje
        for pole in sekcja["pola"]
        if pole["rodzaj"] not in {"tekst_staly", "miejsce_na_podpis_odreczny"}
    }
    dokument = _Arkusz(
        wzor,
        pola,
        Stopka(
            wersja,
            hash_tresci({"wzor": wzor["zrodlo"], "czesc_iii": drukuj_czesc_iii, "wartosci": pola}),
            KOMUNIKAT_PODPIS,
        ),
    )
    dokument.czesc_i(litera, wzor["zrodlo"]["zalacznik"])
    dokument.nowa_strona()
    dokument.czesc_ii_ocena()
    dokument.nowa_strona()
    dokument.czesc_ii_potwierdzenie()
    if drukuj_czesc_iii:
        dokument.nowa_strona()
        dokument.czesc_iii()
    return dokument.bajty()
