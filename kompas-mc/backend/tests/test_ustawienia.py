import os

import pytest

from kompas_mc.ustawienia import wczytaj_env


def test_wczytaj_env_laduje_wartosci_i_nie_nadpisuje_srodowiska(tmp_path, monkeypatch):
    plik = tmp_path / ".env"
    plik.write_text(
        "# komentarz\nDEEPSEEK_API_KEY='lokalny-klucz'\nexport ISTNIEJACA=plik\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ISTNIEJACA", "proces")

    wczytaj_env(plik)

    assert os.environ["DEEPSEEK_API_KEY"] == "lokalny-klucz"
    assert os.environ["ISTNIEJACA"] == "proces"


def test_wczytaj_env_odrzuca_niepoprawna_linie(tmp_path):
    plik = tmp_path / ".env"
    plik.write_text("to nie jest przypisanie\n", encoding="utf-8")
    with pytest.raises(ValueError, match="NAZWA=WARTOSC"):
        wczytaj_env(plik)
