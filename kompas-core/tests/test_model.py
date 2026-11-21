import pytest
from pydantic import ValidationError

from kompas_core.zrodla import ElementAdnotowany, Kategoria, Rozbieznosc, SourceRef


def test_przepis_wymaga_cytatu():
    with pytest.raises(ValidationError, match="cytat"):
        SourceRef(kategoria=Kategoria.PRZEPIS, doc_id="akt")
    ref = SourceRef(kategoria="PRZEPIS", doc_id="akt", cytat_dosłowny="Ocena jest negatywna")
    assert ref.cytat_doslowny == "Ocena jest negatywna"


def test_objasnienie_wymaga_cytatu():
    with pytest.raises(ValidationError):
        SourceRef(kategoria="OBJAŚNIENIE_MATERIAŁU", doc_id="poradnik", cytat_dosłowny="  ")


@pytest.mark.parametrize("kat", ["FUNKCJA_APLIKACJI", "DECYZJA_PROJEKTOWA"])
def test_funkcja_aplikacji_wymaga_uzasadnienia_i_zatwierdzajacego(kat):
    with pytest.raises(ValidationError, match="uzasadnienia"):
        SourceRef(kategoria=kat, zatwierdził="Jan")
    with pytest.raises(ValidationError, match="zatwierdz"):
        SourceRef(kategoria=kat, uzasadnienie="ułatwia pracę")
    SourceRef(kategoria=kat, uzasadnienie="ułatwia pracę", zatwierdził="Jan")


def test_brak_zrodla_bez_wymagan():
    SourceRef(kategoria="BRAK_ŹRÓDŁA")


def test_serializacja_kluczami_ze_specyfikacji():
    ref = SourceRef(kategoria="PRZEPIS", doc_id="a", cytat_doslowny="x")
    dane = ref.model_dump(by_alias=True, exclude_none=True)
    assert dane == {"doc_id": "a", "cytat_dosłowny": "x", "kategoria": "PRZEPIS"}


def test_rozbieznosc_wymaga_dwoch_adnotacji():
    a = SourceRef(kategoria="PRZEPIS", doc_id="a", cytat_dosłowny="x")
    b = SourceRef(kategoria="OBJAŚNIENIE_MATERIAŁU", doc_id="b", cytat_dosłowny="y")
    with pytest.raises(ValidationError, match="dwóch"):
        ElementAdnotowany(id="r1", adnotacje=[a], rozbieznosc=Rozbieznosc(opis="sprzeczne"))
    el = ElementAdnotowany(
        id="r1", adnotacje=[a, b], rozbieżność={"opis": "sprzeczne", "zastosowana": 0}
    )
    assert el.rozbieznosc.zastosowana == 0
