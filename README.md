# Kompas Kompetencji

Kompas Kompetencji wspiera przełożonych i pracowników w prowadzeniu ocen w
służbie cywilnej. Aplikacja znajduje się w [`kompas-mc/`](kompas-mc/README.md),
a mechanizmy wspólne w [`kompas-core/`](kompas-core/README.md).

Materiały źródłowe w `materialy mc/` są wykorzystywane tylko do odczytu.

## Jak uruchomić

Potrzebujesz:

- Python 3.11 lub nowszy i [uv](https://docs.astral.sh/uv/) (`brew install uv`);
- Node 20 lub nowszy z npm.

Aplikacja działa w dwóch terminalach: jeden uruchamia API, drugi interfejs.

**Terminal 1: API**

```sh
cd kompas-mc/backend
uv sync
uv run kompas-mc
```

API działa na <http://127.0.0.1:8002>, a opis endpointów jest pod
<http://127.0.0.1:8002/docs>. Start trwa kilka sekund, bo API buduje korpus
z plików w `materialy mc/`. Baza SQLite powstaje sama w
`kompas-mc/backend/dane/`.

**Terminal 2: interfejs**

```sh
cd kompas-mc/frontend
npm ci
npm run dev
```

Otwórz <http://localhost:5174>. Interfejs przekazuje zapytania `/api` do API na
porcie 8002, więc API musi już działać.

`uv sync` i `npm ci` są potrzebne tylko przy pierwszym uruchomieniu i po zmianie
zależności.

### Konta demo

Każde konto ma hasło `demo`.

| Login | Rola |
|---|---|
| `przelozony1`, `przelozony2` | przełożony |
| `hr` | HR |
| `oceniany` | pracownik oceniany |

Konta i uprawnienia są w `kompas-mc/konfiguracja/role.yaml`.

### Klucz API i model językowy

Do uruchomienia nie potrzebujesz klucza API. Bez klucza asystent odpowiada w
trybie ekstrakcyjnym, czyli cytatami z korpusu. Model lokalny (Ollama) włącza
się w `kompas-mc/konfiguracja/asystent.yaml`.

### Inne porty

| Zmienna | Domyślnie | Do czego |
|---|---|---|
| `KOMPAS_MC_PORT` | `8002` | port API |
| `KOMPAS_MC_API` | `http://127.0.0.1:8002` | adres API, do którego interfejs przekazuje `/api` |

## Testy

```sh
(cd kompas-core && uv run pytest -q)
(cd kompas-mc/backend && uv run pytest -q)
(cd kompas-mc/frontend && npm run build)
```

Walidator adnotacji i inne szczegóły opisuje [`kompas-mc/README.md`](kompas-mc/README.md).

## Licencja

Kod jest udostępniony na licencji BSD 3-Clause, zob. [LICENSE](LICENSE).
Licencja nie obejmuje materiałów źródłowych w `materialy mc/`, które
pozostają własnością ich autorów.
