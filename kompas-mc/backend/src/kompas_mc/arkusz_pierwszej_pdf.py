"""Wydruk pierwszej oceny według załącznika nr 2 do rozporządzenia z 2015 r."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kompas_core.pdf import Pole, Stopka, hash_tresci
from reportlab.platypus import KeepTogether

from .arkusz_pdf import _Arkusz
from .arkusze import KOMUNIKAT_PODPIS


_SKALA_PIERWSZEJ_OCENY = {
    3: "3 punkty\nponiżej oczekiwań",
    5: "5 punktów\nna poziomie oczekiwań",
    7: "7 punktów\npowyżej oczekiwań",
}


class _ArkuszPierwszejOceny(_Arkusz):
    def __init__(
        self, wzor: Mapping[str, Any], wartosci: Mapping[str, str | None], stopka: Stopka
    ) -> None:
        super().__init__(wzor, wartosci, stopka)
        self._styl_komorki.fontSize = 8.8
        self._styl_opisu.fontSize = 9.5
        self._styl_opisu.leading = 12.5

    def czesc_ogolna(self, zalacznik: int) -> None:
        self.akapit(f"Załącznik nr {zalacznik} · Dz. U. z 2015 r. poz. 1144")
        self.naglowek("ARKUSZ PIERWSZEJ OCENY W SŁUŻBIE CYWILNEJ")
        self.naglowek("Część ogólna", 2)
        self.tabela([[self.etykieta("nazwa_urzedu"), self.wartosc("nazwa_urzedu")]], (175, 305))
        self.pola_osoby("Dane ocenianego", "oceniany", (
            "imie", "nazwisko", "komorka_organizacyjna", "stanowisko", "data_nawiazania_stosunku_pracy",
        ))
        self.dane_osoby("Dane bezpośredniego przełożonego", "bezposredni_przelozony")
        self.dane_osoby("Dane kierującego komórką organizacyjną", "kierujacy_komorka")

    def rozmowa_wstepna(self) -> None:
        self.naglowek("Rozmowa wstępna", 2)
        klucz = "rozmowa_wstepna.data"
        self.tabela(
            [
                [self.etykieta(klucz), self.wartosc(klucz)],
                [
                    "Termin wyznaczony na złożenie sprawozdania dotyczącego zadań "
                    "realizowanych przez ocenianego w trakcie przepracowanego okresu",
                    self.przedzial_dat("termin_sprawozdania"),
                ],
                [
                    "Okres, w którym powinna zostać dokonana pierwsza ocena w służbie cywilnej",
                    self.przedzial_dat("okres_pierwszej_oceny"),
                ],
            ],
            (295, 185),
        )
        self.akapit(self.etykieta("potwierdzenie_rozmowy_wstepnej.oswiadczenie"))
        self.podpis_osoby("potwierdzenie_rozmowy_wstepnej.przelozony")
        self.podpis_osoby("potwierdzenie_rozmowy_wstepnej.oceniany")
        self.przypisy_strony(1, 1)

    def przedzial_dat(self, prefiks: str) -> str:
        od = self.wartosc(f"{prefiks}.od") or "................"
        do = self.wartosc(f"{prefiks}.do") or "................"
        return f"od {od}  do {do}"

    def rozmowa_oceniajaca(self) -> None:
        self.naglowek("Rozmowa oceniająca", 2)
        klucz = "rozmowa_oceniajaca.data"
        self.tabela([[self.etykieta(klucz), self.wartosc(klucz)]], (295, 185))
        oswiadczenie = self.pola["potwierdzenie_rozmowy_oceniajacej.oswiadczenie"]["etykieta"]
        self.akapit(oswiadczenie.removesuffix(").") + " [2].")
        self.podpis_osoby("potwierdzenie_rozmowy_oceniajacej.przelozony")
        self.podpis_osoby("potwierdzenie_rozmowy_oceniajacej.oceniany")

    def ocena_czastkowa(self) -> None:
        self.naglowek(
            "Ocena postawy ocenianego, jego zaangażowania i postępów w pracy, relacji "
            "ze współpracownikami oraz terminowości wykonywania zadań",
            2,
        )
        self.tabela(
            [
                ["Elementy oceny [3]\nOcena cząstkowa", *[_SKALA_PIERWSZEJ_OCENY[pkt] for pkt in self.punkty]],
                *[
                    [pole["etykieta"], *self.punkty_kryterium(klucz)]
                    for klucz, pole in self.pola.items()
                    if pole["rodzaj"] == "wybor_punktow"
                ],
            ],
            (234, 82, 82, 82),
        )
        klucz = "ocena_laczna"
        self.tabela([[self.etykieta(klucz), self.wartosc(klucz)]], (234, 246))

    def pierwsza_ocena(self) -> None:
        self.naglowek("Pierwsza ocena w służbie cywilnej", 2)
        self.akapit(self.pola["egzamin"]["etykieta"])
        self.wybor_w_wierszu("egzamin", ("TAK", "NIE", "NIE DOTYCZY [5]"))
        self.akapit(self.etykieta("sprawozdanie_w_terminie"))
        self.wybor_w_wierszu("sprawozdanie_w_terminie")
        self.wybor_w_wierszu("wynik", ("POZYTYWNA [6]", "NEGATYWNA"))
        self.przypisy_strony(2, 6)

    def wybor_w_wierszu(self, klucz: str, etykiety: tuple[str, ...] | None = None) -> None:
        warianty = self.pola[klucz]["warianty"]
        wybrany = self.wartosc(klucz)
        wiersz: list[str | Pole] = []
        for etykieta, wariant in zip(etykiety or warianty, warianty, strict=True):
            wiersz.extend((etykieta, Pole(wybrany == wariant)))
        szerokosci = (480 / len(warianty) - 34, 34) * len(warianty)
        self.tabela([wiersz], szerokosci)

    def uzasadnienie_i_potwierdzenie(self, drukuj_wnioski: bool) -> None:
        self.opis("uzasadnienie", 9)
        if drukuj_wnioski:
            self.opis("wnioski_rozwojowe", 5)
        self.naglowek("Potwierdzenie dokonania pierwszej oceny w służbie cywilnej", 3)
        self.podpis_osoby("dokonanie_oceny.przelozony")
        self.podpis_osoby("dokonanie_oceny.kierujacy")
        self.akapit(self.etykieta("zapoznanie.oswiadczenie"))
        self.podpis_osoby("zapoznanie.oceniany")
        poczatek_pouczenia = len(self._elementy)
        self.naglowek("Pouczenie", 3)
        self.akapit(
            "Po umożliwieniu ocenianemu zapoznania się z oceną oryginał arkusza wraz ze "
            "sprawozdaniem i pismami dotyczącymi zmienianych terminów włącza się do akt osobowych "
            "ocenianego, a kopię arkusza przekazuje się ocenianemu (§ 11 ust. 2 rozporządzenia "
            "z dnia 23 lipca 2015 r.)."
        )
        self.przypisy_strony(7, 8 if drukuj_wnioski else 7)
        self._elementy[poczatek_pouczenia:] = [KeepTogether(self._elementy[poczatek_pouczenia:])]


def _pola(wzor: Mapping[str, Any], wartosci: Mapping[str, str | None], drukuj_wnioski: bool) -> dict[str, str | None]:
    return {
        pole["id"]: wartosci.get(pole["id"])
        for sekcja in wzor["sekcje"]
        for pole in sekcja["pola"]
        if pole["rodzaj"] not in {"tekst_staly", "miejsce_na_podpis_odreczny"}
        and (drukuj_wnioski or pole["id"] != "wnioski_rozwojowe")
    }


def arkusz_pierwszej_oceny_pdf(
    wzor: Mapping[str, Any],
    wartosci: Mapping[str, str | None],
    *,
    drukuj_wnioski: bool,
    wersja: str,
) -> bytes:
    """Składa gotowe wartości procesu w arkusz pierwszej oceny do wydruku."""
    pola = _pola(wzor, wartosci, drukuj_wnioski)
    dokument = _ArkuszPierwszejOceny(
        wzor, pola, Stopka(
            wersja,
            hash_tresci({"wzor": wzor["zrodlo"], "drukuj_wnioski": drukuj_wnioski, "wartosci": pola}),
            KOMUNIKAT_PODPIS,
        ),
    )
    dokument.czesc_ogolna(wzor["zrodlo"]["zalacznik"])
    dokument.rozmowa_wstepna()
    dokument.nowa_strona()
    dokument.rozmowa_oceniajaca()
    dokument.ocena_czastkowa()
    dokument.pierwsza_ocena()
    dokument.nowa_strona()
    dokument.uzasadnienie_i_potwierdzenie(drukuj_wnioski)
    return dokument.bajty()


def rozmowa_wstepna_pdf(wzor: Mapping[str, Any], wartosci: Mapping[str, str | None], *, wersja: str) -> bytes:
    """Część ogólna i sekcja „Rozmowa wstępna” arkusza do podpisu po rozmowie wstępnej (rozp. 2015 § 3–4)."""
    pola = _pola(wzor, wartosci, drukuj_wnioski=False)
    dokument = _ArkuszPierwszejOceny(
        wzor, pola, Stopka(
            wersja,
            hash_tresci({"wzor": wzor["zrodlo"], "czesc": "rozmowa_wstepna", "wartosci": pola}),
            KOMUNIKAT_PODPIS,
        ),
    )
    dokument.czesc_ogolna(wzor["zrodlo"]["zalacznik"])
    dokument.rozmowa_wstepna()
    return dokument.bajty()
