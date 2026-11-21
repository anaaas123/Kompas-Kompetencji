"""Pseudonimizacja danych wysyłanych do zewnętrznego modelu (#6)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient
from kompas_core.llm import Anthropic, DziennikPamiec, Ekstrakcyjny, Ollama, wywolaj
from kompas_core.llm import dostawca as modul_dostawcy
from kompas_core.llm.model import Zapytanie
from kompas_core.zrodla.model import Fragment

from kompas_mc.app import utworz_aplikacje
from kompas_mc.pseudonimizacja import (
    ChronionyDostawca,
    Pseudonimizator,
    chron_zewnetrznych,
)
from kompas_mc.qnt import MockQnt
from kompas_mc.rozmowa import KonfiguracjaRozmowy


@pytest.fixture(scope="module")
def qnt(ustawienia) -> MockQnt:
    return MockQnt.z_pliku(ustawienia.qnt)


@pytest.fixture(scope="module")
def pseudonimizator(qnt, ustawienia) -> Pseudonimizator:
    konf = KonfiguracjaRozmowy.z_pliku(ustawienia.rozmowa)
    return Pseudonimizator(qnt, konf.dane_dla_modelu["pseudonimy"])


def _identyfikatory(p) -> list[str]:
    czlony = [p.imie, p.osoba_id, *[c for c in p.nazwisko.split("-") if c != "Demo"]]
    return czlony


def _sprawdz_brak(tekst: str, osoba) -> None:
    for s in _identyfikatory(osoba):
        assert s not in tekst, f"{s!r} w {tekst!r}"


def test_kontekst_osoby_ocenianej_dostaje_role(pseudonimizator, qnt):
    anna = qnt.pracownik("P-101")
    szefowa = qnt.pracownik(anna.przelozony_id)
    kontekst = (
        f"Oceniana: {anna.imie} {anna.nazwisko} ({anna.osoba_id}), {anna.komorka}. "
        f"Oceniająca: {szefowa.imie} {szefowa.nazwisko}."
    )
    wynik = pseudonimizator.pseudonimizuj(kontekst, oceniany_id="P-101")

    assert "Oceniany" in wynik and "Przełożony" in wynik
    _sprawdz_brak(wynik, anna)
    _sprawdz_brak(wynik, szefowa)
    for czlon in anna.komorka.split(" / "):
        assert czlon not in wynik


def test_przyklad_z_imieniem_w_tresci_jest_oczyszczony(pseudonimizator, qnt):
    przyklad = (
        "Anna przygotowała z Piotrem Nowakiem-Demo raport; Annie Zielińskiej-Demo "
        "pomagał też Wiśniewski. Kacpra i Pawła nie było."
    )
    wynik = pseudonimizator.pseudonimizuj(przyklad, oceniany_id="P-101")

    for slowo in ("Ann", "Piotr", "Nowak", "Zielińsk", "Wiśniewsk", "Kacpr", "Paweł", "Pawł"):
        assert slowo not in wynik, f"{slowo!r} w {wynik!r}"
    assert wynik.startswith("Oceniany przygotowała z [osoba] raport")


def test_zwykle_slowa_zostaja(pseudonimizator):
    tekst = "Ocena okresowa w maju: przełożony omawia cele i współpracę."
    assert pseudonimizator.pseudonimizuj(tekst) == tekst


def _przechwyc_http(monkeypatch) -> list[str]:
    wyslane: list[str] = []

    def post(url, dane, naglowki, timeout):
        wyslane.append(json.dumps(dane, ensure_ascii=False))
        return {"content": [{"type": "text", "text": '{"cytaty": [], "wybor": [], "tresc": null}'}]}

    monkeypatch.setattr(modul_dostawcy, "_post_json", post)
    return wyslane


def test_zapytanie_do_zewnetrznego_modelu_bez_danych_zadnej_osoby(monkeypatch, pseudonimizator, qnt):
    wyslane = _przechwyc_http(monkeypatch)
    dostawcy = chron_zewnetrznych([Anthropic(model="test", api_key="klucz"), Ekstrakcyjny()], pseudonimizator)
    fragment = Fragment(id="f1", doc_id="d", tekst="Ocenę okresową sporządza się co 24 miesiące.")

    for osoba in qnt.pracownicy:
        przelozony = qnt.pracownik(osoba.przelozony_id)
        pytanie = (
            f"Kiedy {osoba.imie} {osoba.nazwisko} ({osoba.osoba_id}) z komórki {osoba.komorka} "
            f"ma ocenę okresową? Oceniający: {przelozony.imie + ' ' + przelozony.nazwisko if przelozony else '-'}."
        )
        wywolaj(Zapytanie(operacja="asystent_formalny", prompt_wersja="t", pytanie=pytanie,
                          fragmenty=[fragment]), dostawcy, DziennikPamiec())
        assert wyslane, "zapytanie nie trafiło do zamockowanego HTTP"
        _sprawdz_brak(wyslane[-1], osoba)
        if przelozony:
            _sprawdz_brak(wyslane[-1], przelozony)

    assert len(wyslane) == len(qnt.pracownicy)


def test_tylko_dostawcy_spoza_maszyny_sa_chronieni(pseudonimizator):
    dostawcy = chron_zewnetrznych(
        [Anthropic(model="a"), Ollama(model="o"), Ekstrakcyjny()], pseudonimizator
    )
    assert isinstance(dostawcy[0], ChronionyDostawca)
    assert (dostawcy[0].nazwa, dostawcy[0].model, dostawcy[0].tryb) == ("anthropic", "a", Anthropic.tryb)
    assert not isinstance(dostawcy[1], ChronionyDostawca)
    assert not isinstance(dostawcy[2], ChronionyDostawca)


def test_asystent_w_aplikacji_ma_chroniony_lancuch(ustawienia, tmp_path):
    konf = yaml.safe_load(ustawienia.konfiguracja_asystenta.read_text(encoding="utf-8"))
    konf["llm"] = {"dostawcy": [{"typ": "anthropic", "model": "test"}, {"typ": "ekstrakcyjny", "k": 3}]}
    konf["faq"] = str(ustawienia.konfiguracja_asystenta.parent / konf["faq"])
    plik = tmp_path / "asystent.yaml"
    plik.write_text(yaml.safe_dump(konf, allow_unicode=True), encoding="utf-8")
    ust = replace(ustawienia, baza=tmp_path / "t.db", log_llm=tmp_path / "llm.jsonl",
                  konfiguracja_asystenta=plik)

    with TestClient(utworz_aplikacje(ust)) as k:
        dostawcy = k.app.state.asystent.dostawcy

    assert [d.nazwa for d in dostawcy] == ["anthropic", "ekstrakcyjny"]
    assert isinstance(dostawcy[0], ChronionyDostawca)
    assert not isinstance(dostawcy[1], ChronionyDostawca)


def test_zasada_w_konfiguracji_rozmowy(ustawienia):
    d = KonfiguracjaRozmowy.z_pliku(ustawienia.rozmowa).dane_dla_modelu
    assert "zewnętrznego modelu" in d["zasada_zewnetrzny_model"]
    assert {"oceniany", "przelozony", "inna_osoba", "komorka", "osoba_id"} <= set(d["pseudonimy"])
    assert any(a["kategoria"] == "DECYZJA_PROJEKTOWA" for a in d["adnotacje"])
