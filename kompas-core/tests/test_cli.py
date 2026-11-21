from pathlib import Path

from kompas_core.zrodla.cli import main


def _konfig(tmp_path: Path, tresc: str) -> Path:
    p = tmp_path / "reguly.yaml"
    p.write_text(tresc, encoding="utf-8")
    return p


DOBRA = """
reguly:
  - id: cykl-24
    opis: cokolwiek, czego walidator nie czyta
    adnotacje:
      - kategoria: PRZEPIS
        doc_id: ustawa
        lokalizator: art. 81 ust. 2
        strona: 1
        cytat_dosłowny: "Ocene sporzadza sie co 24 miesiace."
  - id: kalendarz-swiat
    adnotacje:
      - kategoria: FUNKCJA_APLIKACJI
        uzasadnienie: algorytm świąt ruchomych
        zatwierdził: A
"""


def test_cli_przechodzi_dla_poprawnej_konfiguracji(manifest, tmp_path, capsys):
    assert main(["--manifest", str(manifest), str(_konfig(tmp_path, DOBRA))]) == 0
    out = capsys.readouterr().out
    assert "elementy: 2, cytaty: 1" in out
    assert "uwaga: skan" in out and "BRAK_TEKSTU" in out


def test_cli_konczy_sie_bledem_przy_braku_pokrycia(manifest, tmp_path, capsys):
    zla = DOBRA.replace("24 miesiace", "25 miesiecy") + """
  - id: bez-uzasadnienia
    adnotacje:
      - kategoria: DECYZJA_PROJEKTOWA
  - opis: element bez adnotacji
    adnotacje: []
"""
    assert main(["--manifest", str(manifest), str(_konfig(tmp_path, zla))]) == 1
    out = capsys.readouterr().out
    assert "BRAK_POKRYCIA [cykl-24]" in out
    assert "NIEPOPRAWNA_ADNOTACJA [bez-uzasadnienia]" in out and "uzasadnienia" in out
    assert "BRAK_ADNOTACJI" in out and "reguly[3]" in out


def test_cli_blad_uzycia(tmp_path, capsys):
    assert main(["--manifest", str(tmp_path / "brak.yaml"), str(tmp_path / "x.yaml")]) == 2
