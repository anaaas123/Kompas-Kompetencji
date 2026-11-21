import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzOcene,
  przygotujRozmowe,
  zapiszDecyzje,
  zapiszWskazniki,
  type KryteriumOceny,
  type OcenaWskaznika,
  type Pracownik,
  type ProcesOceny,
  type Przyklad,
  type StanOceny,
  type Sugestia,
  type WskaznikOceny,
} from "./api";
import { NAZWA_SCIEZKI, Zrodla, nazwaKryterium, opisBledu } from "./Krok1";
import { LegendaPorownania, SamoocenaPrzyWskazniku, StatusSamoocenyPrzelozonego } from "./Samoocena";
import { data } from "./zespol-dane";
import "./krok2.css";
import "./ocena.css";

const POWTARZALNOSC = { JEDNORAZOWE: "jednorazowe", KILKAKROTNE: "kilkakrotne", REGULARNE: "regularne" } as const;
const ZLOZONOSC = { NISKA: "niska", SREDNIA: "średnia", WYSOKA: "wysoka" } as const;

function bladZapisu(err: unknown): string {
  if (err instanceof BladApi && err.status === 409) return "Proces oceny nie jest w toku albo krok 2 nie jest zapisany.";
  // Pracownik przed przekazaniem samooceny: komunikat z API („Ocena przełożonego będzie widoczna…”).
  if (err instanceof BladApi && err.status === 403 && typeof err.detail === "string") return err.detail;
  const bledy = err instanceof BladApi ? (err.detail as { bledy?: string[] } | null)?.bledy : undefined;
  return Array.isArray(bledy) ? bledy.join(" ") : opisBledu(err);
}

export function Wybor<T extends string | number>({
  etykieta,
  opcje,
  wartosc,
  zablokowane,
  onWybierz,
}: {
  etykieta: string;
  opcje: { wartosc: T; tekst: string; opis?: string }[];
  wartosc: T | null;
  zablokowane: boolean;
  onWybierz: (w: T | null) => void;
}) {
  return (
    <div className="wybor" role="group" aria-label={etykieta}>
      {opcje.map((o) => (
        <button
          key={String(o.wartosc)}
          type="button"
          aria-pressed={wartosc === o.wartosc}
          aria-label={o.opis}
          disabled={zablokowane}
          onClick={() => onWybierz(wartosc === o.wartosc ? null : o.wartosc)}
        >
          {o.tekst}
        </button>
      ))}
    </div>
  );
}

function NowyPrzyklad({ onZapisz, onAnuluj }: { onZapisz: (p: Przyklad) => void; onAnuluj: () => void }) {
  const [p, setP] = useState<Przyklad>({
    sytuacja: "",
    dzialanie: "",
    rezultat: "",
    powtarzalnosc: null,
    zlozonosc: null,
    uprawnienia: null,
  });
  const pelny = p.sytuacja.trim() && p.dzialanie.trim() && p.rezultat.trim();
  const pole = (klucz: "sytuacja" | "dzialanie" | "rezultat", nazwa: string) => (
    <label className="etykieta">
      {nazwa}
      <textarea rows={2} value={p[klucz]} onChange={(e) => setP({ ...p, [klucz]: e.target.value })} />
    </label>
  );
  return (
    <div className="nowy-przyklad">
      {pole("sytuacja", "Sytuacja")}
      {pole("dzialanie", "Działanie")}
      {pole("rezultat", "Rezultat")}
      <div className="etykieta">Powtarzalność</div>
      <Wybor
        etykieta="Powtarzalność"
        opcje={Object.entries(POWTARZALNOSC).map(([w, t]) => ({ wartosc: w as Przyklad["powtarzalnosc"] & string, tekst: t }))}
        wartosc={p.powtarzalnosc}
        zablokowane={false}
        onWybierz={(w) => setP({ ...p, powtarzalnosc: w })}
      />
      <div className="etykieta">Złożoność</div>
      <Wybor
        etykieta="Złożoność"
        opcje={Object.entries(ZLOZONOSC).map(([w, t]) => ({ wartosc: w as Przyklad["zlozonosc"] & string, tekst: t }))}
        wartosc={p.zlozonosc}
        zablokowane={false}
        onWybierz={(w) => setP({ ...p, zlozonosc: w })}
      />
      <label className="etykieta">
        Uprawnienia (opcjonalnie)
        <input value={p.uprawnienia ?? ""} onChange={(e) => setP({ ...p, uprawnienia: e.target.value || null })} />
      </label>
      <div className="wiersz">
        <button type="button" className="link" onClick={onAnuluj}>
          Anuluj
        </button>
        <button
          type="button"
          className="jasny"
          disabled={!pelny}
          onClick={() =>
            onZapisz({ ...p, sytuacja: p.sytuacja.trim(), dzialanie: p.dzialanie.trim(), rezultat: p.rezultat.trim() })
          }
        >
          Zapisz przykład
        </button>
      </div>
    </div>
  );
}

/** Poziom „na poziomie oczekiwań” to standard stanowiska (instrukcja modelu kompetencji, A4). */
const oczekiwany = (etykieta: string) => /na poziomie oczekiwań/i.test(etykieta);
/** Krótka nazwa poziomu do planu: „powyżej”, „na poziomie”. */
const krotko = (etykieta: string) => etykieta.replace(/ oczekiwań$/i, "").toLowerCase();

function stanWskaznika(w: WskaznikOceny): string {
  if (w.ocena?.brak_podstaw) return "brak podstaw";
  const p = w.poziomy.find((x) => x.poziom === w.ocena?.poziom);
  return p ? `${krotko(p.etykieta)} · ${p.poziom}` : "";
}

/** Jeden wskaźnik: pytanie do rozmowy, pięć odpowiedzi z opisem zachowania, przykład. */
function EkranWskaznika({
  kr,
  w,
  nr,
  pytania,
  tylkoOdczyt,
  czekam,
  blad,
  onZapisz,
}: {
  kr: KryteriumOceny;
  w: WskaznikOceny;
  nr: number;
  pytania: string[];
  tylkoOdczyt: boolean;
  czekam: boolean;
  blad?: string;
  onZapisz: (o: OcenaWskaznika) => void;
}) {
  const [dodaje, setDodaje] = useState(false);
  const przyklady = w.ocena?.przyklady ?? [];
  const zablokowane = tylkoOdczyt || czekam;
  const brak = w.ocena?.brak_podstaw ?? false;

  return (
    <div className="oc-ekran">
      <p className="meta">
        {nazwaKryterium(kr.nazwa)} · wskaźnik {nr} z {kr.wskazniki.length}
      </p>
      <h2 className="oc-tytul">{w.nazwa}</h2>

      {pytania.length > 0 && (
        <div className="oc-pytanie">
          <p className="etykieta">Zapytaj na rozmowie</p>
          {pytania.map((p) => (
            <p key={p}>{p}</p>
          ))}
          <p className="meta">Słuchaj: sytuacja · działanie · rezultat · czy to się powtarzało</p>
        </div>
      )}

      <div className="oc-odpowiedzi" role="radiogroup" aria-label={`Poziom: ${w.nazwa}`}>
        {w.poziomy.map((p) => {
          const wybrany = !brak && w.ocena?.poziom === p.poziom;
          return (
            <button
              key={p.poziom}
              type="button"
              role="radio"
              aria-checked={wybrany}
              className="oc-odpowiedz"
              disabled={zablokowane}
              onClick={() => onZapisz({ poziom: p.poziom, brak_podstaw: false, przyklady })}
            >
              <span className="oc-znacznik" aria-hidden="true" />
              <span className="oc-tresc">
                <span className="oc-etykieta">
                  {p.etykieta}
                  {oczekiwany(p.etykieta) && <span className="znacznik">oczekiwany</span>}
                </span>
                <span className="oc-opis">{p.opis}</span>
              </span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="link oc-brak"
        aria-pressed={brak}
        disabled={zablokowane}
        onClick={() => onZapisz({ poziom: null, brak_podstaw: !brak, przyklady })}
      >
        {brak ? "Cofnij „brak podstaw”" : "Nie było okazji tego zaobserwować: brak podstaw do oceny"}
      </button>
      {brak && <p className="meta">Brak podstaw nie wchodzi do sugestii punktów.</p>}

      <SamoocenaPrzyWskazniku w={w} />

      {w.ostrzezenia.map((o) => (
        <p key={o} className="brak">
          {o}
        </p>
      ))}

      {przyklady.length > 0 && (
        <ul className="lista-przykladow">
          {przyklady.map((p, i) => (
            <li key={i}>
              <p>
                <span className="etykieta">Sytuacja:</span> {p.sytuacja} <span className="etykieta">Działanie:</span>{" "}
                {p.dzialanie} <span className="etykieta">Rezultat:</span> {p.rezultat}
              </p>
              <div className="etykiety">
                {p.powtarzalnosc && <span className="znacznik">{POWTARZALNOSC[p.powtarzalnosc]}</span>}
                {p.zlozonosc && <span className="znacznik">złożoność {ZLOZONOSC[p.zlozonosc]}</span>}
                {p.uprawnienia && <span className="znacznik">{p.uprawnienia}</span>}
                {!tylkoOdczyt && (
                  <button
                    type="button"
                    className="link"
                    disabled={czekam}
                    onClick={() => w.ocena && onZapisz({ ...w.ocena, przyklady: przyklady.filter((_, j) => j !== i) })}
                  >
                    usuń
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {!tylkoOdczyt && w.ocena && !dodaje && (
        <button type="button" className="link oc-brak" onClick={() => setDodaje(true)}>
          Dodaj przykład z rozmowy
        </button>
      )}
      {dodaje && w.ocena && (
        <NowyPrzyklad
          onAnuluj={() => setDodaje(false)}
          onZapisz={(p) => {
            setDodaje(false);
            if (w.ocena) onZapisz({ ...w.ocena, przyklady: [...przyklady, p] });
          }}
        />
      )}
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}

/** „7 pkt”, „5 albo 7 pkt” albo null, gdy oceniono za mało wskaźników. */
function punktySugestii(s: Sugestia): string | null {
  if (s.status === "POZIOM") return `${s.punkty} pkt`;
  if (s.status === "REMIS") return `${(s.punkty_remisu ?? []).join(" albo ")} pkt`;
  return null;
}

const tekstSugestii = (s: Sugestia) => `Sugestia: ${punktySugestii(s) ?? "za mało ocenionych wskaźników"}`;

/** Odejście od sugestii wymaga uzasadnienia; przy niewystarczających danych nie ma od czego odchodzić. */
function wymagaUzasadnienia(s: Sugestia, punkty: number | null): boolean {
  if (punkty === null) return false;
  if (s.status === "POZIOM") return punkty !== s.punkty;
  if (s.status === "REMIS") return !(s.punkty_remisu ?? []).includes(punkty);
  return false;
}

function DecyzjaKryterium({
  kr,
  skala,
  tylkoOdczyt,
  czekam,
  blad,
  onZapisz,
}: {
  kr: KryteriumOceny;
  skala: StanOceny["skala"];
  tylkoOdczyt: boolean;
  czekam: boolean;
  blad?: string;
  onZapisz: (d: { punkty: number; uzasadnienie: string | null } | null) => void;
}) {
  const d = kr.decyzja;
  const [edytuje, setEdytuje] = useState(!d);
  const [punkty, setPunkty] = useState<number | null>(d?.punkty ?? null);
  const [uzasadnienie, setUzasadnienie] = useState(d?.uzasadnienie ?? "");
  const wymagane = wymagaUzasadnienia(kr.sugestia, punkty);

  return (
    <div className="oc-decyzja">
      {d && !edytuje && (
        <div className="sukces">
          Twoja ocena: {d.punkty} pkt ({skala.etykiety[String(d.punkty)]})
          {d.zgodna_z_sugestia === false && d.uzasadnienie && <> · uzasadnienie: {d.uzasadnienie}</>}
          {!tylkoOdczyt && (
            <div className="etykiety">
              <button type="button" className="link" onClick={() => setEdytuje(true)}>
                Zmień
              </button>
              <button type="button" className="link" disabled={czekam} onClick={() => onZapisz(null)}>
                Cofnij decyzję
              </button>
            </div>
          )}
        </div>
      )}
      {!d && tylkoOdczyt && <p className="meta">Przełożony nie zapisał jeszcze oceny kryterium.</p>}

      {!tylkoOdczyt && edytuje && (
        <>
          <p className="etykieta">Twoja ocena kryterium</p>
          <Wybor
            etykieta={`Ocena cząstkowa: ${kr.nazwa}`}
            opcje={skala.punkty.map((p) => ({ wartosc: p, tekst: `${p} pkt`, opis: `${p} pkt: ${skala.etykiety[String(p)]}` }))}
            wartosc={punkty}
            zablokowane={czekam}
            onWybierz={setPunkty}
          />
          {punkty !== null && <p className="meta">{skala.etykiety[String(punkty)]}</p>}
          {wymagane && (
            <label className="etykieta">
              Dlaczego inaczej niż sugestia (wymagane)
              <textarea rows={2} value={uzasadnienie} onChange={(e) => setUzasadnienie(e.target.value)} />
            </label>
          )}
          <div className="wiersz">
            {d ? (
              <button type="button" className="link" onClick={() => setEdytuje(false)}>
                Anuluj
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              className="jasny"
              disabled={czekam || punkty === null || (wymagane && !uzasadnienie.trim())}
              onClick={() => punkty !== null && onZapisz({ punkty, uzasadnienie: wymagane ? uzasadnienie.trim() : null })}
            >
              Zapisz ocenę kryterium
            </button>
          </div>
        </>
      )}
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}

/** Po ostatnim wskaźniku: podstawa (wskaźniki i poziomy), sugestia, poprzednie punkty, decyzja. */
function EkranKryterium({
  kr,
  skala,
  poprzednio,
  tylkoOdczyt,
  czekam,
  blad,
  onZapisz,
}: {
  kr: KryteriumOceny;
  skala: StanOceny["skala"];
  poprzednio: { punkty: number; data: string } | null;
  tylkoOdczyt: boolean;
  czekam: boolean;
  blad?: string;
  onZapisz: (d: { punkty: number; uzasadnienie: string | null } | null) => void;
}) {
  const s = kr.sugestia;
  return (
    <div className="oc-ekran">
      <p className="meta">{nazwaKryterium(kr.nazwa)} · ocena kryterium</p>
      <h2 className="oc-tytul">{nazwaKryterium(kr.nazwa)}</h2>
      <ul className="oc-podstawa">
        {kr.wskazniki.map((w) => (
          <li key={w.wskaznik_id}>
            <span>{w.nazwa}</span>
            <span className="oc-poziom">{stanWskaznika(w) || "nie oceniono"}</span>
          </li>
        ))}
      </ul>
      <div className="oc-sugestia">
        <p>
          {s.status === "NIEWYSTARCZAJACE_DANE" ? <span>{tekstSugestii(s)}</span> : <strong>{tekstSugestii(s)}</strong>}
          <span className="kategoria zasada">Zasada aplikacji</span>
        </p>
        <p className="meta">{s.opis}</p>
        <p className="meta">Sugestia niczego nie zaznacza. Punkty wybierasz Ty.</p>
      </div>
      {poprzednio && (
        <p className="meta">
          Poprzednia ocena ({data(poprzednio.data)}): {poprzednio.punkty} pkt · dane demo
        </p>
      )}
      <DecyzjaKryterium
        key={kr.decyzja?.zapisano ?? "brak"}
        kr={kr}
        skala={skala}
        tylkoOdczyt={tylkoOdczyt}
        czekam={czekam}
        blad={blad}
        onZapisz={onZapisz}
      />
    </div>
  );
}

type Krok = { typ: "wskaznik"; kr: number; w: number } | { typ: "kryterium"; kr: number } | { typ: "podsumowanie" };

function kroki(dane: StanOceny): Krok[] {
  return [
    ...dane.kryteria.flatMap((kr, i): Krok[] => [
      ...kr.wskazniki.map((_, j): Krok => ({ typ: "wskaznik", kr: i, w: j })),
      { typ: "kryterium", kr: i },
    ]),
    { typ: "podsumowanie" },
  ];
}

function etykietaDalej(k: Krok | undefined, dane: StanOceny): string {
  if (!k) return "";
  if (k.typ === "wskaznik" && k.w === 0) return `Dalej: ${nazwaKryterium(dane.kryteria[k.kr].nazwa)}`;
  if (k.typ === "wskaznik") return `Dalej: wskaźnik ${k.w + 1} z ${dane.kryteria[k.kr].wskazniki.length}`;
  if (k.typ === "kryterium") return "Dalej: ocena kryterium";
  return "Dalej: podsumowanie";
}

/** Plan z boku: kryteria z postępem, bieżące rozwinięte do wskaźników; każdy wiersz przenosi do swojego ekranu. */
function Plan({ dane, lista, biezacy, onIdz }: { dane: StanOceny; lista: Krok[]; biezacy: number; onIdz: (i: number) => void }) {
  const k = lista[biezacy];
  const krBiezace = k.typ === "podsumowanie" ? -1 : k.kr;
  const indeks = (f: (x: Krok) => boolean) => lista.findIndex(f);
  return (
    <nav className="k2-podsumowanie oc-plan" aria-label="Plan oceny">
      <h2>Plan</h2>
      <ol>
        {dane.kryteria.map((kr, i) => {
          const ocenione = kr.wskazniki.filter((w) => w.ocena?.poziom != null || w.ocena?.brak_podstaw).length;
          const celKryterium = indeks((x) => x.typ === "kryterium" && x.kr === i);
          return (
            <li key={kr.kompetencja_id}>
              <button
                type="button"
                className="oc-plan-wiersz"
                aria-current={i === krBiezace ? "step" : undefined}
                onClick={() => onIdz(indeks((x) => x.typ !== "podsumowanie" && x.kr === i))}
              >
                <span className={`oc-kropka ${kr.decyzja ? "gotowe" : ""}`} aria-hidden="true" />
                <span className="oc-plan-nazwa">{nazwaKryterium(kr.nazwa)}</span>
                <span className="meta">{kr.decyzja ? `${kr.decyzja.punkty} pkt` : `${ocenione}/${kr.wskazniki.length}`}</span>
              </button>
              {i === krBiezace && (
                <ol className="oc-plan-wskazniki">
                  {kr.wskazniki.map((w, j) => {
                    const cel = indeks((x) => x.typ === "wskaznik" && x.kr === i && x.w === j);
                    return (
                      <li key={w.wskaznik_id}>
                        <button type="button" aria-current={cel === biezacy ? "step" : undefined} onClick={() => onIdz(cel)}>
                          <span className="oc-plan-nazwa">{w.nazwa}</span>
                          <span className="meta">{stanWskaznika(w)}</span>
                        </button>
                      </li>
                    );
                  })}
                  <li>
                    <button
                      type="button"
                      aria-current={celKryterium === biezacy ? "step" : undefined}
                      onClick={() => onIdz(celKryterium)}
                    >
                      <span className="oc-plan-nazwa">Ocena kryterium</span>
                      <span className="meta">{kr.decyzja ? `${kr.decyzja.punkty} pkt` : (punktySugestii(kr.sugestia) ?? "—")}</span>
                    </button>
                  </li>
                </ol>
              )}
            </li>
          );
        })}
        <li>
          <button
            type="button"
            className="oc-plan-wiersz"
            aria-current={k.typ === "podsumowanie" ? "step" : undefined}
            onClick={() => onIdz(lista.length - 1)}
          >
            <span className="oc-kropka" aria-hidden="true" />
            <span className="oc-plan-nazwa">Podsumowanie</span>
          </button>
        </li>
      </ol>
    </nav>
  );
}

export function Ocena({
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
  const [dane, setDane] = useState<StanOceny | null>(null);
  const [pytania, setPytania] = useState<Record<string, string[]>>({});
  const [krok, setKrok] = useState(0);
  const [metodyka, setMetodyka] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const [bledy, setBledy] = useState<Record<string, string>>({});
  const [czekam, setCzekam] = useState<string | null>(null);

  useEffect(() => {
    pobierzOcene(token, proces.id)
      .then(setDane)
      .catch((err) => setBlad(bladZapisu(err)));
    // Pytania z szablonów rozmowy (konfiguracja/rozmowa.yaml); plan niczego nie zapisuje.
    if (moznaProwadzic) {
      przygotujRozmowe(token, proces.id, {})
        .then((plan) => {
          const wg: Record<string, string[]> = {};
          for (const p of plan.pytania) if (p.powiazanie.wskaznik_id) (wg[p.powiazanie.wskaznik_id] ??= []).push(p.tresc);
          setPytania(wg);
        })
        .catch(() => setPytania({}));
    }
  }, [token, proces.id, moznaProwadzic]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [krok]);

  if (!dane) {
    return <section>{blad ? <p className="blad">{blad}</p> : <p className="meta">Wczytuję ocenę…</p>}</section>;
  }

  const tylkoOdczyt = !moznaProwadzic;
  const lista = kroki(dane);
  const k = lista[Math.min(krok, lista.length - 1)];
  const poprzednie = osoba.ostatnia_ocena_okresowa;
  const kp = dane.kompletnosc;

  async function zapiszWskaznik(id: string, ocena: OcenaWskaznika) {
    setCzekam(id);
    setBledy(({ [id]: _, ...reszta }) => reszta);
    try {
      setDane(await zapiszWskazniki(token, proces.id, { [id]: ocena }));
    } catch (err) {
      setBledy((b) => ({ ...b, [id]: bladZapisu(err) }));
    } finally {
      setCzekam(null);
    }
  }

  async function zapiszDecyzje1(id: string, d: { punkty: number; uzasadnienie: string | null } | null) {
    setCzekam(id);
    setBledy(({ [id]: _, ...reszta }) => reszta);
    try {
      setDane(await zapiszDecyzje(token, proces.id, { [id]: d }));
    } catch (err) {
      setBledy((b) => ({ ...b, [id]: bladZapisu(err) }));
    } finally {
      setCzekam(null);
    }
  }

  let ekran;
  if (k.typ === "wskaznik") {
    const kr = dane.kryteria[k.kr];
    const w = kr.wskazniki[k.w];
    ekran = (
      <EkranWskaznika
        key={w.wskaznik_id}
        kr={kr}
        w={w}
        nr={k.w + 1}
        pytania={pytania[w.wskaznik_id] ?? []}
        tylkoOdczyt={tylkoOdczyt}
        czekam={czekam === w.wskaznik_id}
        blad={bledy[w.wskaznik_id]}
        onZapisz={(o) => zapiszWskaznik(w.wskaznik_id, o)}
      />
    );
  } else if (k.typ === "kryterium") {
    const kr = dane.kryteria[k.kr];
    const p = poprzednie?.kryteria?.find((x) => x.kompetencja_id === kr.kompetencja_id);
    ekran = (
      <EkranKryterium
        key={kr.kompetencja_id}
        kr={kr}
        skala={dane.skala}
        poprzednio={p && poprzednie ? { punkty: p.punkty, data: poprzednie.data } : null}
        tylkoOdczyt={tylkoOdczyt}
        czekam={czekam === kr.kompetencja_id}
        blad={bledy[kr.kompetencja_id]}
        onZapisz={(d) => zapiszDecyzje1(kr.kompetencja_id, d)}
      />
    );
  } else {
    ekran = (
      <div className="oc-ekran">
        <h2 className="oc-tytul">Podsumowanie</h2>
        <table>
          <thead>
            <tr>
              <th>Kryterium</th>
              <th>Sugestia</th>
              <th>Twoja ocena</th>
              <th aria-label="Akcja" />
            </tr>
          </thead>
          <tbody>
            {dane.kryteria.map((kr) => (
              <tr key={kr.kompetencja_id}>
                <td>{nazwaKryterium(kr.nazwa)}</td>
                <td>{punktySugestii(kr.sugestia) ?? "za mało danych"}</td>
                <td>{kr.decyzja ? `${kr.decyzja.punkty} pkt` : "—"}</td>
                <td>
                  <button
                    type="button"
                    className="link"
                    onClick={() => setKrok(lista.findIndex((x) => x.typ === "kryterium" && dane.kryteria[x.kr] === kr))}
                  >
                    {kr.decyzja ? "Zmień" : "Oceń"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="meta">
          {kp.kryteria_z_decyzja === kp.kryteria
            ? "Wszystkie kryteria mają ocenę. Średnią i warunki oceny policzy krok 7."
            : `Ocenione kryteria: ${kp.kryteria_z_decyzja} z ${kp.kryteria}. Możesz wrócić do nich po rozmowie.`}
        </p>
      </div>
    );
  }

  const nastepny = lista[krok + 1];

  return (
    <div className="k2">
      <div className="k2-naglowek">
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do kroku 2
        </button>
        <p className="meta">Kroki 3–5 z 8</p>
        <h1>Oceń kompetencje</h1>
        <p className="opis">
          {osoba.imie} {osoba.nazwisko} · {NAZWA_SCIEZKI[dane.sciezka]} · arkusz{" "}
          {dane.arkusz === "PIERWSZA" ? "pierwszej oceny" : dane.arkusz}
        </p>
      </div>
      <StatusSamoocenyPrzelozonego status={dane.samoocena_status} />
      {dane.samoocena_status === "przekazana" && <LegendaPorownania />}

      <div className="dwie">
        <div className="sekcja k2-glowna">
          {ekran}
          <div className="oc-nawigacja">
            {krok > 0 ? (
              <button type="button" className="link" onClick={() => setKrok(krok - 1)}>
                Wstecz
              </button>
            ) : (
              <span />
            )}
            {nastepny ? (
              <button type="button" onClick={() => setKrok(krok + 1)}>
                {etykietaDalej(nastepny, dane)}
              </button>
            ) : (
              <button type="button" onClick={onDalej}>
                Dalej: rozmowa oceniająca
              </button>
            )}
          </div>
        </div>

        <aside className="sekcja k2-boczna">
          <Plan dane={dane} lista={lista} biezacy={Math.min(krok, lista.length - 1)} onIdz={setKrok} />
          <div className="k2-metodyka">
            <button type="button" className="link" aria-expanded={metodyka} onClick={() => setMetodyka((v) => !v)}>
              {metodyka ? "Ukryj zasady" : "Jak oceniać i skąd sugestia?"}
            </button>
            {metodyka && (
              <>
                {dane.instrukcja.map((i) => (
                  <div key={i.tekst}>
                    <p className="meta">{i.tekst}</p>
                    <Zrodla adnotacje={[i.adnotacja]} />
                  </div>
                ))}
                <p className="meta">{dane.metodyka.opis}</p>
                <Zrodla adnotacje={dane.metodyka.adnotacje} />
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
