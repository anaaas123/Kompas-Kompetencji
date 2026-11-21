import { FormEvent, useEffect, useState } from "react";
import {
  BladApi,
  pobierzKrok2,
  zapiszKrok2,
  type Krok2 as DaneKroku2,
  type KryteriumKroku2,
  type Pracownik,
  type ProcesOceny,
  type SourceRef,
} from "./api";
import { NAZWA_SCIEZKI, Zrodla, opisBledu } from "./Krok1";
import { Ikona } from "./Ikona";
import "./krok2.css";

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

/** Źródła wskaźników kryterium bez powtórzeń: zwykle wszystkie stoją na tym samym miejscu rozporządzenia. */
function zrodlaKryterium(k: KryteriumKroku2): SourceRef[] {
  const widziane = new Set<string>();
  return k.wskazniki
    .map((w) => w.podstawa)
    .filter((a) => {
      const klucz = `${a.doc_id}|${a.lokalizator}|${a.strona}`;
      if (widziane.has(klucz)) return false;
      widziane.add(klucz);
      return true;
    });
}

type PropsKryterium = {
  k: KryteriumKroku2;
  wybrane: string[];
  tylkoOdczyt: boolean;
  otwarte: boolean;
  onPrzelacz: () => void;
  onWskaznik: (id: string) => void;
  /** Kryterium dodatkowe: pole wyboru całego kryterium w nagłówku wiersza. */
  dodatkowe?: { wybrane: boolean; zablokowane: boolean; onWybierz: () => void };
};

/** Kryterium jako zwijany wiersz: nagłówek z licznikiem, po rozwinięciu wskaźniki i źródło raz na kryterium. */
function Kryterium({ k, wybrane, tylkoOdczyt, otwarte, onPrzelacz, onWskaznik, dodatkowe }: PropsKryterium) {
  const aktywne = !dodatkowe || dodatkowe.wybrane;
  const pasujace = k.wskazniki.filter((w) => w.proponowany).length;
  return (
    <div className={`k2-kryterium ${otwarte && aktywne ? "otwarte" : ""} ${aktywne ? "" : "nieaktywne"}`}>
      <div className="k2-glowa">
        {dodatkowe && (
          <label className="k2-wybierz">
            <input
              type="checkbox"
              aria-label={`Wybierz kryterium ${k.nazwa}`}
              checked={dodatkowe.wybrane}
              disabled={tylkoOdczyt || dodatkowe.zablokowane}
              onChange={dodatkowe.onWybierz}
            />
          </label>
        )}
        <button type="button" className="k2-przelacz" aria-expanded={otwarte && aktywne} disabled={!aktywne} onClick={onPrzelacz}>
          <span className="k2-nazwa">
            {k.nazwa.charAt(0) + k.nazwa.slice(1).toLowerCase()}
            {k.propozycja && <span className="status uwaga">propozycja systemu</span>}
          </span>
          <span className="k2-opis">
            {aktywne
              ? `${wybrane.length} z ${k.wskazniki.length} wskaźników${pasujace ? ` · ${pasujace} pasuje do zadań z OSP` : ""}`
              : k.propozycja
                ? k.propozycja.powody.join("; ")
                : `${k.wskazniki.length} wskaźników`}
          </span>
          {aktywne && <Ikona nazwa={otwarte ? "gora" : "dalej"} rozmiar={20} />}
        </button>
      </div>
      {otwarte && aktywne && (
        <div className="k2-cialo">
          {k.propozycja && <p className="meta">Dlaczego: {k.propozycja.powody.join("; ")}</p>}
          <ul className="k2-wskazniki">
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
                    {w.nazwa}
                    {w.zadania.length > 0 && (
                      <span className="k2-zadania" title={w.zadania.map((z) => `${z.nr}. ${z.tekst}`).join("\n")}>
                        zadania z OSP: {w.zadania.map((z) => z.nr).join(", ")}
                      </span>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <Zrodla adnotacje={[...zrodlaKryterium(k), ...(k.propozycja?.adnotacje ?? [])]} />
        </div>
      )}
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
  const [otwarte, setOtwarte] = useState<string[]>([]);
  const [pozostale, setPozostale] = useState(false);
  const [metodyka, setMetodyka] = useState(false);

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

  const przelaczOtwarte = (id: string) => setOtwarte((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));
  const wiersz = (k: KryteriumKroku2, dodatkoweKryterium: boolean) => {
    const wybrany = dodatkowe.includes(k.kompetencja_id);
    return (
      <Kryterium
        key={k.kompetencja_id}
        k={k}
        wybrane={wskazniki[k.kompetencja_id] ?? []}
        tylkoOdczyt={tylkoOdczyt}
        otwarte={otwarte.includes(k.kompetencja_id)}
        onPrzelacz={() => przelaczOtwarte(k.kompetencja_id)}
        onWskaznik={(id) => przelaczWskaznik(k.kompetencja_id, id)}
        dodatkowe={
          dodatkoweKryterium
            ? {
                wybrane: wybrany,
                zablokowane: !wybrany && dodatkowe.length >= dane.limit_dodatkowych,
                onWybierz: () => przelaczDodatkowe(k),
              }
            : undefined
        }
      />
    );
  };
  const dalej = (
    <button type="button" className="jasny" onClick={onDalej}>
      Dalej: kroki 3–5
    </button>
  );
  const nazwaArkusza = dane.arkusz === "PIERWSZA" ? "pierwszej oceny" : dane.arkusz;

  return (
    <div className="k2">
      <div className="k2-naglowek">
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do kroku 1
        </button>
        <p className="meta">Krok 2 z 8</p>
        <h1>Kryteria i wskaźniki</h1>
        <p className="opis">
          {osoba.imie} {osoba.nazwisko} · {NAZWA_SCIEZKI[dane.sciezka]} · arkusz {nazwaArkusza}
        </p>
      </div>

      <div className="dwie">
        <div className="sekcja k2-glowna">
          {tylkoOdczyt && !dane.wybor && (
            <p className="brak">Przełożony nie zatwierdził jeszcze kryteriów. Zaznaczenia to propozycja systemu.</p>
          )}
          <div className="k2-grupa">
            <h2>
              Obowiązkowe <span className="meta">{obowiazkowe.length}</span>
            </h2>
            {obowiazkowe.map((k) => wiersz(k, false))}
          </div>

          <div className="k2-grupa">
            <h2>
              Dodatkowe{" "}
              {dane.limit_dodatkowych > 0 && (
                <span className="meta">
                  wybrano {dodatkowe.length} z {dane.limit_dodatkowych}
                </span>
              )}
            </h2>
            {dane.limit_dodatkowych === 0 ? (
              <p className="meta">W pierwszej ocenie nie ma kryteriów dodatkowych.</p>
            ) : (
              <>
                {proponowane.map((k) => wiersz(k, true))}
                {dostepne.length > 0 && (
                  <>
                    <button type="button" className="link k2-pozostale" aria-expanded={pozostale} onClick={() => setPozostale((v) => !v)}>
                      {pozostale ? "Ukryj pozostałe kompetencje" : `Pozostałe kompetencje (${dostepne.length})`}
                    </button>
                    {pozostale && dostepne.map((k) => wiersz(k, true))}
                  </>
                )}
              </>
            )}
          </div>
        </div>

        <aside className="sekcja k2-boczna">
          <div className="k2-podsumowanie">
            <h2>Podsumowanie</h2>
            <dl>
              <div>
                <dt>Kryteria</dt>
                <dd>
                  {obowiazkowe.length} obowiązkowych{dodatkowe.length > 0 && ` + ${dodatkowe.length} dodatkowe`}
                </dd>
              </div>
              <div>
                <dt>Wskaźniki</dt>
                <dd>{liczbaWskaznikow}</dd>
              </div>
            </dl>
            {dane.wybor && !zapisano && (
              <p className="sukces">
                Zapisany wybór: {dane.wybor.kryteria.length} kryteriów, zapisał {dane.wybor.zapisal}.
              </p>
            )}
            {moznaProwadzic && (
              <form onSubmit={zapisz}>
                {pusteKryteria.length > 0 && (
                  <p className="brak">Każde wybrane kryterium musi mieć co najmniej jeden wskaźnik.</p>
                )}
                <button className="k2-zatwierdz" disabled={czekam || pusteKryteria.length > 0}>
                  {czekam ? "Zapisuję…" : "Zatwierdź kryteria i wskaźniki"}
                </button>
              </form>
            )}
            {zapisano && <p className="sukces">{zapisano}</p>}
            {(zapisano || dane.wybor) && dalej}
            {blad && <p className="blad">{blad}</p>}
          </div>

          <div className="k2-metodyka">
            <button type="button" className="link" aria-expanded={metodyka} onClick={() => setMetodyka((v) => !v)}>
              {metodyka ? "Ukryj, jak system dobrał wskaźniki" : "Jak system dobrał wskaźniki?"}
            </button>
            {metodyka && (
              <>
                <p>
                  <span className="status uwaga">{dane.metodyka.status}</span>
                </p>
                <p className="meta">{dane.metodyka.opis}</p>
                <Zrodla adnotacje={[...dane.metodyka.adnotacje, ...dane.podstawa_obowiazkowych, ...dane.podstawa_dodatkowych]} />
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
