import { FormEvent, useEffect, useState } from "react";
import { BladApi, pobierzKrok2, zapiszKrok2, type Krok2 as DaneKroku2, type KryteriumKroku2, type Pracownik, type ProcesOceny } from "./api";
import { NAZWA_SCIEZKI, Zrodla, opisBledu } from "./Krok1";

type Wskazniki = Record<string, string[]>;

function poczatek(d: DaneKroku2): { dodatkowe: string[]; wskazniki: Wskazniki } {
  if (d.wybor) {
    return {
      dodatkowe: d.wybor.kryteria.filter((k) => k.rodzaj === "DODATKOWE").map((k) => k.kompetencja_id),
      wskazniki: Object.fromEntries(d.wybor.kryteria.map((k) => [k.kompetencja_id, k.wskazniki.map((w) => w.id)])),
    };
  }
  const wskazniki: Wskazniki = {};
  for (const k of d.kryteria.filter((k) => k.rodzaj === "OBOWIAZKOWE")) wskazniki[k.kompetencja_id] = domyslne(k);
  return { dodatkowe: [], wskazniki };
}

/** Wskaźniki dopasowane do zadań z OSP; gdy żaden nie pasuje, wszystkie, żeby kryterium nie było puste. */
function domyslne(k: KryteriumKroku2): string[] {
  const pasujace = k.wskazniki.filter((w) => w.proponowany).map((w) => w.wskaznik_id);
  return pasujace.length > 0 ? pasujace : k.wskazniki.map((w) => w.wskaznik_id);
}

type PropsListy = {
  k: KryteriumKroku2;
  wybrane: string[];
  tylkoOdczyt: boolean;
  onWskaznik: (id: string) => void;
};

function ListaWskaznikow({ k, wybrane, tylkoOdczyt, onWskaznik }: PropsListy) {
  return (
    <ul className="wskazniki">
      {k.wskazniki.map((w) => (
        <li key={w.wskaznik_id}>
          <label className="zaznacz">
            <input
              type="checkbox"
              checked={wybrane.includes(w.wskaznik_id)}
              disabled={tylkoOdczyt}
              onChange={() => onWskaznik(w.wskaznik_id)}
            />
            <span>
              {w.nazwa} {w.proponowany && <span className="status pozytywna">pasuje do zadań</span>}
            </span>
          </label>
          <div className="pod-wskaznikiem">
            {w.zadania.length > 0 && (
              <details className="zadania-osp">
                <summary>Zadania z OSP: {w.zadania.map((z) => z.nr).join(", ")}</summary>
                {w.zadania.map((z) => (
                  <p key={z.nr} className="meta">
                    {z.nr}. ({z.rodzaj === "DOMINUJACE" ? "dominujące" : "pozostałe"}) {z.tekst}
                  </p>
                ))}
              </details>
            )}
            <Zrodla adnotacje={[w.podstawa]} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Kryterium(props: PropsListy) {
  return (
    <div className="kryterium">
      <div className="wiersz-przeslanki">
        <strong>{props.k.nazwa}</strong>
        <span className="meta">
          wskaźników: {props.wybrane.length} z {props.k.wskazniki.length}
        </span>
      </div>
      <ListaWskaznikow {...props} />
    </div>
  );
}

export function Krok2({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
  onDalej,
}: {
  token: string;
  osoba: Pracownik;
  proces: ProcesOceny;
  moznaProwadzic: boolean;
  onWstecz: () => void;
  onDalej: () => void;
}) {
  const [dane, setDane] = useState<DaneKroku2 | null>(null);
  const [dodatkowe, setDodatkowe] = useState<string[]>([]);
  const [wskazniki, setWskazniki] = useState<Wskazniki>({});
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [zapisano, setZapisano] = useState<string | null>(null);

  useEffect(() => {
    pobierzKrok2(token, proces.id)
      .then((d) => {
        const p = poczatek(d);
        setDane(d);
        setDodatkowe(p.dodatkowe);
        setWskazniki(p.wskazniki);
      })
      .catch((err) => setBlad(opisBledu(err)));
  }, [token, proces.id]);

  if (!dane) {
    return (
      <section>
        {blad ? <p className="blad">{blad}</p> : <p className="meta">Wczytuję kryteria…</p>}
      </section>
    );
  }

  const tylkoOdczyt = !moznaProwadzic;
  const obowiazkowe = dane.kryteria.filter((k) => k.rodzaj === "OBOWIAZKOWE");
  const proponowane = dane.kryteria.filter((k) => k.rodzaj === "DODATKOWE_PROPONOWANE");
  const dostepne = dane.kryteria.filter((k) => k.rodzaj === "DODATKOWE_DOSTEPNE");
  const wybrane = [...obowiazkowe.map((k) => k.kompetencja_id), ...dodatkowe];
  const pusteKryteria = wybrane.filter((id) => (wskazniki[id] ?? []).length === 0);
  const liczbaWskaznikow = wybrane.reduce((n, id) => n + (wskazniki[id] ?? []).length, 0);

  function przelaczWskaznik(kompetencja: string, id: string) {
    setZapisano(null);
    setWskazniki((w) => {
      const obecne = w[kompetencja] ?? [];
      return { ...w, [kompetencja]: obecne.includes(id) ? obecne.filter((x) => x !== id) : [...obecne, id] };
    });
  }

  function przelaczDodatkowe(k: KryteriumKroku2) {
    setZapisano(null);
    if (dodatkowe.includes(k.kompetencja_id)) {
      setDodatkowe((d) => d.filter((x) => x !== k.kompetencja_id));
    } else {
      setDodatkowe((d) => [...d, k.kompetencja_id]);
      setWskazniki((w) => ({ ...w, [k.kompetencja_id]: w[k.kompetencja_id] ?? domyslne(k) }));
    }
  }

  async function zapisz(e: FormEvent) {
    e.preventDefault();
    setCzekam(true);
    setBlad(null);
    try {
      await zapiszKrok2(token, proces.id, {
        dodatkowe,
        wskazniki: Object.fromEntries(wybrane.map((id) => [id, wskazniki[id] ?? []])),
      });
      setZapisano(`Zapisano krok 2: ${wybrane.length} kryteriów, ${liczbaWskaznikow} wskaźników.`);
    } catch (err) {
      setBlad(
        err instanceof BladApi && err.status === 409
          ? "Proces oceny nie jest w toku, więc wyboru nie można zapisać."
          : opisBledu(err),
      );
    } finally {
      setCzekam(false);
    }
  }

  const dalej = (
    <div className="wiersz">
      <span className="meta">Następny krok: zachowania, sugestia i ocena cząstkowa</span>
      <button type="button" className="jasny" onClick={onDalej}>
        Dalej: kroki 3–5
      </button>
    </div>
  );

  const kartaDodatkowego = (k: KryteriumKroku2) => {
    const wybrany = dodatkowe.includes(k.kompetencja_id);
    const pelny = !wybrany && dodatkowe.length >= dane.limit_dodatkowych;
    return (
      <div key={k.kompetencja_id} className="kryterium">
        <label className="zaznacz">
          <input
            type="checkbox"
            checked={wybrany}
            disabled={tylkoOdczyt || pelny}
            onChange={() => przelaczDodatkowe(k)}
          />
          <span>
            <strong>{k.nazwa}</strong>{" "}
            {k.propozycja && <span className="status uwaga">propozycja systemu</span>}
          </span>
        </label>
        <div className="pod-wskaznikiem">
          {k.propozycja && <p className="meta">Dlaczego: {k.propozycja.powody.join("; ")}</p>}
          {k.propozycja && <Zrodla adnotacje={k.propozycja.adnotacje} />}
          {wybrany && (
            <p className="meta">
              wskaźników: {(wskazniki[k.kompetencja_id] ?? []).length} z {k.wskazniki.length}
            </p>
          )}
        </div>
        {wybrany && (
          <ListaWskaznikow
            k={k}
            wybrane={wskazniki[k.kompetencja_id] ?? []}
            tylkoOdczyt={tylkoOdczyt}
            onWskaznik={(id) => przelaczWskaznik(k.kompetencja_id, id)}
          />
        )}
      </div>
    );
  };

  return (
    <>
      <section>
        <div className="wiersz">
          <div>
            <div className="etykieta">Krok 2 z 8 · Kryteria i wskaźniki</div>
            <h2>
              {osoba.imie} {osoba.nazwisko}
            </h2>
            <p className="opis">
              {NAZWA_SCIEZKI[dane.sciezka]} · arkusz {dane.arkusz === "PIERWSZA" ? "pierwszej oceny" : dane.arkusz}
            </p>
          </div>
          <button type="button" className="link" onClick={onWstecz}>
            Wróć do kroku 1
          </button>
        </div>
        {tylkoOdczyt && !dane.wybor && (
          <p className="brak">Przełożony nie zatwierdził jeszcze kryteriów. Zaznaczenia to propozycja systemu.</p>
        )}
        {dane.wybor && (
          <p className="sukces">
            Zapisany wybór: {dane.wybor.kryteria.length} kryteriów, zapisał {dane.wybor.zapisal}.
          </p>
        )}
        {tylkoOdczyt && dane.wybor && dalej}
      </section>

      <section>
        <h2>Kryteria obowiązkowe</h2>
        <Zrodla adnotacje={dane.podstawa_obowiazkowych} />
        {obowiazkowe.map((k) => (
          <Kryterium
            key={k.kompetencja_id}
            k={k}
            wybrane={wskazniki[k.kompetencja_id] ?? []}
            tylkoOdczyt={tylkoOdczyt}
            onWskaznik={(id) => przelaczWskaznik(k.kompetencja_id, id)}
          />
        ))}
      </section>

      <section>
        <div className="wiersz">
          <h2>Kryteria dodatkowe</h2>
          {dane.limit_dodatkowych > 0 && (
            <span className="meta">
              wybrano {dodatkowe.length} z {dane.limit_dodatkowych}
            </span>
          )}
        </div>
        <Zrodla adnotacje={dane.podstawa_dodatkowych} />
        {dane.limit_dodatkowych === 0 ? (
          <p className="brak">W pierwszej ocenie nie ma kryteriów dodatkowych.</p>
        ) : (
          <>
            {proponowane.map(kartaDodatkowego)}
            {dostepne.length > 0 && (
              <details className="pozostale">
                <summary>Pozostałe kompetencje ({dostepne.length})</summary>
                {dostepne.map(kartaDodatkowego)}
              </details>
            )}
          </>
        )}
      </section>

      <section>
        <h2>Metodyka doboru</h2>
        <p>
          <span className="status uwaga">{dane.metodyka.status}</span>
        </p>
        <p>{dane.metodyka.opis}</p>
        <Zrodla adnotacje={dane.metodyka.adnotacje} />
      </section>

      {moznaProwadzic && (
        <section>
          <h2>Zatwierdzenie</h2>
          <form onSubmit={zapisz}>
            {pusteKryteria.length > 0 && (
              <p className="brak">Każde wybrane kryterium musi mieć co najmniej jeden wskaźnik.</p>
            )}
            <div className="wiersz">
              <span className="meta">
                Kryteriów: {wybrane.length} · wskaźników: {liczbaWskaznikow}
              </span>
              <button disabled={czekam || pusteKryteria.length > 0}>
                {czekam ? "Zapisuję…" : "Zatwierdź kryteria i wskaźniki"}
              </button>
            </div>
          </form>
          {zapisano && <p className="sukces">{zapisano}</p>}
          {(zapisano || dane.wybor) && dalej}
          {blad && <p className="blad">{blad}</p>}
        </section>
      )}
    </>
  );
}
