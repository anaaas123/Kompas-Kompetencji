"""Podpowiedzi celów z LLM i RAG (#12, spec #2).

Zapytanie idzie przez łańcuch dostawców z core (``wywolaj``: fallback, log, walidacja cytatów).
Model dostaje fragmenty modelu kompetencji (wskaźnik i opisy poziomów) oraz strony poradników
o wnioskach rozwojowych i IPRZ, a kontekst osoby wyłącznie po pseudonimizacji. Każdy cel zwrócony
przez model przechodzi osobną walidację: wskaźnik musi istnieć w modelu, a cytat musi występować
w podanym fragmencie korpusu. Cel, który jej nie przejdzie, jest odrzucany. Gdy nie zostanie żaden,
API zwraca podpowiedzi regułowe.
"""

from __future__ import annotations

import json
from datetime import date

from kompas_core.llm import BrakOdpowiedzi, Dziennik, LlmProvider, Tryb, Zapytanie, wywolaj
from kompas_core.zrodla import Fragment, cytat_w_tekscie
from pydantic import BaseModel

from .cele import CytatCelu, KonfiguracjaLlmCelow, PodpowiedzCelu
from .kompetencje import DOC_ID as DOC_MODELU
from .kompetencje import ModelKompetencji, Wskaznik

OPERACJA = "cele_smart"

POLECENIE = """Zaproponuj od 1 do {maks} celów rozwojowych SMART dla Ocenianego.
Opieraj się na wskaźnikach ocenionych poniżej poziomu oczekiwań (5), na samoocenie (jeśli jest)
oraz na opisach poziomów z modelu kompetencji i zaleceniach poradnika o wnioskach rozwojowych i IPRZ.
Nie powtarzaj istniejących celów. Każdy cel dotyczy jednego wskaźnika z katalogu.
W polu "tresc" zwróć tekst z obiektem JSON:
{{"cele": [{{"nazwa": "...", "opis": "...", "miernik": "...", "termin": "RRRR-MM-DD",
"wskaznik_id": "<ID z katalogu>", "fragment_id": "<ID fragmentu>", "cytat": "<dosłowny cytat z fragmentu>"}}]}}
Cytat każdego celu dopisz też do "cytaty", a jego wskaznik_id do "wybor". Dziś jest {dzis}."""


class _CelModelu(BaseModel):
    nazwa: str
    opis: str = ""
    miernik: str
    termin: str | None = None
    wskaznik_id: str
    fragment_id: str
    cytat: str


class WynikLlmCelow(BaseModel):
    podpowiedzi: list[PodpowiedzCelu]
    odrzucone: list[str]
    """Powody odrzucenia celów albo całej odpowiedzi."""
    dostawca: str | None = None
    tryb: Tryb | None = None


class PodpowiedziLlm:
    """Cele SMART z LLM: RAG na modelu kompetencji i poradnikach, walidacja każdego celu.

    ``dostawcy`` to łańcuch z konfiguracji asystenta bez dostawcy ekstrakcyjnego (nie układa
    celów); w testach podmieniany na atrapę.
    """

    def __init__(
        self,
        fragmenty: list[Fragment],
        model: ModelKompetencji,
        konf: KonfiguracjaLlmCelow,
        dostawcy: list[LlmProvider],
        dziennik: Dziennik,
    ) -> None:
        po_id = {f.id: f for f in fragmenty}
        brak = [z for z in konf.zrodla if z not in po_id]
        if brak:
            raise ValueError(f"cele.yaml: llm.zrodla spoza korpusu: {brak}")
        self.zrodla = [po_id[z] for z in konf.zrodla]
        self.model_fragmenty = {f.lokalizator: f for f in fragmenty if f.doc_id == DOC_MODELU}
        self.model = model
        self.konf = konf
        self.dostawcy = [d for d in dostawcy if d.tryb != Tryb.EKSTRAKCYJNE]
        self.dziennik = dziennik

    def _fragmenty_wskaznika(self, wskaznik_id: str) -> list[Fragment]:
        w = _wskazniki(self.model).get(wskaznik_id)
        if w is None:
            return []
        lokalizatory = [w[1].adnotacja.lokalizator] + [p.adnotacja.lokalizator for p in w[1].poziomy]
        return [self.model_fragmenty[lok] for lok in lokalizatory if lok in self.model_fragmenty]

    def zaproponuj(self, kontekst: str, wskazniki: list[str], dzis: date) -> WynikLlmCelow:
        """``kontekst`` musi być już pseudonimizowany; ``wskazniki`` to ID ocenionych wskaźników."""
        if not self.dostawcy:
            return WynikLlmCelow(podpowiedzi=[], odrzucone=["brak skonfigurowanego dostawcy LLM"])
        fragmenty = [f for w in wskazniki for f in self._fragmenty_wskaznika(w)] + self.zrodla
        zapytanie = Zapytanie(
            operacja=OPERACJA,
            prompt_wersja=self.konf.wersja,
            pytanie=(
                POLECENIE.format(maks=self.konf.maks_celow, dzis=dzis.isoformat())
                + f"\n\nKONTEKST OSOBY (dane pseudonimizowane):\n{kontekst}"
            ),
            fragmenty=fragmenty,
            katalog=wskazniki,
        )
        try:
            wynik = wywolaj(zapytanie, self.dostawcy, self.dziennik)
        except BrakOdpowiedzi as e:
            return WynikLlmCelow(
                podpowiedzi=[], odrzucone=[f"{w.dostawca}: {'; '.join(w.bledy)}" for w in e.wpisy]
            )
        przyjete, odrzucone = waliduj_cele(
            wynik.odpowiedz.tresc, fragmenty, self.model, dzis, self.konf.maks_celow
        )
        return WynikLlmCelow(
            podpowiedzi=przyjete, odrzucone=odrzucone, dostawca=wynik.dostawca, tryb=wynik.tryb
        )


def _wskazniki(model: ModelKompetencji) -> dict[str, tuple[str, Wskaznik]]:
    return {w.id: (k.nazwa, w) for k in model.kompetencje for w in k.wskazniki}


def waliduj_cele(
    tresc: str | None, fragmenty: list[Fragment], model: ModelKompetencji, dzis: date, maks: int = 3
) -> tuple[list[PodpowiedzCelu], list[str]]:
    """Cele z odpowiedzi modelu, które przeszły walidację, i powody odrzucenia pozostałych.

    Cel jest odrzucany, gdy brakuje mu pól, wskaźnik nie istnieje w modelu kompetencji, fragment
    nie był w zapytaniu albo cytat nie występuje w tym fragmencie. Termin, którego nie da się
    odczytać albo który już minął, zostaje pusty do uzupełnienia.
    """
    try:
        surowe = json.loads(tresc or "")["cele"]
        if not isinstance(surowe, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        return [], ["odpowiedź modelu nie zawiera listy celów w formacie JSON"]

    po_fragmencie = {f.id: f for f in fragmenty}
    wskazniki = _wskazniki(model)
    przyjete: list[PodpowiedzCelu] = []
    odrzucone: list[str] = []
    for i, s in enumerate(surowe, start=1):
        try:
            cel = _CelModelu.model_validate(s)
        except ValueError:
            odrzucone.append(f"cel {i}: niepełne dane")
            continue
        etykieta = f"cel {i} („{cel.nazwa[:60]}”)"
        if cel.wskaznik_id not in wskazniki:
            odrzucone.append(f"{etykieta}: wskaźnika {cel.wskaznik_id} nie ma w modelu kompetencji")
            continue
        fragment = po_fragmencie.get(cel.fragment_id)
        if fragment is None or not cel.cytat.strip() or not cytat_w_tekscie(cel.cytat, fragment.tekst):
            odrzucone.append(f"{etykieta}: cytat bez pokrycia w źródle {cel.fragment_id}")
            continue
        if len(przyjete) >= maks:
            odrzucone.append(f"{etykieta}: ponad limit {maks} celów")
            continue
        kompetencja, wskaznik = wskazniki[cel.wskaznik_id]
        przyjete.append(
            PodpowiedzCelu(
                nazwa=cel.nazwa,
                opis=cel.opis,
                wskaznik_id=cel.wskaznik_id,
                wskaznik=wskaznik.nazwa,
                kompetencja=kompetencja,
                miernik=cel.miernik,
                termin=_termin(cel.termin, dzis),
                zrodlo="llm",
                cytat=CytatCelu(
                    fragment_id=fragment.id, doc_id=fragment.doc_id, lokalizator=fragment.lokalizator,
                    strona=fragment.strona, cytat=cel.cytat,
                ),
            )
        )
    return przyjete, odrzucone


def _termin(tekst: str | None, dzis: date) -> date | None:
    try:
        termin = date.fromisoformat(tekst or "")
    except ValueError:
        return None
    return termin if termin > dzis else None
