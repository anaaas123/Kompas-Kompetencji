# Wykorzystanie sztucznej inteligencji

Model językowy działa przez łańcuch dostawców `LlmProvider` z `kompas-mc/konfiguracja/asystent.yaml` (sekcja `llm.dostawcy`), w tej kolejności:

1. `openai_zgodny`: DeepSeek (`https://api.deepseek.com`), model `deepseek-v4-flash`, klucz ze zmiennej `DEEPSEEK_API_KEY`, timeout 30 s, temperatura 0;
2. `ollama`: model lokalny `qwen3:8b`, timeout 5 s;
3. `ekstrakcyjny`: bez modelu, fragmenty wybrane wyszukiwaniem BM25 (k = 3).

Wygrywa pierwsza odpowiedź, której cytaty przejdą walidację. Brak klucza, sieci albo Ollamy oznacza przejście do następnego dostawcy; bez klucza i bez Ollamy odpowiada tryb ekstrakcyjny, który nie wymaga sieci ani modelu. Model dostaje instrukcję systemową, wybrane fragmenty źródeł i pytanie (w czacie rozmowy i podpowiedziach celów także pseudonimizowany kontekst) i ma wskazać w tych fragmentach dosłowne cytaty. Bazy wiedzy nie tworzy model: korpus i indeks buduje kod z plików przy starcie API. **AI nie ustala poziomu oceny ani wyniku i nie wpisuje treści do formularza.**

## Gdzie i jak

| Miejsce | Tryb | Co robi | Czego nie robi |
|---|---|---|---|
| **Asystent formalny** (czat, `POST /api/asystent`) | Łańcuch dostawców z `asystent.yaml`. Fragmenty wybiera wyszukiwanie BM25 na rdzeniach słów (bez wektorów) na korpusie MC oraz dopasowanie do zestawu pytań i odpowiedzi (39 pozycji, `faq.yaml`). Do dostawcy trafiają najwyżej 3 fragmenty. | Odpowiada cytatami z dokumentu, paragrafu i strony. Filtruje źródła według ścieżki (pierwsza / okresowa). Odpowiada „brak wystarczających informacji w bazie wiedzy”, gdy: (1) pytanie wskazuje ustawę o służbie cywilnej, której tekstu nie ma w bazie (uwaga `brak_ustawy`); poza FAQ także gdy (2) pytanie zawiera pojęcie spoza korpusu i FAQ (z nazwą pojęcia), (3) najlepszy fragment ma wynik poniżej 4,0, (4) najlepszy fragment zawiera mniej niż połowę pojęć pytania (`minimalne_pokrycie: 0.5`). | Nie odpowiada bez cytatu. Na ekranie są tylko cytaty, które przeszły walidację; tekst odpowiedzi pokazuje się wyłącznie przy trafieniu FAQ i jest to tekst drużyny. Odpowiedź z cytatem, którego nie ma w przekazanym fragmencie, jest odrzucana, a łańcuch przechodzi do następnego dostawcy. |
| **Czat rozmowy** (krok 6, `POST /api/procesy/{id}/rozmowa/czat`) | Ten sam asystent formalny i łańcuch dostawców z `asystent.yaml` | Odpowiada jak asystent formalny, z tymi samymi odmowami. Do pytania dołącza pseudonimizowany stan oceny (wskaźniki, poziomy, przykłady, samoocena, decyzje). | Nic nie zapisuje i nie zmienia ocen. |
| **Plan rozmowy** (krok 6, `POST /api/procesy/{id}/rozmowa`) | **Szablony** (deterministyczne, bez LLM) | Układa plan rozmowy: zakres z § 10 rozp. 2016 / § 2 i 7 rozp. 2015, pytania ze wskaźników, przykładów i zadań OSP (każde z uzasadnieniem i powiązaniem), argumenty i szkic informacji zwrotnej. | Nic nie zapisuje i nie zmienia ocen. Wszystko ma oznaczenie „sugestia do edycji”. Nie wysyła danych do modelu. |
| **Podpowiedzi celów** (`GET /api/pracownicy/{osoba_id}/cele/podpowiedzi`) | Łańcuch z `asystent.yaml` bez dostawcy ekstrakcyjnego; gdy nie da poprawnej odpowiedzi, reguły z `rozwoj.yaml` | Proponuje 1–3 cele SMART z fragmentów modelu kompetencji, stron poradników o IPRZ i pseudonimizowanego kontekstu. Każdy cel ma wskaźnik z modelu i cytat. | Nie zapisuje celu (status `propozycja`). Cel ze wskaźnikiem spoza modelu albo z cytatem bez pokrycia jest odrzucany. |
| **Sugerowany poziom kompetencji** (krok 4) | Reguła deterministyczna, bez AI | Mediana poziomów ocenionych wskaźników według zatwierdzonej wersji metodyki. | Nie wypełnia oceny cząstkowej. Odejście od sugestii jest zapisywane, uzasadnienie opcjonalne. |
| **Propozycje kryteriów dodatkowych** (krok 2) i **form rozwoju** (krok 8) | Reguły i słowa kluczowe z konfiguracji, bez AI | Dopasowanie zadań z OSP do wskaźników. Formy rozwoju z przykładowych arkuszy w poradnikach, z cytatami. | Nie wybiera za przełożonego. Pole wniosków do IPRZ pozostaje puste, dopóki przełożony go nie wypełni. |

## Kontrola jakości i bezpieczeństwa AI

- **Walidator cytatów** (`kompas-waliduj`, uruchamiany ręcznie) sprawdza każdy cytat w konfiguracji i w FAQ dosłownie w korpusie. Normalizuje tylko białe znaki i dzielenie wyrazów. Ostatni przebieg: 190 elementów, 185 cytatów, 0 błędów. Cytat FAQ, którego nie ma w korpusie, zatrzymuje też start API.
- **Walidacja odpowiedzi LLM** (`kompas_core.llm.wywolaj`): każdy cytat musi pochodzić z fragmentu przekazanego do modelu. W przeciwnym razie odpowiedź jest odrzucana, zalogowana i łańcuch przechodzi do następnego dostawcy (test z atrapą zmyślającą cytat).
- **Log każdego wywołania** (`backend/dane/llm.jsonl`): tryb (na żywo / zapisane / ekstrakcyjne), model, wersja promptu, ID użytych fragmentów, wynik walidacji. Błąd zapisu tego pliku jest zgłaszany przez `logging` (stderr procesu API) i nie przerywa odpowiedzi.
- **Pytania kontrolne** (`pytania-kontrolne.yaml`): 22 pytania z bazy z oczekiwanym dokumentem i paragrafem oraz 6 pytań spoza bazy, które muszą dostać „brak informacji”. Uruchamia je `pytest` (`tests/test_asystent_formalny.py`); wynik w trybie ekstrakcyjnym: 22/22 i 6/6.
- **Pseudonimizacja**: imiona, nazwiska, identyfikatory osób i nazwy komórek z mocka QNT zastępują etykiety (`Oceniany`, `Przełożony`, `Osoba`, `Komórka`) przed wysłaniem kontekstu do dostawcy. Listę pól dozwolonych i zabronionych zawiera `rozmowa.yaml` (`dane_dla_modelu`).

## Ograniczenia

- Ustawy o służbie cywilnej nie ma w materiałach MC. Pytanie, które ją wskazuje (np. „art. 81 ustawy”, „u.s.c.”), dostaje „brak informacji” bez cytatów; API dołącza uwagę `brak_ustawy`, że tekstu ustawy nie ma w bazie. Przesłanki ustawowe w odpowiedziach pochodzą z poradników i mają oznaczenie „brak tekstu ustawy w bazie”.
- Zestawu pytań i odpowiedzi organizatora nie ma w materiałach. Korzystamy z zestawu drużyny, w którym każda odpowiedź ma cytat.
- Wyszukiwanie BM25 nie rozumie parafraz tak dobrze jak model semantyczny. Parafrazy pokrywa FAQ, a resztę obsługuje odpowiedź „brak informacji”, zamiast zgadywać. Zestaw parafraz w trybie ekstrakcyjnym: 16/22 trafień, 5/5 odmów spoza bazy.
- Odpowiedź pokazuje tryb i dostawcę. Zestawy pytań zmierzyliśmy w trybie ekstrakcyjnym; z dostawcami modelowymi pomiaru nie ma (`kompas-mc/README.md`).
