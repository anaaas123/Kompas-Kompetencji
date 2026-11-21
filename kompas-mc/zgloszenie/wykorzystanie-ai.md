# Wykorzystanie sztucznej inteligencji

Zgodnie z pkt 5 zadania korzystamy tylko z darmowych narzędzi. Domyślnie działa **tryb ekstrakcyjny**, który nie wymaga sieci, klucza ani modelu. Model językowy jest opcjonalny, lokalny (Ollama) i ograniczony do układania odpowiedzi z pobranych fragmentów. **AI nie ustala poziomu oceny ani wyniku i nie wpisuje treści do formularza.**

## Gdzie i jak

| Miejsce | Tryb | Co robi | Czego nie robi |
|---|---|---|---|
| **Asystent formalny** (czat, `POST /api/asystent`) | **Ekstrakcyjny** (domyślny): wyszukiwanie BM25 z prostą normalizacją polskich form na korpusie MC oraz dopasowanie do zestawu pytań i odpowiedzi (39 pozycji, `faq.yaml`). Opcjonalnie **LLM lokalny** (Ollama) za interfejsem `LlmProvider`. | Odpowiada cytatami z dokumentu, paragrafu i strony. Filtruje źródła według ścieżki (pierwsza / okresowa). Przy pojęciu spoza bazy albo zbyt słabym dopasowaniu odpowiada „brak wystarczających informacji w bazie wiedzy”. | Nie odpowiada bez cytatu. Odpowiedź LLM z cytatem, którego nie ma w pobranym fragmencie, jest odrzucana i system wraca do trybu ekstrakcyjnego. |
| **Asystent rozmowy** (krok 6, `POST /api/procesy/{id}/rozmowa`) | **Szablony** (deterministyczne, bez LLM) | Układa plan rozmowy: zakres z § 10 rozp. 2016 / § 2 i 7 rozp. 2015, pytania ze wskaźników, przykładów i zadań OSP (każde z uzasadnieniem i powiązaniem), argumenty i szkic informacji zwrotnej. | Nic nie zapisuje i nie zmienia ocen. Wszystko ma oznaczenie „sugestia do edycji”. Konfiguracja wymienia dane, które nie mogą trafić do modelu: imię, nazwisko, przykłady, notatki, sprawozdanie. |
| **Sugerowany poziom kompetencji** (krok 4) | Reguła deterministyczna, bez AI | Mediana poziomów ocenionych wskaźników według zatwierdzonej wersji metodyki. | Nie wypełnia oceny cząstkowej. Odejście od sugestii wymaga tylko uzasadnienia. |
| **Propozycje kryteriów dodatkowych** (krok 2) i **form rozwoju** (krok 8) | Reguły i słowa kluczowe z konfiguracji, bez AI | Dopasowanie zadań z OSP do wskaźników. Formy rozwoju z przykładowych arkuszy w poradnikach, z cytatami. | Nie wybiera za przełożonego. Pole wniosków do IPRZ pozostaje puste, dopóki przełożony go nie wypełni. |

## Kontrola jakości i bezpieczeństwa AI

- **Walidator cytatów** (`kompas-waliduj`, w CI) sprawdza każdy cytat w konfiguracji i w FAQ dosłownie w korpusie. Normalizuje tylko białe znaki i dzielenie wyrazów.
- **Walidacja odpowiedzi LLM** (`kompas_core.llm.wywolaj`): każdy cytat musi pochodzić z fragmentu przekazanego do modelu. W przeciwnym razie odpowiedź jest odrzucana, zalogowana i zastąpiona trybem ekstrakcyjnym (test z atrapą zmyślającą cytat).
- **Log każdego wywołania** (`backend/dane/llm.jsonl`): tryb (na żywo / zapisane / ekstrakcyjne), model, wersja promptu, ID użytych fragmentów, wynik walidacji.
- **Pytania kontrolne** (`pytania-kontrolne.yaml`): 22 pytania z bazy z oczekiwanym dokumentem i paragrafem oraz 6 pytań spoza bazy, które muszą dostać „brak informacji”. Testy uruchamiają je przy każdym PR.
- **Dane osobowe** nie trafiają do zewnętrznego modelu. Dostawcy dozwoleni w wersji MC to `ollama` (lokalny), `zapisane` i `ekstrakcyjny`. Konfiguracja odrzuca usługę chmurową.

## Ograniczenia

- Ustawy o służbie cywilnej nie ma w materiałach MC. Przesłanki ustawowe pochodzą z poradników i mają oznaczenie „brak tekstu ustawy w bazie”.
- Zestawu pytań i odpowiedzi organizatora nie ma w materiałach. Korzystamy z zestawu drużyny, w którym każda odpowiedź ma cytat.
- Wyszukiwanie BM25 nie rozumie parafraz tak dobrze jak model semantyczny. Parafrazy pokrywa FAQ, a resztę obsługuje odpowiedź „brak informacji”, zamiast zgadywać.
- Tryb LLM wymaga lokalnej Ollamy. Na demo działa tryb ekstrakcyjny.
