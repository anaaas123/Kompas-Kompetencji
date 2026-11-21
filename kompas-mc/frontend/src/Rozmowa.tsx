import { useCallback, useEffect, useRef, useState } from "react";
import { BladApi, pobierzOcene, przygotujRozmowe, type DaneRozmowy, type PlanRozmowy, type Pracownik, type ProcesOceny, type PytanieRozmowy, type StanOceny } from "./api";
import { AgendaRozbieznosci } from "./Samoocena";
import { NAZWA_SCIEZKI, Zrodla, opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";

const TAK_NIE = [
  { wartosc: "tak", tekst: "tak" },
  { wartosc: "nie", tekst: "nie" },
] as const;

const naBool = (w: "tak" | "nie" | null) => (w === null ? null : w === "tak");

function powiazanie(p: PytanieRozmowy["powiazanie"]): string {
  if (p.typ === "zadanie_osp") return `zadanie ${p.zadanie_osp} z OSP`;
  if (p.typ === "przepis") return "zakres rozmowy z przepisu";
  const co = p.typ === "przyklad" ? "przykład" : "wskaźnik";
  return p.wskaznik ? `${co}: ${p.wskaznik}` : co;
}

export function Rozmowa({
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
  const [plan, setPlan] = useState<PlanRozmowy | null>(null);
  // Samoocena przy rozmowie (#9): status i rozbieżności z GET /ocena (przełożony, po przekazaniu).
  const [stanOceny, setStanOceny] = useState<StanOceny | null>(null);
  const [pytania, setPytania] = useState<Record<string, string>>({});
  const [mocne, setMocne] = useState("");
  const [rozwoj, setRozwoj] = useState("");
  const [cele, setCele] = useState("");
  const [sprawozdanie, setSprawozdanie] = useState<"tak" | "nie" | null>(null);
  const [egzamin, setEgzamin] = useState<"tak" | "nie" | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const ostatnie = useRef(0);

  const przygotuj = useCallback(
    async (dane: DaneRozmowy) => {
      // Liczy się tylko odpowiedź na ostatnie zapytanie (podwójny efekt w trybie deweloperskim, szybkie kliknięcia).
      const nr = ++ostatnie.current;
      setCzekam(true);
      setBlad(null);
      try {
        const p = await przygotujRozmowe(token, proces.id, dane);
        if (nr !== ostatnie.current) return;
        setPlan(p);
        setPytania(Object.fromEntries(p.pytania.map((q) => [q.id, q.tresc])));
        setMocne(p.informacja_zwrotna.mocne_strony.join("\n"));
        setRozwoj(p.informacja_zwrotna.obszary_rozwoju.join("\n"));
      } catch (err) {
        if (nr !== ostatnie.current) return;
        setBlad(err instanceof BladApi && err.status === 409 ? "Najpierw zapisz kryteria i wskaźniki (krok 2)." : opisBledu(err));
      } finally {
        if (nr === ostatnie.current) setCzekam(false);
      }
    },
    [token, proces.id],
  );

  useEffect(() => {
    if (moznaProwadzic) przygotuj({});
  }, [moznaProwadzic, przygotuj]);

  useEffect(() => {
    pobierzOcene(token, proces.id).then(setStanOceny).catch(() => setStanOceny(null));
  }, [token, proces.id]);

  const dalej = proces.sciezka === "okresowa" && (
    <section>
      <div className="wiersz">
        <span className="meta">Następny krok: wynik i terminy</span>
        <button type="button" onClick={onDalej}>
          Dalej: wynik i terminy
        </button>
      </div>
    </section>
  );

  const naglowek = (
    <section>
      <div className="wiersz">
        <div>
          <div className="etykieta">Krok 6 z 8 · Rozmowa oceniająca</div>
          <h2>
            {osoba.imie} {osoba.nazwisko}
          </h2>
          <p className="opis">
            {NAZWA_SCIEZKI[proces.sciezka]} · plan rozmowy
          </p>
        </div>
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do kroków 3–5
        </button>
      </div>
      {!moznaProwadzic && <p className="brak">Plan rozmowy przygotowuje i widzi tylko przełożony, bo zawiera przykłady z oceny.</p>}
      {plan && (
        <p className="brak">
          {plan.oznaczenie} Zmiany w pytaniach i szkicu nie są zapisywane. Tryb: szablony bez modelu językowego ({plan.wersja}).
        </p>
      )}
      {blad && <p className="blad">{blad}</p>}
      {moznaProwadzic && !plan && !blad && <p className="meta">Przygotowuję plan…</p>}
    </section>
  );

  if (!plan) {
    return (
      <>
        {naglowek}
        {stanOceny && <AgendaRozbieznosci stan={stanOceny} />}
        {dalej}
      </>
    );
  }

  return (
    <>
      {naglowek}

      {stanOceny && <AgendaRozbieznosci stan={stanOceny} />}

      <section>
        <h2>Zakres rozmowy</h2>
        <ol className="zadania">
          {plan.zakres.map((z) => (
            <li key={z.id}>
              {z.punkt}
              <Zrodla adnotacje={z.adnotacje} />
            </li>
          ))}
        </ol>
      </section>

      {plan.kwestie.length > 0 && (
        <section>
          <h2>Kwestie do omówienia</h2>
          {plan.kwestie.map((k) => (
            <div key={k.id} className="kryterium">
              <p className="brak">{k.tresc}</p>
              <Zrodla adnotacje={k.adnotacje} />
            </div>
          ))}
        </section>
      )}

      <section>
        <h2>Pytania ({plan.pytania.length})</h2>
        <ul className="wskazniki">
          {plan.pytania.map((q) => (
            <li key={q.id} className="kryterium">
              <div className="etykieta powiazanie">{powiazanie(q.powiazanie)}</div>
              <textarea
                rows={2}
                aria-label="Treść pytania"
                value={pytania[q.id] ?? ""}
                onChange={(e) => setPytania((p) => ({ ...p, [q.id]: e.target.value }))}
              />
              <p className="meta">Dlaczego: {q.uzasadnienie}</p>
              <Zrodla adnotacje={q.adnotacje} />
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Argumenty: zachowanie, przykład, rezultat</h2>
        <ul className="wskazniki">
          {plan.argumenty.map((a) => (
            <li key={a.wskaznik_id} className="kryterium">
              <strong>{a.wskaznik}</strong>
              <p className="meta">
                {a.kompetencja}
                {a.poziom !== null && ` · ${a.poziom} (${a.etykieta})`}
              </p>
              {a.zachowanie && (
                <p>
                  <span className="etykieta">Zachowanie z modelu:</span> {a.zachowanie}
                </p>
              )}
              {a.zachowanie_zrodlo && <Zrodla adnotacje={[a.zachowanie_zrodlo]} />}
              {a.przyklad && (
                <p>
                  <span className="etykieta">Przykład:</span> {a.przyklad}
                  {a.rezultat && (
                    <>
                      {" "}
                      <span className="etykieta">Rezultat:</span> {a.rezultat}
                    </>
                  )}
                </p>
              )}
              {a.uwaga && <p className="brak">{a.uwaga}</p>}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Informacja zwrotna (szkic)</h2>
        <fieldset className="formularz">
          <label className="etykieta">
            Mocne strony
            <textarea rows={4} value={mocne} onChange={(e) => setMocne(e.target.value)} />
          </label>
          <label className="etykieta">
            Obszary rozwoju
            <textarea
              rows={3}
              value={rozwoj}
              placeholder="Asystent nie znalazł obszarów rozwoju w ocenach. Dopisz je sam."
              onChange={(e) => setRozwoj(e.target.value)}
            />
          </label>
        </fieldset>
      </section>

      <section>
        <details className="pozostale">
          <summary>Dane do planu (opcjonalnie)</summary>
          <fieldset className="formularz" disabled={czekam}>
            <label className="etykieta">
              Cele na okres oceny, każdy w osobnym wierszu
              <textarea rows={3} value={cele} onChange={(e) => setCele(e.target.value)} />
            </label>
            <div className="etykieta">Sprawozdanie złożone w terminie</div>
            <Wybor etykieta="Sprawozdanie w terminie" opcje={[...TAK_NIE]} wartosc={sprawozdanie} zablokowane={czekam} onWybierz={setSprawozdanie} />
            <div className="etykieta">Egzamin obowiązkowy</div>
            <Wybor etykieta="Egzamin obowiązkowy" opcje={[...TAK_NIE]} wartosc={egzamin} zablokowane={czekam} onWybierz={setEgzamin} />
            <div className="wiersz">
              <span className="meta">Nowy plan zastąpi zmiany w pytaniach i szkicu.</span>
              <button
                type="button"
                className="jasny"
                onClick={() =>
                  przygotuj({
                    cele: cele.split("\n").map((c) => c.trim()).filter(Boolean),
                    sprawozdanie_zlozone_w_terminie: naBool(sprawozdanie),
                    egzamin_obowiazkowy: naBool(egzamin),
                  })
                }
              >
                {czekam ? "Przygotowuję…" : "Przygotuj plan ponownie"}
              </button>
            </div>
          </fieldset>
        </details>
      </section>

      {dalej}
    </>
  );
}
