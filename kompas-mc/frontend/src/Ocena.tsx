import { useEffect, useState, type CSSProperties } from "react";
import {
  BladApi,
  pobierzOcene,
  pobierzKrok2,
  przygotujRozmowe,
  zapiszDecyzje,
  zapiszWskazniki,
  type KryteriumOceny,
  type OcenaWskaznika,
  type Pracownik,
  type ProcesOceny,
  type StanOceny,
  type Sugestia,
  type WskaznikOceny,
} from "./api";
import { NAZWA_SCIEZKI, Zrodla, nazwaKryterium, opisBledu } from "./Krok1";
import { LegendaPorownania, SamoocenaPrzyWskazniku, StatusSamoocenyPrzelozonego } from "./Samoocena";
import { data } from "./zespol-dane";
import { usePoprzedniaOcena } from "./PoprzedniaOcena";
import { Zwijane } from "./Zwijane";
import { Ikona } from "./Ikona";
import "./krok2.css";
import "./ocena.css";

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

/** Poziom „na poziomie oczekiwań” to standard stanowiska (instrukcja modelu kompetencji, A4). */
const oczekiwany = (etykieta: string) => /na poziomie oczekiwań/i.test(etykieta);
/** Krótka nazwa poziomu: „powyżej”, „na poziomie”. */
const krotko = (etykieta: string) => etykieta.replace(/ oczekiwań$/i, "").toLowerCase();
const oceniony = (w: WskaznikOceny) => w.ocena?.poziom != null || !!w.ocena?.brak_podstaw;

function stanWskaznika(w: WskaznikOceny): string {
  if (w.ocena?.brak_podstaw) return "brak podstaw";
  const p = w.poziomy.find((x) => x.poziom === w.ocena?.poziom);
  return p ? `${krotko(p.etykieta)} · ${p.poziom}` : "";
}

/** „7 pkt”, „5 albo 7 pkt” albo null, gdy oceniono za mało wskaźników. */
function punktySugestii(s: Sugestia): string | null {
  if (s.status === "POZIOM") return `${s.punkty} pkt`;
  if (s.status === "REMIS") return `${(s.punkty_remisu ?? []).join(" albo ")} pkt`;
  return null;
}

const zgodnaZSugestia = (s: Sugestia, punkty: number) =>
  s.status === "POZIOM" ? punkty === s.punkty : s.status === "REMIS" ? (s.punkty_remisu ?? []).includes(punkty) : true;

/** Etykieta kafla jak w makiecie v2: „Znacznie poniżej”, „Na poziomie”. */
const etykietaKafla = (etykieta: string) => {
  const k = krotko(etykieta);
  return k.charAt(0).toUpperCase() + k.slice(1);
};

/** Jeden wskaźnik (układ makiety v2): zadania z OSP, przypomnienie z pytaniem, pięć równych kafli z opisem, przykład. */
function EkranWskaznika({
  kr,
  w,
  nr,
  pytania,
  zadania,
  tylkoOdczyt,
  czekam,
  blad,
  onZapisz,
}: {
  kr: KryteriumOceny;
  w: WskaznikOceny;
  nr: number;
  pytania: string[];
  zadania: { nr: number; tekst: string }[];
  tylkoOdczyt: boolean;
  czekam: boolean;
  blad?: string;
  onZapisz: (o: OcenaWskaznika) => void;
}) {
  const [uwagi, setUwagi] = useState(w.ocena?.uwagi ?? "");
  const przyklady = w.ocena?.przyklady ?? [];
  // Zablokowane tylko w odczycie: „disabled” na czas zapisu zrzucałby fokus klawiatury na początek strony.
  const zablokowane = tylkoOdczyt;
  const brak = w.ocena?.brak_podstaw ?? false;
  const zapisz = (o: OcenaWskaznika) => !czekam && onZapisz(o);
  const doZapisu = (o: Omit<OcenaWskaznika, "przyklady" | "uwagi">) => ({ ...o, przyklady, uwagi: uwagi.trim() || null });

  return (
    <div className="oc-ekran">
      <div className="oc-glowa">
        <p className="meta">
          {nazwaKryterium(kr.nazwa)} · wskaźnik {nr} z {kr.wskazniki.length}
        </p>
        <h2 className="oc-tytul" tabIndex={-1}>
          {w.nazwa.replace(/\.$/, "")}
        </h2>
        {zadania.length > 0 && (
          <p className="meta oc-zadania">Zadanie z OSP: {zadania.map((z) => `${z.nr}. ${z.tekst}`).join(" · ")}</p>
        )}
      </div>

      <div className="oc-pytanie">
        <Ikona nazwa="pytanie" rozmiar={20} />
        <div>
          <p className="oc-pytanie-tytul">Przypomnij sobie sytuację z okresu oceny</p>
          {pytania.slice(0, 1).map((p) => (
            <p key={p}>
              <span className="meta">Możesz zapytać: </span>
              {p}
            </p>
          ))}
        </div>
      </div>

      <div className="oc-obserwacja">
        <p className="etykieta">Obserwacja</p>
        <div className="oc-kafle" role="radiogroup" aria-label={`Poziom: ${w.nazwa}`}>
          {w.poziomy.map((p) => {
            const wybrany = !brak && w.ocena?.poziom === p.poziom;
            return (
              <button
                key={p.poziom}
                type="button"
                role="radio"
                aria-checked={wybrany}
                aria-label={`${p.etykieta}: ${p.opis}`}
                className="oc-kafel"
                disabled={zablokowane}
                onClick={() => zapisz(doZapisu({ poziom: p.poziom, brak_podstaw: false }))}
              >
                <span className="oc-kafel-etykieta">
                  {wybrany && <Ikona nazwa="ok" rozmiar={16} />}
                  {etykietaKafla(p.etykieta)}
                  {oczekiwany(p.etykieta) && <span className="znacznik">oczekiwany</span>}
                </span>
                <span className="oc-kafel-opis">{p.opis}</span>
              </button>
            );
          })}
        </div>
        <div className="oc-pod-kaflami">
          {brak ? <span className="meta">Ten wskaźnik nie wpłynie na sugestię punktów.</span> : <span />}
          <button
            type="button"
            className="link oc-brak"
            aria-pressed={brak}
            disabled={zablokowane}
            onClick={() => zapisz(doZapisu({ poziom: null, brak_podstaw: !brak }))}
          >
            {brak ? "Cofnij brak podstaw" : "Brak podstaw do oceny"}
          </button>
        </div>
      </div>

      <SamoocenaPrzyWskazniku w={w} />

      <label className="etykieta oc-uwagi">
        Przykład z okresu (opcjonalnie)
        <textarea
          rows={3}
          value={uwagi}
          disabled={tylkoOdczyt}
          placeholder="Sytuacja → działanie → rezultat"
          onChange={(e) => setUwagi(e.target.value)}
          onBlur={() => w.ocena && (w.ocena.uwagi ?? "") !== uwagi.trim() && onZapisz({ ...w.ocena, uwagi: uwagi.trim() || null })}
        />
      </label>
      {przyklady.map((p, i) => (
        <p key={i} className="meta">
          Przykład: {p.sytuacja} – {p.dzialanie} – {p.rezultat}
        </p>
      ))}
      {w.ostrzezenia.map((o) => (
        <p key={o} className="brak">
          {o}
        </p>
      ))}
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}

/** Ocena kryterium pod ostatnim wskaźnikiem: podstawa, sugestia, poprzednie punkty i wybór, zapis od kliknięcia. */
function OcenaKryterium({
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
  const d = kr.decyzja;
  const [uzasadnienie, setUzasadnienie] = useState(d?.uzasadnienie ?? "");
  const sugerowane = punktySugestii(s);
  const inna = d !== null && !zgodnaZSugestia(s, d.punkty);

  return (
    <div className="oc-kryterium">
      <h2 className="oc-tytul">Ocena kryterium: {nazwaKryterium(kr.nazwa)}</h2>
      <ul className="oc-podstawa">
        {kr.wskazniki.map((w) => (
          <li key={w.wskaznik_id}>
            <span>{w.nazwa}</span>
            <span className="oc-poziom">{stanWskaznika(w) || "nie oceniono"}</span>
          </li>
        ))}
      </ul>
      <p className="oc-sugestia">
        {sugerowane ? (
          <>
            <strong>Sugestia: {sugerowane}</strong> <span className="meta">{s.opis}</span>
          </>
        ) : (
          <span className="meta">Sugestia pojawi się, gdy ocenisz co najmniej połowę wskaźników.</span>
        )}
        <span className="kategoria zasada">Zasada aplikacji</span>
      </p>
      {poprzednio && (
        <p className="meta">
          Poprzednia ocena ({data(poprzednio.data)}): {poprzednio.punkty} pkt · dane demo
        </p>
      )}
      <p className="etykieta">Twoja ocena</p>
      <div className="oc-punkty" role="radiogroup" aria-label={`Ocena cząstkowa: ${kr.nazwa}`} style={{ "--kolumny": skala.punkty.length } as CSSProperties}>
        {skala.punkty.map((p) => {
          const wybrany = d?.punkty === p;
          const sugerowany = s.status === "POZIOM" ? s.punkty === p : s.status === "REMIS" && (s.punkty_remisu ?? []).includes(p);
          return (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={wybrany}
              className="oc-punkt"
              disabled={tylkoOdczyt}
              onClick={() => !czekam && !wybrany && onZapisz({ punkty: p, uzasadnienie: uzasadnienie.trim() || null })}
            >
              <span className="oc-punkt-liczba">
                {wybrany && <Ikona nazwa="ok" rozmiar={16} />}
                {p} pkt
              </span>
              <span className="oc-punkt-opis">{skala.etykiety[String(p)]}</span>
              {sugerowany && <span className="znacznik">sugestia</span>}
            </button>
          );
        })}
      </div>
      {inna && (
        <label className="etykieta oc-uwagi">
          Dlaczego inaczej niż sugestia? (opcjonalnie)
          <textarea
            rows={2}
            value={uzasadnienie}
            disabled={tylkoOdczyt}
            onChange={(e) => setUzasadnienie(e.target.value)}
            onBlur={() =>
              d && (d.uzasadnienie ?? "") !== uzasadnienie.trim() && onZapisz({ punkty: d.punkty, uzasadnienie: uzasadnienie.trim() || null })
            }
          />
        </label>
      )}
      {!d && !tylkoOdczyt && <p className="meta">Sugestia to tylko podpowiedź. Punkty wybierasz Ty.</p>}
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}

type Krok = { typ: "wskaznik"; kr: number; w: number } | { typ: "podsumowanie" };

const kroki = (dane: StanOceny): Krok[] => [
  ...dane.kryteria.flatMap((kr, i) => kr.wskazniki.map((_, j): Krok => ({ typ: "wskaznik", kr: i, w: j }))),
  { typ: "podsumowanie" },
];

function etykietaDalej(k: Krok | undefined, dane: StanOceny): string {
  if (!k) return "";
  if (k.typ === "podsumowanie") return "Dalej: podsumowanie";
  if (k.w === 0) return `Dalej: ${nazwaKryterium(dane.kryteria[k.kr].nazwa)}`;
  return `Dalej: wskaźnik ${k.w + 1} z ${dane.kryteria[k.kr].wskazniki.length}`;
}

/** Postęp jak w formularzach administracji: „Kryterium X z N”, cienki pasek z odcinkiem na każdy wskaźnik
 *  (pogrupowany po kryteriach), lista kryteriów do przejścia dopiero po „Plan oceny”. */
function Os({ dane, lista, biezacy, onIdz }: { dane: StanOceny; lista: Krok[]; biezacy: number; onIdz: (i: number) => void }) {
  const [plan, setPlan] = useState(false);
  const k = lista[biezacy];
  const wszystkie = dane.kryteria.reduce((n, kr) => n + kr.wskazniki.length, 0);
  const ocenione = dane.kryteria.reduce((n, kr) => n + kr.wskazniki.filter(oceniony).length, 0);
  const idz = (i: number) => {
    setPlan(false);
    onIdz(i);
  };
  return (
    <nav className="oc-os" aria-label="Plan oceny">
      <div className="oc-os-glowa">
        <p className="oc-os-krok">
          {k.typ === "podsumowanie" ? "Podsumowanie" : `Kryterium ${k.kr + 1} z ${dane.kryteria.length}`}
          <span className="meta"> · ocenione wskaźniki {ocenione} z {wszystkie}</span>
        </p>
        <button type="button" className="link" aria-expanded={plan} onClick={() => setPlan((v) => !v)}>
          {plan ? "Zwiń plan" : "Plan oceny"}
        </button>
      </div>
      <div className="oc-os-pasek" role="progressbar" aria-label="Ocenione wskaźniki" aria-valuemin={0} aria-valuemax={wszystkie} aria-valuenow={ocenione}>
        {dane.kryteria.map((kr, i) => (
          <span key={kr.kompetencja_id} className="oc-os-grupa" style={{ flexGrow: kr.wskazniki.length }}>
            {kr.wskazniki.map((w, j) => (
              <span
                key={w.wskaznik_id}
                className={`oc-os-odcinek ${oceniony(w) ? "pelny" : ""} ${k.typ === "wskaznik" && k.kr === i && k.w === j ? "biezacy" : ""}`}
              />
            ))}
          </span>
        ))}
      </div>
      <Zwijane otwarte={plan}>
        <ol className="oc-os-lista">
          {dane.kryteria.map((kr, i) => {
            const tu = k.typ === "wskaznik" && k.kr === i;
            return (
              <li key={kr.kompetencja_id}>
                <button
                  type="button"
                  aria-current={tu ? "step" : undefined}
                  onClick={() => idz(lista.findIndex((x) => x.typ === "wskaznik" && x.kr === i))}
                >
                  <span className={`oc-os-nr ${kr.decyzja ? "gotowe" : ""}`} aria-hidden="true">
                    {kr.decyzja ? <Ikona nazwa="ok" rozmiar={14} /> : i + 1}
                  </span>
                  <span className="oc-os-nazwa">{nazwaKryterium(kr.nazwa)}</span>
                  <span className="meta">
                    {kr.decyzja ? `${kr.decyzja.punkty} pkt` : `${kr.wskazniki.filter(oceniony).length} z ${kr.wskazniki.length}`}
                  </span>
                </button>
              </li>
            );
          })}
          <li>
            <button type="button" aria-current={k.typ === "podsumowanie" ? "step" : undefined} onClick={() => idz(lista.length - 1)}>
              <span className="oc-os-nr" aria-hidden="true">
                {dane.kryteria.length + 1}
              </span>
              <span className="oc-os-nazwa">Podsumowanie</span>
              <span className="meta">
                {dane.kompletnosc.kryteria_z_decyzja} z {dane.kompletnosc.kryteria}
              </span>
            </button>
          </li>
        </ol>
      </Zwijane>
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
  const [zadania, setZadania] = useState<Record<string, { nr: number; tekst: string }[]>>({});
  const [krok, setKrok] = useState(0);
  const [metodyka, setMetodyka] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const [bledy, setBledy] = useState<Record<string, string>>({});
  const [czekam, setCzekam] = useState<string | null>(null);
  const poprzednie = usePoprzedniaOcena(token, osoba.osoba_id);

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
    // Powiązanie wskaźnik ↔ zadania z OSP (krok 2, dobór zespołu zatwierdzany przez przełożonego).
    pobierzKrok2(token, proces.id)
      .then((k2) =>
        setZadania(Object.fromEntries(k2.kryteria.flatMap((k) => k.wskazniki.map((w) => [w.wskaznik_id, w.zadania.map((z) => ({ nr: z.nr, tekst: z.tekst }))])))),
      )
      .catch(() => setZadania({}));
  }, [token, proces.id, moznaProwadzic]);

  // Po „Dalej” fokus na tytule nowego ekranu (czytnik ekranu i klawiatura zaczynają od góry).
  useEffect(() => {
    window.scrollTo(0, 0);
    document.querySelector<HTMLElement>(".oc-ekran .oc-tytul")?.focus({ preventScroll: true });
  }, [krok]);

  if (!dane) {
    return <section>{blad ? <p className="blad">{blad}</p> : <p className="meta">Wczytuję ocenę…</p>}</section>;
  }

  const tylkoOdczyt = !moznaProwadzic;
  const lista = kroki(dane);
  const biezacy = Math.min(krok, lista.length - 1);
  const k = lista[biezacy];
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

  const ostatniWskaznik = (i: number) => lista.findIndex((x) => x.typ === "wskaznik" && x.kr === i && x.w === dane.kryteria[i].wskazniki.length - 1);

  let ekran;
  if (k.typ === "wskaznik") {
    const kr = dane.kryteria[k.kr];
    const w = kr.wskazniki[k.w];
    const p = poprzednie?.punkty[kr.kompetencja_id];
    ekran = (
      <>
        <EkranWskaznika
          key={w.wskaznik_id}
          kr={kr}
          w={w}
          nr={k.w + 1}
          pytania={pytania[w.wskaznik_id] ?? []}
          zadania={zadania[w.wskaznik_id] ?? []}
          tylkoOdczyt={tylkoOdczyt}
          czekam={czekam === w.wskaznik_id}
          blad={bledy[w.wskaznik_id]}
          onZapisz={(o) => zapiszWskaznik(w.wskaznik_id, o)}
        />
        {k.w === kr.wskazniki.length - 1 && (
          <OcenaKryterium
            key={kr.kompetencja_id}
            kr={kr}
            skala={dane.skala}
            poprzednio={p !== undefined && poprzednie ? { punkty: p, data: poprzednie.data } : null}
            tylkoOdczyt={tylkoOdczyt}
            czekam={czekam === kr.kompetencja_id}
            blad={bledy[kr.kompetencja_id]}
            onZapisz={(d) => zapiszDecyzje1(kr.kompetencja_id, d)}
          />
        )}
      </>
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
            {dane.kryteria.map((kr, i) => (
              <tr key={kr.kompetencja_id}>
                <td>{nazwaKryterium(kr.nazwa)}</td>
                <td>{punktySugestii(kr.sugestia) ?? "za mało danych"}</td>
                <td>{kr.decyzja ? `${kr.decyzja.punkty} pkt` : "—"}</td>
                <td>
                  <button type="button" className="link" onClick={() => setKrok(ostatniWskaznik(i))}>
                    {kr.decyzja ? "Zmień" : "Oceń"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="meta">
          {kp.kryteria_z_decyzja === kp.kryteria
            ? "Wszystkie kryteria są ocenione. Średnią i wynik zobaczysz w kroku 7."
            : `Ocenione kryteria: ${kp.kryteria_z_decyzja} z ${kp.kryteria}. Do każdego możesz wrócić także po rozmowie.`}
        </p>
      </div>
    );
  }

  const nastepny = lista[biezacy + 1];

  return (
    <div className="k2 oc">
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
      <Os dane={dane} lista={lista} biezacy={biezacy} onIdz={setKrok} />
      {(dane.samoocena_status === "przekazana" || k.typ === "podsumowanie") && (
        <StatusSamoocenyPrzelozonego status={dane.samoocena_status} />
      )}
      {dane.samoocena_status === "przekazana" && <LegendaPorownania />}

      <div className="oc-kolumna">
        {ekran}
        <div className="oc-nawigacja">
          {biezacy > 0 ? (
            <button type="button" className="link" onClick={() => setKrok(biezacy - 1)}>
              Wstecz
            </button>
          ) : (
            <span />
          )}
          {k.typ === "wskaznik" && (
            <span className="meta oc-licznik">
              {biezacy + 1} z {lista.length - 1}
            </span>
          )}
          {nastepny ? (
            <button type="button" onClick={() => setKrok(biezacy + 1)}>
              {etykietaDalej(nastepny, dane)}
            </button>
          ) : (
            <button type="button" onClick={onDalej}>
              Dalej: rozmowa oceniająca
            </button>
          )}
        </div>
        <div className="k2-metodyka">
          <button type="button" className="link" aria-expanded={metodyka} onClick={() => setMetodyka((v) => !v)}>
            {metodyka ? "Ukryj zasady" : "Jak oceniać i skąd sugestia?"}
          </button>
          <Zwijane otwarte={metodyka}>
            <div className="k1-szczegoly">
              {dane.instrukcja.map((i) => (
                <div key={i.tekst}>
                  <p className="meta">{i.tekst}</p>
                  <Zrodla adnotacje={[i.adnotacja]} />
                </div>
              ))}
              <p className="meta">{dane.metodyka.opis}</p>
              <Zrodla adnotacje={dane.metodyka.adnotacje} />
            </div>
          </Zwijane>
        </div>
      </div>
    </div>
  );
}
