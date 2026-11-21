import { createContext, useContext, useId, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { Ikona } from "./Ikona";
import { SzkieletListy, WierszListy } from "./Lista";
import { Zwijane } from "./Zwijane";
export { Arkusz as Wynik } from "./Arkusz";
import "./krok7.css";
import {
  BladApi,
  pobierzOcene,
  type SourceRef,
  type DaneWyniku,
  type Pracownik,
  type ProcesOceny,
  type SladReguly,
  type Termin,
  type WynikOkresowy,
  type ZmianaTerminu,
} from "./api";
import { Zrodla, nazwaKryterium, opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";

export const data = (iso: string) => iso.split("-").reverse().join(".");

const liczba = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const srednia = (v: string | number) => liczba.format(Number(String(v).replace(",", ".")));

function opisObliczenia(opis: string) {
  return opis.replace(/(średnia z \d+ ocen to \d+\/\d+ = |średnia |ocena łączna )(\d+(?:[.,]\d+)?)(?:\/(\d+))?/gi,
    (_, przed: string, n: string, mianownik?: string) =>
      przed + (mianownik ? liczba.format(Number(n) / Number(mianownik)) : srednia(n)));
}

export function dzienZapisu(czas: Date) {
  return czas.toLocaleDateString("sv-SE", { timeZone: "Europe/Warsaw" });
}

export async function dataRozmowy(token: string, procesId: number) {
  const stan = await pobierzOcene(token, procesId);
  const czasy = stan.kryteria.flatMap((k) => k.decyzja ? [Date.parse(k.decyzja.zapisano)] : []).filter(Number.isFinite);
  return dzienZapisu(czasy.length ? new Date(Math.max(...czasy)) : new Date());
}

export function notatkaRozwoju(procesId: number): string | null {
  try {
    const notatka = sessionStorage.getItem(`kompas-notatka-${procesId}-rozwoj`);
    if (notatka?.trim()) return notatka;
    const szkic = JSON.parse(sessionStorage.getItem(`kompas-szkic-${procesId}`) ?? "null");
    return typeof szkic?.rozwoj === "string" && szkic.rozwoj.trim() ? szkic.rozwoj : null;
  } catch {
    return null;
  }
}

const TERMINY: { klucz: keyof WynikOkresowy["terminy"]; nazwa: string }[] = [
  { klucz: "termin_kryteriow", nazwa: "Ustalenie kryteriów" },
  { klucz: "termin_bazowy", nazwa: "Termin bazowy oceny" },
  { klucz: "termin_sporzadzenia_oceny", nazwa: "Sporządzenie oceny" },
  { klucz: "termin_sprzeciwu", nazwa: "Sprzeciw ocenianego" },
  { klucz: "ponowne_kryteria", nazwa: "Ponowne ustalenie kryteriów" },
  { klucz: "okno_zmiany_stanowiska", nazwa: "Okno po zmianie stanowiska" },
];

const PRZYCZYNY: Record<ZmianaTerminu["przyczyna"], string> = {
  zmiana_oceniajacego: "zmiana oceniającego",
  przewidywana_nieobecnosc_ocenianego: "nieobecność ocenianego",
  przewidywana_nieobecnosc_oceniajacego: "nieobecność oceniającego",
  wniosek_ocenianego: "wniosek ocenianego",
};

/** Data RRRR-MM-DD, która istnieje w kalendarzu (2026-13-01 i 2026-02-30 odpada). */
export function poprawnaData(v: string | null | undefined): boolean {
  if (!v) return true;
  const d = new Date(`${v}T00:00:00Z`);
  return /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}

export function PoleDaty({
  nazwa,
  wartosc,
  onZmiana,
  id,
}: {
  id?: string;
  nazwa: string;
  wartosc: string | null;
  onZmiana: (v: string | null) => void;
}) {
  const brak = useContext(Rozwiniecia).braki.find((b) => b.cel === id);
  return (
    <label className="etykieta">
      {nazwa}
      <input
        id={id}
        inputMode="numeric"
        placeholder="RRRR-MM-DD"
        value={wartosc ?? ""}
        aria-invalid={!!brak || !poprawnaData(wartosc)}
        onChange={(e) => onZmiana(e.target.value.trim() || null)}
      />
      {brak && <span className="blad">{brak.opis ?? "Uzupełnij datę."}</span>}
    </label>
  );
}

/** Zapisuje pobrany plik na dysku (PDF wymaga tokenu, więc nie może być zwykłym linkiem). */
export function zapiszPlik(plik: Blob, nazwa: string) {
  const url = URL.createObjectURL(plik);
  const a = document.createElement("a");
  a.href = url;
  a.download = nazwa;
  a.click();
  URL.revokeObjectURL(url);
}

export function bladWyniku(err: unknown): string {
  const d = err instanceof BladApi ? (err.detail as { komunikat?: string } | null) : null;
  if (d?.komunikat) return d.komunikat;
  if (err instanceof BladApi) {
    if (err.status === 409) return "Najpierw zapisz oceny cząstkowe wszystkich kryteriów (rozmowa oceniająca).";
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) return "Nie masz uprawnień do tej oceny.";
    if (err.status !== 422) return "Nie udało się wczytać lub zapisać danych oceny.";
  }
  return opisBledu(err);
}

export function Slad({ slad }: { slad: SladReguly[] }) {
  return (
    <ol className="slad">
      {slad.map((s) => (
        <li key={s.regula.id + s.opis}>
          {opisObliczenia(s.opis)}
          <Zrodla adnotacje={[s.regula.zrodlo]} />
        </li>
      ))}
    </ol>
  );
}

export interface Krok7Props {
  token: string;
  osoba: Pracownik;
  proces: ProcesOceny;
  moznaProwadzic: boolean;
  onWstecz: () => void;
  onDalej: () => void;
  onZmienOcene?: () => void;
  zalogowanyId?: string | null;
}

export function Naglowek({
  osoba,
  tytul,
  opis,
  wstecz,
  onWstecz,
}: {
  osoba: Pracownik;
  tytul: string;
  opis: string;
  wstecz: string;
  onWstecz: () => void;
}) {
  return (
    <header className="k2-naglowek">
      <button className="link" type="button" onClick={onWstecz}>
        <Ikona nazwa="wstecz" />
        {wstecz}
      </button>
      <p className="meta">Część 3 z 3 · Ocena na piśmie</p>
      <h1>{tytul}</h1>
      <p className="opis">
        {osoba.imie} {osoba.nazwisko} · {opis}
      </p>
    </header>
  );
}

export function Wczytywanie({ blad }: { blad: string | null }) {
  return blad ? (
    <p className="blad" role="alert">
      {blad}
    </p>
  ) : (
    <SzkieletListy />
  );
}

export interface Brak {
  tekst: string;
  cel: string;
  grupa?: string;
  opis?: string;
  tylkoTermin?: boolean;
}



export function BladPola({ cel }: { cel: string }) {
  const brak = useContext(Rozwiniecia).braki.find((b) => b.cel === cel);
  return brak ? <span className="blad">{brak.opis ?? "Uzupełnij pole."}</span> : null;
}

const Rozwiniecia = createContext({ braki: [] as Brak[], otwarte: new Set<string>(), przelacz: (_id: string) => {} });

export function Sekcja({ id, tytul, children }: { id: string; tytul: string; children: ReactNode }) {
  const { otwarte, przelacz } = useContext(Rozwiniecia);
  const rozwinieta = otwarte.has(id);
  const panel = useId();
  return (
    <section className="sekcja k7-sekcja">
      <h2>
        <button
          className="k7-rozwin"
          type="button"
          id={id}
          aria-expanded={rozwinieta}
          aria-controls={panel}
          onClick={() => przelacz(id)}
        >
          {tytul}
          <Ikona nazwa="dalej" />
        </button>
      </h2>
      <div id={panel}>
        <Zwijane otwarte={rozwinieta}>{children}</Zwijane>
      </div>
    </section>
  );
}

function grupyBraku(b: Brak) {
  return b.grupa?.includes("/") ? [b.grupa.split("/")[0], b.grupa] : b.grupa ? [b.grupa] : [];
}

export function Podsumowanie({
  braki: wszystkieBraki,
  dzieci,
  bok,
  akcje,
  glowna,
  onWstecz,
  blad,
  podpis,
}: {
  braki: Brak[];
  dzieci: ReactNode;
  bok: ReactNode;
  akcje: ReactNode;
  glowna: ReactNode;
  onWstecz: () => void;
  blad: string | null;
  podpis: string;
}) {
  const cele = new Set<string>();
  const braki = wszystkieBraki.filter((b) => {
    const klucz = b.cel === "pola" || b.cel === "terminy" ? b.tekst : b.cel;
    if (cele.has(klucz)) return false;
    cele.add(klucz);
    return true;
  });
  const [otwarte, setOtwarte] = useState(() => new Set(braki.flatMap(grupyBraku).filter((id) => id !== "wyjatki" && id !== "daty")));
  const [wszystkie, setWszystkie] = useState(false);
  const pierwszy = braki[0];
  const przelacz = (id: string) =>
    setOtwarte((stare) => {
      const nowe = new Set(stare);
      if (nowe.has(id)) nowe.delete(id);
      else nowe.add(id);
      return nowe;
    });
  function pokaz(b: Brak) {
    flushSync(() => setOtwarte((stare) => new Set([...stare, ...grupyBraku(b)])));
    const cel = document.getElementById(b.cel);
    const pole = cel?.querySelector<HTMLElement>("input:enabled, textarea:enabled, button:enabled");
    (pole ?? cel)?.focus({ preventScroll: true });
    (pole ?? cel)?.scrollIntoView({ block: "center" });
  }
  const wiersz = (b: Brak, i: number) => (
    <WierszListy
      key={b.cel + i}
      maly
      tytul={b.tekst}
      onClick={() => pokaz(b)}
    />
  );
  return (
    <Rozwiniecia.Provider value={{ otwarte, przelacz, braki }}>
      {braki.length > 0 && (
        <section className="sekcja k7-braki">
          <h2>Co jeszcze trzeba</h2>
          <div className="lista">{braki.slice(0, 3).map(wiersz)}</div>
          {braki.length > 3 && (
            <>
              <button type="button" className="link" aria-expanded={wszystkie} onClick={() => setWszystkie(!wszystkie)}>
                {wszystkie ? "Zwiń listę" : `Pokaż pozostałe (${braki.length - 3})`}
              </button>
              <Zwijane otwarte={wszystkie}>
                <div className="lista">{braki.slice(3).map(wiersz)}</div>
              </Zwijane>
            </>
          )}
        </section>
      )}
      <div className="dwie">
        <aside className="sekcja k7-boczna">{bok}</aside>
        <div className="sekcja k7-tresc">
          {dzieci}
          <div className="k7-akcje">{akcje}</div>
        </div>
      </div>
      <div className="oc-nawigacja k7-pasek">
        <button type="button" className="link" onClick={onWstecz}>
          <Ikona nazwa="wstecz" />
          Wróć do rozmowy
        </button>
        <div className="k7-komunikat">
          {blad && (
            <span className="blad" role="alert">
              {blad}
            </span>
          )}
          <span role="status">
            {pierwszy && `Brakuje: ${braki.length} · ${pierwszy.tekst}`}
          </span>
          <span className="meta">{podpis} Podpisy złóż odręcznie na wydruku.</span>
        </div>
        {glowna}
      </div>
    </Rozwiniecia.Provider>
  );
}

export function Werdykt({
  wynik,
  warunki,
  onZmienOcene,
}: {
  wynik: WynikOkresowy["obliczenie"] | null;
  warunki: { opis: string; spelniony: boolean; zrodlo: SourceRef; szczegoly?: string; slad?: string }[];
  onZmienOcene?: () => void;
}) {
  return (
    <>
      <div className={`k7-werdykt ${wynik?.wynik ?? ""}`} role="status">
        <h2>{wynik ? `Ocena ${wynik.wynik}` : "Wynik jeszcze nieustalony"}</h2>
        {wynik && (
          <p>
            Średnia {srednia(wynik.srednia)}{" "}
            pkt{wynik.poziom && ` · ${wynik.poziom}`}
          </p>
        )}
      </div>
      {warunki.length > 0 && (
        <div className="sekcja">
          <h2>Warunki</h2>
          <ul className="oc-podstawa k7-warunki">
            {warunki.map((w) => (
              <li key={w.opis}>
                <span
                  className={w.spelniony ? "k7-tak" : "k7-nie"}
                  role="img"
                  aria-label={w.spelniony ? "Spełniony" : "Niespełniony"}
                >
                  <Ikona nazwa={w.spelniony ? "ok" : "krzyz"} />
                </span>
                <div>
                  {opisObliczenia(w.opis)}
                  {w.szczegoly && <p>{w.szczegoly}</p>}
                  {w.slad && <details><summary>Ślad obliczenia</summary>{opisObliczenia(w.slad)}</details>}
                  <Zrodla adnotacje={[w.zrodlo]} />
                  {!w.spelniony && onZmienOcene && (
                    <button type="button" className="link" onClick={onZmienOcene}>Zmień ocenę</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

export function TabelaTerminow({
  terminy,
  slad,
  children,
}: {
  terminy: [string, Termin][];
  slad: SladReguly[];
  children?: ReactNode;
}) {
  return (
    <Sekcja id="terminy" tytul="Terminy">
      {terminy.length > 0 && (
        <table className="k7-terminy">
          <thead>
            <tr>
              <th>Termin i podstawa</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {terminy.map(([nazwa, t]) => (
              <tr key={nazwa}>
                <td>
                  <details>
                    <summary>{nazwa}</summary>
                    <Slad slad={t.slad} />
                  </details>
                </td>
                <td>{data(t.data)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {children}
      {slad.length > 0 && (
        <details>
          <summary>Jak ustalono terminy</summary>
          <Slad slad={slad} />
        </details>
      )}
    </Sekcja>
  );
}

export const DATY_OKRESOWE = [
  ["data_ustalenia_kryteriow", "Ustalenie kryteriów"],
  ["data_zapoznania_z_kryteriami", "Zapoznanie ocenianego z kryteriami"],
  ["data_sporzadzenia_oceny", "Sporządzenie oceny"],
  ["data_zapoznania_z_ocena", "Zapoznanie ocenianego z oceną"],
] as const;

interface FormularzOkresowej {
  wynik: WynikOkresowy;
  f: DaneWyniku;
  ustaw: (zmiana: Partial<DaneWyniku>) => void;
  blokada: boolean;
}

export function BokOkresowej({ wynik, f, ustaw, blokada, onZmienOcene, children }: FormularzOkresowej & {
  children: ReactNode;
  onZmienOcene?: () => void;
}) {
  const o = wynik.obliczenie;
  const minimum = Math.min(...wynik.oceny_czastkowe.map((k) => k.punkty));
  const wypiszPunkty = (oceny: WynikOkresowy["oceny_czastkowe"]) => oceny.map((k) => `${nazwaKryterium(k.nazwa)}: ${k.punkty} pkt`).join(", ");
  const warunki = o.slad.flatMap(({ regula, opis }) => {
    const spelniony = regula.id !== o.regula_rozstrzygajaca.id || o.wynik === "pozytywna";
    if (regula.id === "negatywna-za-ocene-czastkowa") {
      return [{
        opis: spelniony ? "Żadne kryterium nie otrzymało najniższej oceny." : "Co najmniej jedno kryterium otrzymało najniższą ocenę.",
        spelniony, zrodlo: regula.zrodlo,
        szczegoly: spelniony ? undefined : wypiszPunkty(wynik.oceny_czastkowe.filter((k) => k.punkty === minimum)),
        slad: opis,
      }];
    }
    if (regula.id !== "negatywna-za-poziom" && regula.id !== "pozytywna") return [];
    return [{
      opis: regula.id === "pozytywna" ? "Warunki pozytywnej oceny są spełnione." : `Ogólny poziom: ${o.poziom}.`,
      spelniony, zrodlo: regula.zrodlo, szczegoly: spelniony ? undefined : wypiszPunkty(wynik.oceny_czastkowe), slad: opis,
    }];
  });
  return (
    <>
      <Werdykt wynik={o} warunki={warunki} onZmienOcene={onZmienOcene} />
      <label className="etykieta">
        Uzasadnienie {wynik.uzasadnienie_wymagane ? "(wymagane)" : "(opcjonalnie)"}
        <textarea
          id="uzasadnienie"
          rows={3}
          disabled={blokada}
          required={wynik.uzasadnienie_wymagane}
          value={f.uzasadnienie ?? ""}
          onChange={(e) => ustaw({ uzasadnienie: e.target.value })}
        />
      </label>
      <BladPola cel="uzasadnienie" />
      {wynik.podstawa_uzasadnienia && <Zrodla adnotacje={[wynik.podstawa_uzasadnienia]} />}
      {children}
      {wynik.czesc_iii.dostepna ? (
        <div>
          <label className="zaznacz">
            <input
              type="checkbox"
              disabled={blokada}
              checked={f.dolacz_wniosek_o_stopien}
              onChange={(e) => ustaw({ dolacz_wniosek_o_stopien: e.target.checked })}
            />
            Wnioskuję o kolejny stopień służbowy (część III)
          </label>
          <Zrodla adnotacje={[wynik.czesc_iii.adnotacja]} />
          {f.dolacz_wniosek_o_stopien && !wynik.czesc_iii.dolaczana &&
            <p className="meta">Zapisz szkic, aby uzupełnić pola wniosku w części III arkusza.</p>}
        </div>
      ) : (
        <p>{o.wynik === "negatywna" ? "Przy ocenie negatywnej nie dołącza się części III." :
          "Część III dotyczy wyłącznie urzędników służby cywilnej."}</p>
      )}
      <section className="sekcja">
        <h2>Zapoznanie z oceną</h2>
        <p>Niezwłocznie zapoznaj ocenianego z oceną (§ 12).</p>
        <p>Oceniany może wnieść sprzeciw do dyrektora generalnego urzędu w ciągu 7 dni od zapoznania się z oceną.
          Sprzeciw rozpatruje się w ciągu 14 dni od jego wniesienia.</p>
        {wynik.terminy.termin_sprzeciwu?.slad.filter((s) => s.regula.id === "okresowa.termin.sprzeciw-7")
          .map((s) => <Zrodla key={s.regula.id} adnotacje={[s.regula.zrodlo]} />)}
        <small>Poradnik KPRM dotyczący ocen okresowych, s. 32–33.</small>
      </section>
    </>
  );
}

export function DaneOkresowej({ wynik, f, ustaw, blokada, children }: FormularzOkresowej & { children: ReactNode }) {
  const stanowisko = f.zmiana_stanowiska;
  const z = f.zmiana_terminu;
  const ustawZmiane = (zmiana: Partial<ZmianaTerminu>) => z && ustaw({ zmiana_terminu: { ...z, ...zmiana } });
  const terminy: [string, Termin][] = [];
  for (const { klucz, nazwa } of TERMINY) {
    const t = wynik.terminy[klucz];
    if (t && typeof t === "object" && "data" in t) terminy.push([nazwa, t]);
    // API zwraca dwie granice okna po zmianie stanowiska.
    else if (t && typeof t === "object" && "od" in t && "do" in t) {
      const okno = t as { od: Termin; do: Termin };
      terminy.push([`${nazwa} od`, okno.od], [`${nazwa} do`, okno.do]);
    }
  }
  return (
    <>
      <TabelaTerminow terminy={terminy} slad={wynik.terminy.slad}>
        {wynik.poprzednia_ocena && (
          <p>
            Poprzednia ocena: {data(wynik.poprzednia_ocena.data)}, {wynik.poprzednia_ocena.wynik}{" "}
            {wynik.poprzednia_ocena.poziom}
          </p>
        )}
        {wynik.terminy.zachowaj_kryteria && <p>Kryteria z poprzedniej oceny zostają.</p>}
      </TabelaTerminow>
      <Sekcja id="daty" tytul="Daty (z wcześniejszych kroków)">
        <fieldset className="formularz" disabled={blokada}>
          <div className="siatka-dat">
            {DATY_OKRESOWE.map(([k, nazwa]) => (
              <PoleDaty key={k} id={k} nazwa={nazwa} wartosc={f[k]} onZmiana={(v) => ustaw({ [k]: v })} />
            ))}
          </div>
        </fieldset>
        {children}
      </Sekcja>
      <Sekcja id="wyjatki" tytul="Pozostałe daty i wyjątki">
        <fieldset className="formularz" disabled={blokada}>
          <div className="siatka-dat">
            {(wynik.terminy.braki.some((b) => b.includes("poprzednią oceną negatywną")) ||
              f.data_zapoznania_z_poprzednia_ocena) && (
              <PoleDaty
                id="data_zapoznania_z_poprzednia_ocena"
                nazwa="Zapoznanie z poprzednią oceną negatywną"
                wartosc={f.data_zapoznania_z_poprzednia_ocena}
                onZmiana={(v) => ustaw({ data_zapoznania_z_poprzednia_ocena: v })}
              />
            )}
          </div>
          {wynik.poprzednia_ocena && !wynik.poprzednia_ocena.poziom && (
            <label className="etykieta">
              Poziom poprzedniej oceny
              <input
                id="poprzednia_ocena_poziom"
                value={f.poprzednia_ocena_poziom ?? ""}
                onChange={(e) => ustaw({ poprzednia_ocena_poziom: e.target.value || null })}
              />
              <BladPola cel="poprzednia_ocena_poziom" />
            </label>
          )}
          <label className="zaznacz">
            <input type="checkbox" checked={!!stanowisko} onChange={(e) => ustaw({
              zmiana_stanowiska: e.target.checked ? { data: "", istotna_zmiana_obowiazkow: false } : null,
            })} />
            Zmiana stanowiska (§ 9 ust. 1–2)
          </label>
          {stanowisko && (
            <>
              <PoleDaty id="data_zmiany_stanowiska" nazwa="Data zmiany stanowiska" wartosc={stanowisko.data}
                onZmiana={(v) => ustaw({ zmiana_stanowiska: { ...stanowisko, data: v ?? "" } })} />
              <label className="zaznacz">
                <input type="checkbox" checked={stanowisko.istotna_zmiana_obowiazkow}
                  onChange={(e) => ustaw({ zmiana_stanowiska: { ...stanowisko, istotna_zmiana_obowiazkow: e.target.checked } })} />
                Istotna zmiana obowiązków
              </label>
            </>
          )}
          <label className="zaznacz">
            <input
              type="checkbox"
              checked={!!z}
              onChange={(e) =>
                ustaw({
                  zmiana_terminu: e.target.checked
                    ? { nowy_termin: "", data_zawiadomienia: "", przyczyna: "wniosek_ocenianego" }
                    : null,
                })
              }
            />
            Zmień termin sporządzenia oceny (§ 8)
          </label>
          {z && (
            <div className="sekcja">
              <div className="siatka-dat">
                <PoleDaty
                  id="nowy_termin"
                  nazwa="Nowy termin"
                  wartosc={z.nowy_termin}
                  onZmiana={(v) => ustawZmiane({ nowy_termin: v ?? "" })}
                />
                <PoleDaty
                  id="data_zawiadomienia"
                  nazwa="Data zawiadomienia"
                  wartosc={z.data_zawiadomienia}
                  onZmiana={(v) => ustawZmiane({ data_zawiadomienia: v ?? "" })}
                />
              </div>
              <span className="etykieta">Przyczyna zmiany</span>
              <Wybor
                etykieta="Przyczyna zmiany terminu"
                opcje={Object.entries(PRZYCZYNY).map(([w, t]) => ({ wartosc: w as ZmianaTerminu["przyczyna"], tekst: t }))}
                wartosc={z.przyczyna}
                zablokowane={blokada}
                onWybierz={(w) => w && ustawZmiane({ przyczyna: w })}
              />
            </div>
          )}
        </fieldset>
      </Sekcja>
      <Sekcja id="kryteria" tytul="Oceny cząstkowe">
        <div className="lista">
          {wynik.oceny_czastkowe.map((k) => (
            <WierszListy
              key={k.kompetencja_id}
              maly
              tytul={nazwaKryterium(k.nazwa)}
              opis={k.rodzaj === "OBOWIAZKOWE" ? "obowiązkowe" : "dodatkowe"}
              prawa={`${k.punkty} pkt`}
            />
          ))}
        </div>
        <details>
          <summary>Jak policzono wynik</summary>
          <Slad slad={wynik.obliczenie.slad} />
          <Zrodla adnotacje={[wynik.obliczenie.regula_rozstrzygajaca.zrodlo]} />
        </details>
      </Sekcja>
    </>
  );
}
