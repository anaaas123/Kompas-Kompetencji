import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BladApi, pobierzOcene, przygotujRozmowe, pytajWczacieRozmowy, type DaneRozmowy, type OdpowiedzCzatuRozmowy, type PlanRozmowy, type Pracownik, type ProcesOceny, type PytanieRozmowy, type StanOceny } from "./api";
import { AgendaRozbieznosci } from "./Samoocena";
import { NAZWA_SCIEZKI, Zrodla, nazwaKryterium, opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";
import { Ikona } from "./Ikona";
import { Zwijane } from "./Zwijane";
import "./krok2.css";

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
      <div className="k2-naglowek">
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do kroków 3–5
        </button>
        <p className="meta">Krok 6 z 8</p>
        <h1>Rozmowa oceniająca</h1>
        <p className="opis">
          {osoba.imie} {osoba.nazwisko} · {NAZWA_SCIEZKI[proces.sciezka]}
        </p>
      </div>
      {!moznaProwadzic && <p className="brak">Plan rozmowy przygotowuje i widzi tylko przełożony, bo zawiera przykłady z oceny.</p>}
      {plan && <p className="meta">Pytania i szkic to podpowiedzi do rozmowy. Możesz je zmieniać – nie są zapisywane.</p>}
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

  // Wszystkie pytania zostają (Karol 21.11): grupy według § 10 i kryteriów, zwijane; najpierw obowiązki z OSP.
  const grupy = new Map<string, PytanieRozmowy[]>();
  for (const q of plan.pytania) {
    const t = q.powiazanie.typ;
    const nazwa =
      t === "zadanie_osp" ? "Obowiązki z opisu stanowiska" : t === "przepis" ? "Cele i rozwój" : nazwaKryterium(q.powiazanie.kompetencja ?? "Inne");
    grupy.set(nazwa, [...(grupy.get(nazwa) ?? []), q]);
  }
  const kolejnosc = (n: string) => (n === "Obowiązki z opisu stanowiska" ? 0 : n === "Cele i rozwój" ? 2 : 1);
  const listaGrup = [...grupy].sort(([a], [b]) => kolejnosc(a) - kolejnosc(b));
  // Wskaźniki poniżej oczekiwań (poziom niższy niż „na poziomie oczekiwań”) idą na górę rozmowy.
  const ponizej = (stanOceny?.kryteria ?? []).flatMap((k) =>
    k.wskazniki.flatMap((w) => {
      const standard = w.poziomy.find((x) => /na poziomie oczekiwań/i.test(x.etykieta))?.poziom;
      const wybrany = w.poziomy.find((x) => x.poziom === w.ocena?.poziom);
      return standard !== undefined && wybrany && wybrany.poziom < standard ? [{ k: k.nazwa, w, wybrany }] : [];
    }),
  );
  const przyklady = plan.argumenty.filter((a) => a.przyklad);

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

      {ponizej.length > 0 && (
        <section>
          <h2>Najpierw omów: poniżej oczekiwań</h2>
          <ul className="oc-podstawa">
            {ponizej.map(({ k, w, wybrany }) => (
              <li key={w.wskaznik_id}>
                <span>
                  <span className="etykieta">{nazwaKryterium(k)}</span>
                  <br />
                  {w.nazwa}
                </span>
                <span className="oc-poziom">{wybrany.etykieta.toLowerCase()}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>Pytania ({plan.pytania.length})</h2>
        <div className="k2-grupa">
          {listaGrup.map(([nazwa, lista]) => (
            <GrupaPytan
              key={nazwa}
              nazwa={nazwa}
              lista={lista}
              pytania={pytania}
              onZmien={(id, t) => setPytania((p) => ({ ...p, [id]: t }))}
            />
          ))}
        </div>
      </section>

      {przyklady.length > 0 && (
        <section>
          <h2>Przykłady z oceny</h2>
          <ul className="wskazniki">
            {przyklady.map((a) => (
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
      )}

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
        <h2>Zapytaj asystenta o rozmowę</h2>
        <CzatRozmowy token={token} procesId={proces.id} />
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

/** Grupa pytań jako zwijany wiersz (wzór kroku 2); powód i źródło raz na grupę. */
function GrupaPytan({
  nazwa,
  lista,
  pytania,
  onZmien,
}: {
  nazwa: string;
  lista: PytanieRozmowy[];
  pytania: Record<string, string>;
  onZmien: (id: string, tresc: string) => void;
}) {
  const [otwarte, setOtwarte] = useState(false);
  const zrodla = [...new Map(lista.flatMap((q) => q.adnotacje).map((a) => [`${a.doc_id}|${a.lokalizator}`, a])).values()];
  const powody = [...new Set(lista.map((q) => q.uzasadnienie))];
  return (
    <div className="k2-kryterium">
      <div className="k2-glowa">
        <button type="button" className="k2-przelacz" aria-expanded={otwarte} onClick={() => setOtwarte((v) => !v)}>
          <span className="k2-nazwa">{nazwa}</span>
          <span className="k2-opis">{lista.length === 1 ? "1 pytanie" : `${lista.length} pytania`}</span>
          <Ikona nazwa={otwarte ? "gora" : "dalej"} rozmiar={20} />
        </button>
      </div>
      <Zwijane otwarte={otwarte}>
        <div className="k2-cialo">
          {lista.map((q) => (
            <label key={q.id} className="etykieta rozmowa-pytanie">
              {powiazanie(q.powiazanie)}
              <textarea rows={2} value={pytania[q.id] ?? ""} onChange={(e) => onZmien(q.id, e.target.value)} />
            </label>
          ))}
          {powody.map((p) => (
            <p key={p} className="meta">
              Dlaczego: {p}
            </p>
          ))}
          <Zrodla adnotacje={zrodla} />
        </div>
      </Zwijane>
    </div>
  );
}

interface WymianaCzatu {
  id: number;
  pytanie: string;
  odpowiedz?: OdpowiedzCzatuRozmowy;
  blad?: string;
}

function CzatRozmowy({ token, procesId }: { token: string; procesId: number }) {
  const [pytanie, setPytanie] = useState("");
  const [historia, setHistoria] = useState<WymianaCzatu[]>([]);
  const [czekam, setCzekam] = useState(false);

  async function wyslij(e: FormEvent) {
    e.preventDefault();
    const tekst = pytanie.trim();
    if (!tekst || czekam) return;
    const id = Date.now();
    setHistoria((h) => [...h, { id, pytanie: tekst }]);
    setPytanie("");
    setCzekam(true);
    try {
      const odpowiedz = await pytajWczacieRozmowy(token, procesId, tekst);
      setHistoria((h) => h.map((w) => (w.id === id ? { ...w, odpowiedz } : w)));
    } catch (err) {
      setHistoria((h) => h.map((w) => (w.id === id ? { ...w, blad: opisBledu(err) } : w)));
    } finally {
      setCzekam(false);
    }
  }

  return (
    <div className="czat">
      <p className="opis">
        Asystent korzysta z materiałów oraz pseudonimizowanego kontekstu tej oceny. Nie podejmuje decyzji za przełożonego.
      </p>
      <ol className="rozmowa" aria-live="polite">
        {historia.map((w) => (
          <li key={w.id}>
            <p className="pytanie">{w.pytanie}</p>
            {!w.odpowiedz && !w.blad && <p className="meta">Szukam w źródłach…</p>}
            {w.blad && <p className="blad">{w.blad}</p>}
            {w.odpowiedz && <OdpowiedzCzatu odpowiedz={w.odpowiedz} />}
          </li>
        ))}
      </ol>
      <form onSubmit={wyslij}>
        <textarea
          rows={2}
          aria-label="Pytanie do asystenta rozmowy"
          placeholder="Np. jak przekazać ocenę 3 za współpracę?"
          value={pytanie}
          onChange={(e) => setPytanie(e.target.value)}
        />
        <div className="wiersz">
          <span className="meta">Historia pozostaje w tej sesji.</span>
          <button className="jasny" disabled={czekam || !pytanie.trim()}>
            {czekam ? "Szukam…" : "Zapytaj"}
          </button>
        </div>
      </form>
    </div>
  );
}

function OdpowiedzCzatu({ odpowiedz }: { odpowiedz: OdpowiedzCzatuRozmowy }) {
  if (!odpowiedz.znaleziono) {
    return <p className="brak">{odpowiedz.komunikat} Asystent nie odpowiada bez źródła.</p>;
  }
  return (
    <div className="odpowiedz">
      <p className="brak">{odpowiedz.oznaczenie_sugestii}</p>
      {odpowiedz.tresc && <p>{odpowiedz.tresc}</p>}
      {odpowiedz.cytaty.map((cytat) => (
        <article className="cytat" key={cytat.fragment_id}>
          <div className="zrodlo">
            <strong>{cytat.dokument}</strong>
            {cytat.lokalizator && <> · {cytat.lokalizator}</>}
            {cytat.strona && <> · s. {cytat.strona}</>}
          </div>
          <blockquote>{cytat.wyrozniony || cytat.cytat}</blockquote>
        </article>
      ))}
      <p className="meta">
        Tryb: {odpowiedz.tryb} · dostawca: {odpowiedz.dostawca}
      </p>
    </div>
  );
}
