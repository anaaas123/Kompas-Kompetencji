"""Krok 1 (#29): analiza OSP, propozycja ścieżki (pierwsza / okresowa) i arkusza B/C.

Czyste funkcje na danych z mocka QNT i OSP. Treść reguł (opisy, cytaty) jest w
``konfiguracja/krok1.yaml``; tu jest tylko logika łącząca ją z danymi kadrowymi.
Przy niejednoznacznych danych system zwraca listę braków i nie zgaduje.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import Kategoria, SourceRef
from pydantic import BaseModel

from .osp import KatalogOsp, OpisStanowiska
from .qnt import Pracownik

Sciezka = Literal["pierwsza", "okresowa"]
Arkusz = Literal["B", "C"]


class Brak(BaseModel):
    pole: str
    komunikat: str


class Przeslanka(BaseModel):
    id: str
    sciezka: Sciezka
    rodzaj: Literal["WARUNEK", "WYLACZENIE"]
    opis: str
    spelniona: bool | None
    """``None``: dane kadrowe nie wystarczają, żeby to ustalić."""
    dane_kadrowe: dict
    adnotacje: list[SourceRef]
    uwaga: str | None = None


class PropozycjaSciezki(BaseModel):
    proponowana: Sciezka | None
    przeslanki: list[Przeslanka]
    braki: list[Brak]


class ArkuszOkresowy(BaseModel):
    arkusz: Arkusz | None
    zrodlo: Literal["OSP", "QNT"] | None
    uzasadnienie: str
    adnotacje: list[SourceRef]
    braki: list[Brak]


class ArkuszA(BaseModel):
    status: Literal["POZA_ZAKRESEM_PROTOTYPU"] = "POZA_ZAKRESEM_PROTOTYPU"
    dotyczy: bool
    komunikat: str
    adnotacje: list[SourceRef]


class Uwaga(BaseModel):
    id: str
    komunikat: str
    adnotacje: list[SourceRef]


class AnalizaKroku1(BaseModel):
    osoba_id: str
    osp: OpisStanowiska | None
    sciezka: PropozycjaSciezki
    arkusz_okresowy: ArkuszOkresowy
    arkusz_a: ArkuszA
    uwagi: list[Uwaga]


class _Regula(BaseModel):
    id: str
    opis: str | None = None
    adnotacje: list[SourceRef]


class _RegulaPrzeslanki(_Regula):
    sciezka: Sciezka
    rodzaj: Literal["WARUNEK", "WYLACZENIE"]
    opis: str
    ustawowa: bool = False


class _RegulaArkuszaA(_Regula):
    komunikat: str
    stanowiska: list[str]


class _OpcjaPodleglych(BaseModel):
    opcja: str
    kieruje: bool


class _UwagaKonf(BaseModel):
    id: str
    komunikat: str
    adnotacje: list[SourceRef]


class KonfiguracjaKroku1(BaseModel):
    uwaga_ustawa: str
    przeslanki: list[_RegulaPrzeslanki]
    arkusze: dict[str, _Regula]
    podlegli: list[_OpcjaPodleglych]
    uwagi: dict[str, _UwagaKonf]

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaKroku1:
        dane = yaml.safe_load(Path(plik).read_text(encoding="utf-8"))
        dane["arkusze"]["A"] = _RegulaArkuszaA.model_validate(dane["arkusze"]["A"])
        return cls.model_validate(dane)

    @property
    def arkusz_a(self) -> _RegulaArkuszaA:
        a = self.arkusze["A"]
        assert isinstance(a, _RegulaArkuszaA)
        return a


# ---------------------------------------------------------------- ścieżka


def _spelnienie(p: Pracownik) -> dict[str, tuple[bool | None, dict, Brak | None]]:
    """Dla każdej przesłanki: (spełniona, użyte dane kadrowe, brak danych)."""
    okreslony = p.rodzaj_umowy == "okreslony"
    ma_pierwsza = p.pierwsza_ocena is not None
    wynik: dict[str, tuple[bool | None, dict, Brak | None]] = {}

    dane = {"rodzaj_umowy": p.rodzaj_umowy, "zastepstwo": p.zastepstwo, "pierwsza_ocena": ma_pierwsza}
    if not okreslony or p.zastepstwo:
        wynik["pierwsza.pierwsze-zatrudnienie"] = (False, dane, None)
    elif ma_pierwsza:
        wynik["pierwsza.pierwsze-zatrudnienie"] = (True, dane, None)
    else:
        wynik["pierwsza.pierwsze-zatrudnienie"] = (
            None,
            dane,
            Brak(
                pole="pierwsza_ocena",
                komunikat="Umowa na czas określony, ale QNT nie podaje, czy to pierwsze zatrudnienie "
                "w służbie cywilnej (brak danych pierwszej oceny).",
            ),
        )

    dane = {"zastepstwo": p.zastepstwo, "pierwsza_ocena": ma_pierwsza}
    if not p.zastepstwo:
        wynik["pierwsza.zastepstwo"] = (False, dane, None)
    elif ma_pierwsza:
        wynik["pierwsza.zastepstwo"] = (True, dane, None)
    else:
        wynik["pierwsza.zastepstwo"] = (
            None,
            dane,
            Brak(
                pole="pierwsza_ocena",
                komunikat="Zastępstwo: QNT nie podaje, czy strony ustaliły, że osoba podlega "
                "pierwszej ocenie.",
            ),
        )

    dane = {"absolwent_ksap": p.absolwent_ksap, "wniosek_o_mianowanie": p.wniosek_o_mianowanie}
    if not p.absolwent_ksap:
        wynik["pierwsza.wylaczenie-ksap"] = (False, dane, None)
    elif p.wniosek_o_mianowanie is None:
        wynik["pierwsza.wylaczenie-ksap"] = (
            None,
            dane,
            Brak(
                pole="wniosek_o_mianowanie",
                komunikat="Absolwent KSAP: QNT nie podaje, czy złożył wniosek o mianowanie.",
            ),
        )
    else:
        wynik["pierwsza.wylaczenie-ksap"] = (p.wniosek_o_mianowanie, dane, None)

    wynik["okresowa.urzednik"] = (p.korpus == "urzednik_sc", {"korpus": p.korpus}, None)
    wynik["okresowa.czas-nieokreslony"] = (
        p.korpus == "pracownik_sc" and p.rodzaj_umowy == "nieokreslony",
        {"korpus": p.korpus, "rodzaj_umowy": p.rodzaj_umowy},
        None,
    )
    wynik["okresowa.wylaczenie-czas-okreslony"] = (
        p.korpus == "pracownik_sc" and okreslony,
        {"korpus": p.korpus, "rodzaj_umowy": p.rodzaj_umowy},
        None,
    )
    return wynik


def _ocen(przeslanki: list[Przeslanka], sciezka: Sciezka) -> bool | None:
    """True/False/None (nie wiadomo) dla ścieżki: któryś warunek i żadne wyłączenie."""
    warunki = [p.spelniona for p in przeslanki if p.sciezka == sciezka and p.rodzaj == "WARUNEK"]
    wylaczenia = [p.spelniona for p in przeslanki if p.sciezka == sciezka and p.rodzaj == "WYLACZENIE"]
    if any(w is True for w in wylaczenia):
        return False
    if any(w is True for w in warunki):
        return None if any(w is None for w in wylaczenia) else True
    return None if any(w is None for w in warunki) else False


def proponuj_sciezke(p: Pracownik, konf: KonfiguracjaKroku1) -> PropozycjaSciezki:
    spelnienie = _spelnienie(p)
    przeslanki: list[Przeslanka] = []
    braki: list[Brak] = []
    for r in konf.przeslanki:
        spelniona, dane, brak = spelnienie[r.id]
        przeslanki.append(
            Przeslanka(
                id=r.id,
                sciezka=r.sciezka,
                rodzaj=r.rodzaj,
                opis=r.opis,
                spelniona=spelniona,
                dane_kadrowe=dane,
                adnotacje=r.adnotacje,
                uwaga=konf.uwaga_ustawa if r.ustawowa else None,
            )
        )
        if brak and brak not in braki:
            braki.append(brak)

    pierwsza, okresowa = _ocen(przeslanki, "pierwsza"), _ocen(przeslanki, "okresowa")
    if pierwsza is True and okresowa is True:
        braki.append(
            Brak(
                pole="sciezka",
                komunikat="Dane kadrowe spełniają przesłanki obu ścieżek; wymagają wyjaśnienia w kadrach.",
            )
        )
    if p.ostatnia_ocena_okresowa is not None and pierwsza is True:
        braki.append(
            Brak(
                pole="ostatnia_ocena_okresowa",
                komunikat="QNT podaje ocenę okresową osoby, która według pozostałych danych "
                "podlega pierwszej ocenie.",
            )
        )
    if pierwsza is False and okresowa is False and not braki:
        braki.append(
            Brak(
                pole="sciezka",
                komunikat="Według danych kadrowych osoba nie podlega ani pierwszej ocenie, "
                "ani ocenie okresowej.",
            )
        )

    proponowana: Sciezka | None = None
    if not braki:
        proponowana = "pierwsza" if pierwsza else "okresowa" if okresowa else None
    return PropozycjaSciezki(proponowana=proponowana, przeslanki=przeslanki, braki=braki)


# ---------------------------------------------------------------- arkusz


def _kieruje_wg_osp(osp: OpisStanowiska, konf: KonfiguracjaKroku1) -> tuple[bool | None, Brak | None]:
    zazn = osp.podlegli.zaznaczone
    if len(zazn) != 1:
        return None, Brak(
            pole="osp.podlegli",
            komunikat=f"OSP {osp.symbol}: pole „liczba podległych pracowników” ma "
            f"{len(zazn)} zaznaczonych opcji zamiast jednej.",
        )
    for o in konf.podlegli:
        if zazn[0].lower().startswith(o.opcja.lower()):
            return o.kieruje, None
    return None, Brak(
        pole="osp.podlegli",
        komunikat=f"OSP {osp.symbol}: nieznana opcja „{zazn[0]}” w polu liczby podległych pracowników.",
    )


def wybierz_arkusz(
    p: Pracownik, osp: OpisStanowiska | None, konf: KonfiguracjaKroku1
) -> ArkuszOkresowy:
    if _arkusz_a_dotyczy(p, osp, konf):
        return ArkuszOkresowy(
            arkusz=None,
            zrodlo=None,
            uzasadnienie=konf.arkusz_a.komunikat,
            adnotacje=konf.arkusz_a.adnotacje,
            braki=[Brak(pole="arkusz", komunikat=konf.arkusz_a.komunikat)],
        )

    if osp is None:
        regula = konf.arkusze["B" if p.kieruje_pracownikami else "C"]
        return ArkuszOkresowy(
            arkusz="B" if p.kieruje_pracownikami else "C",
            zrodlo="QNT",
            uzasadnienie=f"Brak OSP w materiałach; według QNT stanowisko "
            f"{'polega' if p.kieruje_pracownikami else 'nie polega'} na bezpośrednim kierowaniu "
            f"pracownikami. {regula.opis}",
            adnotacje=[
                *regula.adnotacje,
                SourceRef(
                    kategoria=Kategoria.BRAK_ZRODLA,
                    uzasadnienie=f"Brak OSP dla stanowiska „{p.stanowisko}” w „materialy mc”; "
                    "użyto pola kieruje_pracownikami z QNT.",
                ),
            ],
            braki=[],
        )

    kieruje, brak = _kieruje_wg_osp(osp, konf)
    if brak:
        return ArkuszOkresowy(
            arkusz=None, zrodlo="OSP", uzasadnienie=brak.komunikat, adnotacje=[], braki=[brak]
        )
    pole_osp = [osp.podlegli.adnotacja] if osp.podlegli.adnotacja else []
    if kieruje != p.kieruje_pracownikami:
        brak = Brak(
            pole="kieruje_pracownikami",
            komunikat=f"OSP {osp.symbol} („{osp.podlegli.zaznaczone[0]}”) i QNT "
            f"(kieruje_pracownikami={p.kieruje_pracownikami}) różnią się; arkusz wymaga wyjaśnienia.",
        )
        return ArkuszOkresowy(
            arkusz=None, zrodlo="OSP", uzasadnienie=brak.komunikat, adnotacje=pole_osp, braki=[brak]
        )
    arkusz: Arkusz = "B" if kieruje else "C"
    regula = konf.arkusze[arkusz]
    return ArkuszOkresowy(
        arkusz=arkusz,
        zrodlo="OSP",
        uzasadnienie=f"OSP {osp.symbol}: „{osp.podlegli.zaznaczone[0]}”. {regula.opis}",
        adnotacje=[*pole_osp, *regula.adnotacje],
        braki=[],
    )


def _arkusz_a_dotyczy(p: Pracownik, osp: OpisStanowiska | None, konf: KonfiguracjaKroku1) -> bool:
    nazwy = [p.stanowisko.lower(), osp.nazwa.lower() if osp else ""]
    return any(s.lower() in n for s in konf.arkusz_a.stanowiska for n in nazwy)


# ---------------------------------------------------------------- całość


def analizuj(p: Pracownik, katalog: KatalogOsp, konf: KonfiguracjaKroku1) -> AnalizaKroku1:
    osp = katalog.po_symbolu(p.symbol_osp)
    sciezka = proponuj_sciezke(p, konf)
    arkusz = wybierz_arkusz(p, osp, konf)
    a = konf.arkusz_a
    uwagi: list[Uwaga] = []
    if osp is None:
        uwagi.append(
            Uwaga(
                id="brak.osp",
                komunikat=f"Brak OSP dla stanowiska „{p.stanowisko}” "
                f"({p.symbol_osp or 'bez symbolu'}) w „materialy mc”.",
                adnotacje=[
                    SourceRef(
                        kategoria=Kategoria.BRAK_ZRODLA,
                        uzasadnienie="OSP w „materialy mc”: " + ", ".join(katalog.symbole),
                    )
                ],
            )
        )
    if sciezka.proponowana == "pierwsza":
        u = konf.uwagi["osp-pierwsza-ocena"]
        uwagi.append(Uwaga(id=u.id, komunikat=u.komunikat, adnotacje=u.adnotacje))
    return AnalizaKroku1(
        osoba_id=p.osoba_id,
        osp=osp,
        sciezka=sciezka,
        arkusz_okresowy=arkusz,
        arkusz_a=ArkuszA(
            dotyczy=_arkusz_a_dotyczy(p, osp, konf), komunikat=a.komunikat, adnotacje=a.adnotacje
        ),
        uwagi=uwagi,
    )
