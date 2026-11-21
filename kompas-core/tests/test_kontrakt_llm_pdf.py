from kompas_core.llm import Cytat, Ekstrakcyjny, LlmProvider, Odpowiedz, Tryb, Zapytanie
from kompas_core.zrodla import Fragment


def test_ekstrakcyjny_spelnia_protokol():
    assert isinstance(Ekstrakcyjny(), LlmProvider)
    assert Ekstrakcyjny.tryb is Tryb.EKSTRAKCYJNE


def test_modele_kontraktu():
    f = Fragment(id="a#1", doc_id="a", tekst="Ocena jest negatywna.")
    z = Zapytanie(operacja="asystent", prompt_wersja="v1", pytanie="kiedy negatywna?", fragmenty=[f])
    o = Odpowiedz(cytaty=[Cytat(fragment_id="a#1", cytat="Ocena jest negatywna.")])
    assert z.katalog == [] and o.wybor == [] and o.tresc is None
