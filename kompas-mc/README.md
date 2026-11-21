# Kompas Kompetencji

Aplikacja korzysta z mechanizmów w `kompas-core/`. Jej źródłami są wyłącznie
pliki z folderu `materialy mc/`, którego zawartość jest tylko do odczytu.

| Część | Katalog | Port | Dane |
|---|---|---|---|
| API (FastAPI) | `backend/` | **8002** (`KOMPAS_MC_PORT`) | `backend/dane/kompas-mc.db`, log LLM `backend/dane/llm.jsonl` |
| Interfejs (React + Vite) | `frontend/` | **5174** | proxy `/api` → 8002 (`KOMPAS_MC_API`) |
| Konfiguracja | `konfiguracja/` | — | `korpus.yaml` (manifest źródeł), `asystent.yaml`, `role.yaml` (konta demo i uprawnienia), `qnt.yaml` (fikcyjni pracownicy) |

## Uruchomienie

Wymagane: Python ≥ 3.11 z [uv](https://docs.astral.sh/uv/) oraz Node ≥ 20.

```sh
# terminal 1: API na http://127.0.0.1:8002 (docs: /docs)
cd kompas-mc/backend && uv sync && uv run kompas-mc

# terminal 2: interfejs na http://127.0.0.1:5174
cd kompas-mc/frontend && npm ci && npm run dev
```

Start API trwa kilka sekund, bo przy starcie powstaje korpus z plików MC.

## Asystent formalny

`POST /api/asystent {"pytanie": "...", "sciezka": "pierwsza" | "okresowa" | null}`

- Domyślny łańcuch to DeepSeek (`deepseek-v4-flash`) → lokalna Ollama
  (`qwen3:8b`) → tryb ekstrakcyjny BM25. Brak klucza, sieci lub Ollamy nie
  przerywa odpowiedzi: asystent przechodzi do następnego dostawcy.
- Aby włączyć DeepSeek, skopiuj `backend/.env.example` jako `backend/.env` i
  ustaw `DEEPSEEK_API_KEY=sk-...`. Plik `.env` jest ignorowany przez Git. Aby
  wyłączyć DeepSeek, usuń wartość klucza; kolejność dostawców zmienia się w
  `konfiguracja/asystent.yaml`.
- Nazwę modelu można sprawdzić bez ujawniania klucza poleceniem
  `curl -sS https://api.deepseek.com/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"`.
  Konfiguracja używa zgodnego aliasu `deepseek-v4-flash` wymaganego przez
  specyfikację; DeepSeek kieruje go obecnie do aktualnego modelu Flash.
- Każda próba, wybrany model, tryb i przyczyna fallbacku trafiają do
  `backend/dane/llm.jsonl`.
- Gdy najlepszy fragment nie zawiera co najmniej 60% słów pytania, odpowiedź brzmi „brak wystarczających informacji w bazie wiedzy”.
- Ścieżka zawęża źródła do dokumentów danej ścieżki i wspólnych (model kompetencji, OSP).
- Odpowiedź modelu z cytatem bez pokrycia jest odrzucana i uruchamia fallback.

### Pomiar jakości asystenta

Pomiar używa niezmienianych zestawów `pytania-kontrolne.yaml` oraz
`pytania-parafrazy.yaml`. Tryb DeepSeek wymaga lokalnego klucza i nie jest
uruchamiany w testach CI; poniższa tabela nie przypisuje mu wyniku bez pomiaru.

| Tryb | Pytania kontrolne: dokument i cytat | Parafrazy: dokument i cytat | Odmowy spoza bazy |
|---|---:|---:|---:|
| Ekstrakcyjny | 22/22 | 16/22 | 6/6 kontrolnych, 4/5 parafraz |
| DeepSeek `deepseek-v4-flash` | do pomiaru z kluczem | do pomiaru z kluczem | do pomiaru z kluczem |

`GET /api/zrodla` pokazuje dokumenty korpusu, duplikat „Rozporządzenie … (4).pdf” (fragment rozporządzenia z 2016 r., nie osobne źródło) i pliki pominięte.

## Logowanie, role i mock QNT

`POST /api/auth/login {"login": "...", "hasło": "demo"}` zwraca token; kolejne zapytania wysyłają `Authorization: Bearer <token>`.

| Konto | Rola | Widzi |
|---|---|---|
| `przelozony1`, `przelozony2` | przełożony | swoich podwładnych (`przelozony_id`) i notatki o nich |
| `hr` | HR/administrator | wszystkich pracowników, bez notatek przełożonego |
| `oceniany` | oceniany | tylko siebie |

- `GET /api/ja`: zalogowany użytkownik i jego rola.
- `GET /api/pracownicy`, `GET /api/pracownicy/{osoba_id}`: pracownicy z mocka QNT według reguł dostępu; poza zakresem 403, brak osoby 404.
- `GET` i `POST /api/pracownicy/{osoba_id}/notatki`: notatki przełożonego o podwładnym; HR i oceniany dostają 403.

Kontrakt jest w `/docs` (OpenAPI). Konta i uprawnienia zmienia się w `konfiguracja/role.yaml`, bez zmian w kodzie.

**Zakres danych osobowych.** Mock QNT zawiera 10 fikcyjnych osób powiązanych z trzema OSP: imię, nazwisko, stanowisko, komórkę, przełożonego i fakty kadrowe potrzebne do wyboru ścieżki oceny i terminów (podstawa i data zatrudnienia, korpus, ostatnia ocena, egzamin, zastępstwo, nieobecności). Nie ma PESEL, adresów ani danych wrażliwych. Pola `scenariusz` i `oczekiwany_arkusz` służą tylko do demo i testów i nie trafiają do odpowiedzi API.

## Krok 1: analiza OSP, ścieżka i arkusz

- `GET /api/pracownicy/{osoba_id}/krok1` (podgląd, akcja `ocena.czytaj`) zwraca OSP z korpusu: cel, zadania dominujące i pozostałe, liczbę podległych, złożoność, samodzielność i kompetencje miękkie. Każde pole ma adnotację z cytatem. Zwraca też propozycję ścieżki z przesłankami i arkusz B/C według § 3 rozp. 2016.
- Przesłanki ustawowe znamy tylko z poradników, więc mają kategorię `OBJAŚNIENIE_MATERIAŁU` i uwagę „brak tekstu ustawy w bazie”. Gdy dane kadrowe są niejednoznaczne, `proponowana` ma wartość `null`, a `braki` mówią, czego brakuje.
- `POST /api/procesy {"osoba_id", "sciezka", "uzasadnienie"?}` (akcja `ocena.prowadz`, tylko przełożony) rozpoczyna proces oceny. Wybór innej ścieżki niż proponowana wymaga uzasadnienia.
- `GET /api/procesy` i `GET /api/procesy/{id}` pokazują procesy według ról.
- Treść reguł (opisy i cytaty) jest w `konfiguracja/krok1.yaml`.

## Krok 2: kryteria i wskaźniki

- `GET /api/model-kompetencji` zwraca model z `Model_kompetencji.xlsx`: 14 kompetencji, 49 wskaźników, 5 poziomów (1/3/5/7/9) i instrukcję. Każdy element ma adnotację z komórką arkusza.
- `GET /api/procesy/{id}/krok2` zwraca kryteria obowiązkowe według arkusza: § 4 ust. 2 (B) i § 4 ust. 3 (C) rozp. 2016 albo § 2 pkt 1 rozp. 2015. Pokazuje też propozycje najwyżej 3 kryteriów dodatkowych (w pierwszej ocenie 0) oraz przy każdym wskaźniku zadania z OSP, które go uzasadniają.
- `PUT /api/procesy/{id}/krok2 {"dodatkowe": [...], "wskazniki": {kompetencja_id: [wskaznik_id]}}` (akcja `ocena.prowadz`) zapisuje wybór przełożonego. Limit dodatkowych sprawdza API.
- Dobór zadań do wskaźników i punktacja kryteriów dodatkowych to `DECYZJA_PROJEKTOWA` („wymaga zatwierdzenia”). Słowa kluczowe są jawne w `konfiguracja/krok2.yaml`.

## Kroki 3–5: zachowania, sugestia, decyzja

- `GET /api/procesy/{id}/ocena` zwraca wskaźniki wybrane w kroku 2 z 5 opisami zachowań, oceny i przykłady oraz sugestię poziomu każdego kryterium z etykietą metodyki. Zwraca też decyzję przełożonego i dane w formacie `/api/rozwoj/propozycje`.
- `PUT /api/procesy/{id}/ocena/wskazniki` (krok 3) zapisuje poziom 1/3/5/7/9 albo „brak podstaw do oceny” oraz przykłady w układzie sytuacja – działanie – rezultat (z powtarzalnością, złożonością i uprawnieniami). Poziom inny niż 5 bez przykładu daje ostrzeżenie.
- `PUT /api/procesy/{id}/ocena/decyzje` (krok 5) zapisuje ocenę cząstkową. Punkty muszą być ze skali ścieżki: 1–9 według § 11 rozp. 2016 albo 3/5/7 według § 9 rozp. 2015. Odejście od sugestii wymaga uzasadnienia.
- Metodyka sugestii (`konfiguracja/ocena.yaml`, `DECYZJA_PROJEKTOWA`):
  - mediana ocenionych wskaźników;
  - „brak podstaw” nie wchodzi do mediany;
  - przy remisie system pokazuje dwie wartości;
  - poniżej połowy ocenionych wskaźników sugestii nie ma („niewystarczające dane”);
  - w pierwszej ocenie mapowanie 5→3.

  Sugestia nigdy nie wpisuje oceny sama.

## Testy i walidator

```sh
cd kompas-mc/backend
uv run pytest -q
uv run kompas-waliduj --manifest ../konfiguracja/korpus.yaml ../konfiguracja/*.yaml
```

Walidator sprawdza każdy element konfiguracji z kluczem `adnotacje`: czy ma
adnotację i czy cytat występuje dosłownie w korpusie. CI
(`.github/workflows/mc.yml`) uruchamia go przy każdym pull requeście do `main`.

## Dokładanie źródła

Dopisz dokument do `konfiguracja/korpus.yaml` (`doc_id`, `plik`, `sciezka`, `kategoria`, `podzial`). Test `test_kazdy_plik_z_materialow_mc_jest_uwzgledniony` pilnuje, żeby każdy plik z `materialy mc/` był źródłem, duplikatem albo świadomie pominięty.
