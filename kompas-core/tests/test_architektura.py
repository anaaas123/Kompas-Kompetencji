"""Test architektoniczny: core nie odwołuje się do materiałów żadnej wersji."""

import re
import unicodedata
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[1]
ZAKAZANE = re.compile(r"materia[łl]y(\s+mc)?\b|kompas[-_]v1|kompas[-_]mc", re.IGNORECASE)


def _pliki():
    for katalog in ("src", "tests"):
        for p in (KORZEN / katalog).rglob("*"):
            if p.is_file() and p.suffix in {".py", ".yaml", ".yml", ".json", ".toml"}:
                if p.name != Path(__file__).name:
                    yield p
    yield KORZEN / "pyproject.toml"


def test_core_nie_odwoluje_sie_do_materialow_ani_wersji():
    naruszenia = []
    for p in _pliki():
        tekst = unicodedata.normalize("NFC", p.read_text(encoding="utf-8"))
        for nr, linia in enumerate(tekst.splitlines(), start=1):
            if ZAKAZANE.search(linia):
                naruszenia.append(f"{p.relative_to(KORZEN)}:{nr}: {linia.strip()}")
    assert not naruszenia, "core odwołuje się do materiałów lub wersji:\n" + "\n".join(naruszenia)
