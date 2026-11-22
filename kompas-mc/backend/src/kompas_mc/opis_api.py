"""API opisu osoby na karcie pracownika (#55). Niczego nie zapisuje.

Dostęp: ``ocena.czytaj`` z regułą dostępu do pracownika (przełożony – podwładni, oceniany – siebie,
HR – wszyscy). Fakty z treści ocen tylko przy ``ocena.tresc`` (HR go nie ma); pracownik nie widzi
bieżących decyzji przed przekazaniem samooceny (jak ``GET …/ocena``); samoocena tylko przy
``samoocena.czytaj`` i po przekazaniu; cele przy ``cele.czytaj``. Etap i termin liczy ``etap_osoby``
z ``cykl.py``, ta sama funkcja co ``GET /api/cykl``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from pydantic import BaseModel, Field

from . import cele as c
from .cykl import etap_osoby
from .krok1 import Sciezka
from .krok2_api import StanKroku2
from .ocena import aktualne_decyzje
from .ocena_api import _wczytaj_dane
from .opis_osoby import NIE_DO_MODELU, OZNACZENIE_OPISU, Fakt, Zdanie, fakty, opis_z_modelu, opis_z_szablonu
from .procesy import _KOLUMNY, _z_wiersza
from .pseudonimizacja import Pseudonimizator
from .qnt import MockQnt, Pracownik
from .samoocena import powod_ukrycia, rozbieznosc, wczytaj as wczytaj_samoocene
from .terminy_okresowej import KonfiguracjaTerminow
from .terminy_pierwszej import KonfiguracjaTerminowPierwszej


class ZdanieOpisu(BaseModel):
    tekst: str
    fakty: list[Fakt]


class OpisOsoby(BaseModel):
    zdania: list[ZdanieOpisu]
    tryb: str
    """``SZABLON`` albo znacznik trybu odpowiedzi modelu (np. ``NA_ŻYWO``)."""
    dostawca: str | None = None
    oznaczenie: str = OZNACZENIE_OPISU
    odrzucone: list[str] = Field(default_factory=list)
    """Powody odrzucenia zdań z modelu albo informacja, który dostawca zawiódł (szczegóły w ``llm.jsonl``)."""


def router(
    auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2, konf_okresowej: KonfiguracjaTerminow,
    konf_pierwszej: KonfiguracjaTerminowPierwszej, sciezka_osoby: Callable[[Pracownik], Sciezka | None],
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["opis osoby"])

    def zbierz(request: Request, uz: Uzytkownik, p: Pracownik, rekord: dict) -> list[Fakt]:
        baza = request.app.state.baza
        f = getattr(request.app.state, "dzis", None)
        dzis = f() if f else date.today()
        w = baza.execute(
            f"SELECT {_KOLUMNY}, pierwsza_ocena FROM procesy WHERE status = 'W_TOKU' AND osoba_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (p.osoba_id,),
        ).fetchone()
        proces, zapis = (_z_wiersza(w[:-1]), w[-1]) if w else (None, None)
        sciezka = proces.sciezka if proces else sciezka_osoby(p)
        etap = etap_osoby(p, sciezka, proces, zapis, konf_okresowej, konf_pierwszej, dzis, qnt.dzis_demo)

        tresc = auth.moze(uz, "pracownik", rekord, "ocena.tresc")
        biezace = samo = None
        if proces is not None and proces.krok2 is not None:
            status, przekazano, pozycje = wczytaj_samoocene(baza, proces.id)
            oceny, decyzje = _wczytaj_dane(baza, proces.id)
            if tresc and powod_ukrycia(auth, uz, rekord, baza, proces) is None:
                if d := aktualne_decyzje(proces.krok2, decyzje):
                    biezace = (len(proces.krok2.kryteria), {k: x.punkty for k, x in d.items()})
            if status == "przekazana" and auth.moze(uz, "pracownik", rekord, "samoocena.czytaj"):
                prog = request.app.state.samoocena.prog_rozbieznosci
                samo = (przekazano, sum(1 for wid, s in pozycje.items() if rozbieznosc(s, oceny.get(wid), prog)))
        cele = c.lista(baza, p.osoba_id) if auth.moze(uz, "pracownik", rekord, "cele.czytaj") else None
        nazwy = {k.id: k.nazwa.capitalize() for k in stan2.model.kompetencje}  # jak nazwaKryterium we frontendzie
        return fakty(p, etap, dzis, nazwy, oceny_czastkowe=tresc, biezace=biezace, samoocena=samo, cele=cele)

    def odpowiedz(zdania: list[Zdanie], lista: list[Fakt], tryb: str, **reszta) -> OpisOsoby:
        po_id = {f.id: f for f in lista}
        return OpisOsoby(
            zdania=[ZdanieOpisu(tekst=z.tekst, fakty=[po_id[i] for i in z.fakty]) for z in zdania],
            tryb=tryb, **reszta,
        )

    @r.get("/pracownicy/{osoba_id}/opis")
    def opis(
        osoba_id: str, request: Request, model: bool = False, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")
    ) -> OpisOsoby:
        """2–4 zdania o osobie, każde z faktami, na których się opiera. Domyślnie szablon; ``model=true``
        próbuje modelu (bez stanowiska, po pseudonimizacji), a gdy nie zostanie żadne poprawne zdanie,
        zwraca szablon z powodami w ``odrzucone``. AI nie ustala oceny ani poziomu."""
        p = qnt.pracownik(osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        rekord = p.model_dump()
        auth.sprawdz(uz, "pracownik", rekord, "ocena.czytaj")
        lista = zbierz(request, uz, p, rekord)
        odrzucone: list[str] = []
        if model:
            pseudonimy = Pseudonimizator(qnt)
            do_modelu = [
                f.model_copy(update={"tekst": pseudonimy.tekst(f.tekst, osoba_id)})
                for f in lista if f.id not in NIE_DO_MODELU
            ]
            asystent = request.app.state.asystent
            wynik = opis_z_modelu(do_modelu, asystent.dostawcy, asystent.dziennik)
            if wynik.zdania:
                return odpowiedz(
                    wynik.zdania, lista, str(wynik.tryb), dostawca=wynik.dostawca, odrzucone=wynik.odrzucone
                )
            odrzucone = wynik.odrzucone
        return odpowiedz(opis_z_szablonu(lista), lista, "SZABLON", odrzucone=odrzucone)

    return r
