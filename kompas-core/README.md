# kompas-core

Core Kompasu Kompetencji zawiera **wyłącznie mechanizmy**. Dokumenty, reguły,
cytaty i dane demo należą do konfiguracji aplikacji w `kompas-mc/`. Core nie
odwołuje się do folderu z materiałami.

```sh
cd kompas-core
uv sync
uv run pytest
```

Aplikacja dołącza core jako zależność ścieżkową w swoim `pyproject.toml`:

```toml
dependencies = ["kompas-core"]

[tool.uv.sources]
kompas-core = { path = "../kompas-core", editable = true }
```

## Moduł źródeł (`kompas_core.zrodla`)

| Element | Co robi |
|---|---|
| `SourceRef` | Adnotacja źródłowa. Kategorie: `PRZEPIS`, `OBJAŚNIENIE_MATERIAŁU` (wymagają `doc_id` i `cytat_dosłowny`), `FUNKCJA_APLIKACJI` / `DECYZJA_PROJEKTOWA` (wymagają `uzasadnienie` i `zatwierdził`), `BRAK_ŹRÓDŁA`. Reguły kategorii sprawdza konstruktor. |
| `ElementAdnotowany` | Element treści z listą adnotacji i opcjonalną flagą `rozbieżność` (co najmniej 2 adnotacje, `zastosowana` = indeks adnotacji). |
| `ekstrahuj(plik, doc_id, doc_version)` | PDF (strona po stronie, `BRAK_TEKSTU` dla stron bez warstwy tekstowej), DOCX (śledzone zmiany osobno w `Fragment.zmiany`), XLSX (`Arkusz!A1`). |
| `Korpus` | Zbiór fragmentów z manifestu aplikacji. `wyszukaj()` to BM25 z prostą normalizacją polskich form; zwraca `Trafienie(fragment_id, wynik, fragment)`. |
| `waliduj_elementy()` | Sprawdza, czy każdy element ma adnotację i czy każdy cytat występuje dosłownie w korpusie. Normalizuje tylko białe znaki i dzielenie wyrazów na końcu wiersza. |
| `kompas-waliduj` | CLI do CI, kod wyjścia 1 przy braku pokrycia. |

Klucze JSON/YAML są takie jak w specyfikacji (`cytat_dosłowny`, `zatwierdził`, `rozbieżność`). W Pythonie pola nie mają polskich znaków (`cytat_doslowny`). Konstruktor przyjmuje obie formy, a `model_dump(by_alias=True)` zwraca formę ze specyfikacji.

## LLM (`kompas_core.llm`)

| Element | Co robi |
|---|---|
| `Zapytanie` | Operacja, wersja promptu, pytanie, fragmenty korpusu z ID i opcjonalny katalog dozwolonych ID. |
| `Odpowiedz` | `cytaty` (`fragment_id` + dosłowny cytat), `wybor` (ID z katalogu), opcjonalna `tresc` ułożona z cytatów. |
| `LlmProvider` | Protokół: `nazwa`, `model`, `tryb` (`NA_ŻYWO` / `ZAPISANE` / `EKSTRAKCYJNE`), `odpowiedz(zapytanie)`. Dostawcy: `Anthropic`, `Ollama`, `Zapisane`, `Ekstrakcyjny`. |
| `wywolaj(zapytanie, dostawcy, dziennik)` | Pyta dostawców po kolei. Odpowiedź z cytatem bez pokrycia albo z ID spoza wejścia jest odrzucana i logowana, a system przechodzi do następnego dostawcy. |
| `z_konfiguracji(cfg)` | Łańcuch dostawców z konfiguracji aplikacji, z opcjonalną listą `dozwolone`. |

## PDF (`kompas_core.pdf`)

`DokumentPdf` (ReportLab) ma metody `naglowek`, `akapit`, `tabela` z komórkami `Pole(zaznaczone)` drukowanymi jako „X”, `podpis` i stopkę `Stopka(wersja, hash)` na każdej stronie. Font TTF z polskimi znakami jest konfigurowalny: parametr `font` albo zmienna `KOMPAS_PDF_FONT`. `hash_tresci()` liczy sha256 z kanonicznego JSON.

## Moduł dostępu (`kompas_core.auth`)

| Element | Co robi |
|---|---|
| `KonfiguracjaRol` | Konta demo (`login`, `hasło`, `rola`, `osoba_id`), uprawnienia ról do akcji (`"*"` = wszystkie) i `reguły_dostępu`. Podaje ją konfiguracja aplikacji. |
| `RegulaDostepu` | Rekord zasobu jest dostępny dla roli, gdy `rekord[pole]` równa się polu użytkownika (domyślnie `osoba_id`) albo je zawiera. Np. przełożony widzi tylko swoich podwładnych. |
| `Autoryzacja` | `zaloguj()` daje token sesji. `wymagaj(akcja)` to zależność FastAPI: 401 bez tokenu, 403 bez uprawnienia. `moze()`, `sprawdz()` (403) i `filtruj()` stosują reguły dostępu do rekordów. `router()`: `POST /auth/login`. |
| `Dziennik` | Dziennik zmian w SQLite: `zapisz()` zapisuje autora, czas, różnicę pól i wersję reguł; `historia()` zwraca wpisy zasobu chronologicznie. |
