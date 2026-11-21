import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzWynik,
  pobierzZawiadomienie,
  zapiszWynik,
  type DaneWyniku,
  type Pracownik,
  type ProcesOceny,
  type SladReguly,
  type Termin,
  type WynikOkresowy,
  type ZmianaTerminu,
} from "./api";
import { Zrodla, opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";

const data = (iso: string) => iso.split("-").reverse().join(".");

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

export function PoleDaty({ nazwa, wartosc, onZmiana }: { nazwa: string; wartosc: string | null; onZmiana: (v: string | null) => void }) {
  return (
    <label className="etykieta">
      {nazwa}
      <input
        inputMode="numeric"
        placeholder="RRRR-MM-DD"
        value={wartosc ?? ""}
        aria-invalid={!poprawnaData(wartosc)}
        onChange={(e) => onZmiana(e.target.value.trim() || null)}
      />
    </label>
  );
}

function DaneOceny({
  wynik,
  token,
  tylkoOdczyt,
  onZapisano,
}: {
  wynik: WynikOkresowy;
  token: string;
  tylkoOdczyt: boolean;
  onZapisano: (w: WynikOkresowy) => void;
}) {
  const [f, setF] = useState<DaneWyniku>(wynik.dane);
  const [czekam, setCzekam] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const z = f.zmiana_terminu;
  const daty = [
    f.data_ustalenia_kryteriow,
    f.data_zapoznania_z_kryteriami,
    f.data_sporzadzenia_oceny,
    f.data_zapoznania_z_ocena,
    z?.nowy_termin,
    z?.data_zawiadomienia,
  ];
  const zlaData = daty.some((d) => !poprawnaData(d));
  const brakUzasadnienia = wynik.uzasadnienie_wymagane && !f.uzasadnienie?.trim();
  const niepelnaZmiana = z !== null && (!z.nowy_termin || !z.data_zawiadomienia);
  const ustaw = (zmiana: Partial<DaneWyniku>) => setF((p) => ({ ...p, ...zmiana }));
  const ustawZmiane = (zmiana: Partial<ZmianaTerminu>) => ustaw({ zmiana_terminu: { ...(z as ZmianaTerminu), ...zmiana } });

  async function zapisz() {
    setCzekam(true);
    setBlad(null);
    try {
      // Część III tylko przy ocenie pozytywnej: wybór sprzed zmiany wyniku nie idzie dalej.
      const dolacz = wynik.czesc_iii.dostepna && f.dolacz_wniosek_o_stopien;
      onZapisano(await zapiszWynik(token, wynik.proces_id, { ...f, dolacz_wniosek_o_stopien: dolacz }));
    } catch (err) {
      setBlad(bladWyniku(err));
    } finally {
      setCzekam(false);
    }
  }

  async function pobierzPdf() {
    setBlad(null);
    try {
      zapiszPlik(await pobierzZawiadomienie(token, wynik.proces_id), `zawiadomienie-zmiana-terminu-${wynik.proces_id}.pdf`);
    } catch (err) {
      setBlad(bladWyniku(err));
    }
  }

  return (
    <section>
      <h2>Daty, uzasadnienie i zawiadomienie</h2>
      <fieldset className="formularz" disabled={tylkoOdczyt || czekam}>
        <div className="siatka-dat">
          <PoleDaty nazwa="Ustalenie kryteriów" wartosc={f.data_ustalenia_kryteriow} onZmiana={(v) => ustaw({ data_ustalenia_kryteriow: v })} />
          <PoleDaty nazwa="Zapoznanie ocenianego z kryteriami" wartosc={f.data_zapoznania_z_kryteriami} onZmiana={(v) => ustaw({ data_zapoznania_z_kryteriami: v })} />
          <PoleDaty nazwa="Sporządzenie oceny" wartosc={f.data_sporzadzenia_oceny} onZmiana={(v) => ustaw({ data_sporzadzenia_oceny: v })} />
          <PoleDaty nazwa="Zapoznanie ocenianego z oceną" wartosc={f.data_zapoznania_z_ocena} onZmiana={(v) => ustaw({ data_zapoznania_z_ocena: v })} />
        </div>
        {zlaData && <p className="blad">Podaj datę w formacie RRRR-MM-DD, np. 2026-11-21.</p>}

        <label className="etykieta">
          Uzasadnienie oceny{wynik.uzasadnienie_wymagane ? " (wymagane przy ocenie negatywnej)" : " (opcjonalnie)"}
          <textarea rows={3} value={f.uzasadnienie ?? ""} onChange={(e) => ustaw({ uzasadnienie: e.target.value })} />
        </label>
        {wynik.podstawa_uzasadnienia && <Zrodla adnotacje={[wynik.podstawa_uzasadnienia]} />}

        {wynik.poprzednia_ocena && !wynik.poprzednia_ocena.poziom && (
          <label className="etykieta">
            Poziom poprzedniej oceny (brak w danych kadrowych)
            <input value={f.poprzednia_ocena_poziom ?? ""} onChange={(e) => ustaw({ poprzednia_ocena_poziom: e.target.value || null })} />
          </label>
        )}

        {wynik.czesc_iii.dostepna && (
          <>
            <label className="zaznacz">
              <input
                type="checkbox"
                checked={f.dolacz_wniosek_o_stopien}
                onChange={(e) => ustaw({ dolacz_wniosek_o_stopien: e.target.checked })}
              />
              <span>Dołącz wniosek o kolejny stopień służbowy (część III arkusza)</span>
            </label>
            <Zrodla adnotacje={[wynik.czesc_iii.adnotacja]} />
          </>
        )}

        <label className="zaznacz">
          <input
            type="checkbox"
            checked={z !== null}
            onChange={(e) =>
              ustaw({
                zmiana_terminu: e.target.checked
                  ? { nowy_termin: "", data_zawiadomienia: "", przyczyna: "wniosek_ocenianego" }
                  : null,
              })
            }
          />
          <span>Zmiana terminu sporządzenia oceny (zawiadomienie § 8)</span>
        </label>
        {z && (
          <div className="nowy-przyklad">
            <div className="siatka-dat">
              <PoleDaty nazwa="Nowy termin" wartosc={z.nowy_termin || null} onZmiana={(v) => ustawZmiane({ nowy_termin: v ?? "" })} />
              <PoleDaty nazwa="Data zawiadomienia" wartosc={z.data_zawiadomienia || null} onZmiana={(v) => ustawZmiane({ data_zawiadomienia: v ?? "" })} />
            </div>
            <div className="etykieta">Przyczyna</div>
            <Wybor
              etykieta="Przyczyna zmiany terminu"
              opcje={Object.entries(PRZYCZYNY).map(([w, t]) => ({ wartosc: w as ZmianaTerminu["przyczyna"], tekst: t }))}
              wartosc={z.przyczyna}
              zablokowane={tylkoOdczyt}
              onWybierz={(w) => w && ustawZmiane({ przyczyna: w })}
            />
          </div>
        )}
      </fieldset>

      <div className="wiersz">
        {wynik.zawiadomienie_dostepne ? (
          <button type="button" className="jasny" onClick={pobierzPdf}>
            Pobierz zawiadomienie § 8 (PDF)
          </button>
        ) : (
          <span />
        )}
        {!tylkoOdczyt && (
          <button type="button" disabled={czekam || zlaData || brakUzasadnienia || niepelnaZmiana} onClick={zapisz}>
            {czekam ? "Zapisuję…" : "Zapisz wynik i terminy"}
          </button>
        )}
      </div>
      {blad && <p className="blad">{blad}</p>}
    </section>
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
  return d?.komunikat ?? opisBledu(err);
}

function Slad({ slad }: { slad: SladReguly[] }) {
  return (
    <ol className="slad">
      {slad.map((s) => (
        <li key={s.regula.id + s.opis}>
          {s.opis}
          <Zrodla adnotacje={[s.regula.zrodlo]} />
        </li>
      ))}
    </ol>
  );
}

export function Wynik({
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
  const [dane, setDane] = useState<WynikOkresowy | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    pobierzWynik(token, proces.id)
      .then(setDane)
      .catch((err) => setBlad(bladWyniku(err)));
  }, [token, proces.id]);

  const naglowek = (
    <section>
      <div className="wiersz">
        <div>
          <div className="etykieta">Krok 7 z 8 · Wynik i terminy</div>
          <h2>
            {osoba.imie} {osoba.nazwisko}
          </h2>
          <p className="opis">ocena okresowa · arkusz {proces.arkusz}</p>
        </div>
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do rozmowy
        </button>
      </div>
      {blad && <p className="blad">{blad}</p>}
      {!blad && !dane && <p className="meta">Wczytuję wynik…</p>}
      {dane && (dane.zapisany ? <p className="sukces">Wynik i dane zapisane.</p> : <p className="brak">Wynik nie jest zapisany dla bieżących ocen cząstkowych.</p>)}
    </section>
  );
  if (!dane) return naglowek;

  const o = dane.obliczenie;
  const terminy = TERMINY.map((t) => ({ ...t, termin: dane.terminy[t.klucz] as Termin | null })).filter((t) => t.termin);

  return (
    <>
      {naglowek}

      <section>
        <h2>Wynik oceny</h2>
        <p className="wartosc">
          <span className={`status ${o.wynik}`}>ocena {o.wynik}</span> średnia {o.srednia.replace(".", ",")} · {o.poziom}
        </p>
        <p className="meta">Rozstrzyga: {o.regula_rozstrzygajaca.zrodlo.lokalizator}</p>
        <Zrodla adnotacje={[o.regula_rozstrzygajaca.zrodlo]} />
        <table>
          <thead>
            <tr>
              <th>Kryterium</th>
              <th>Rodzaj</th>
              <th>Ocena cząstkowa</th>
            </tr>
          </thead>
          <tbody>
            {dane.oceny_czastkowe.map((k) => (
              <tr key={k.kompetencja_id}>
                <td>{k.nazwa}</td>
                <td className="meta">{k.rodzaj === "OBOWIAZKOWE" ? "obowiązkowe" : "dodatkowe"}</td>
                <td>{k.punkty} pkt</td>
              </tr>
            ))}
          </tbody>
        </table>
        <details className="zadania-osp">
          <summary>Jak policzono wynik</summary>
          <Slad slad={o.slad} />
        </details>
        <p className="meta">Reguły: {dane.wersja_regul}</p>
      </section>

      <section>
        <h2>Terminy</h2>
        {dane.poprzednia_ocena && (
          <p className="meta">
            Poprzednia ocena: {data(dane.poprzednia_ocena.data)}, {dane.poprzednia_ocena.wynik}
            {dane.poprzednia_ocena.poziom && `, ${dane.poprzednia_ocena.poziom}`}
          </p>
        )}
        <table>
          <thead>
            <tr>
              <th>Termin</th>
              <th>Data</th>
              <th>Skąd</th>
            </tr>
          </thead>
          <tbody>
            {terminy.map(({ klucz, nazwa, termin }) => (
              <tr key={klucz}>
                <td>{nazwa}</td>
                <td>{data(termin!.data)}</td>
                <td>
                  <Slad slad={termin!.slad} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {dane.terminy.zachowaj_kryteria && <p className="meta">Kryteria z poprzedniej oceny zostają.</p>}
        {dane.terminy.slad.length > 0 && <Slad slad={dane.terminy.slad} />}
        {dane.terminy.braki.length > 0 && (
          <div className="brak">
            System nie zgaduje, brakuje danych:
            <ul>
              {dane.terminy.braki.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <DaneOceny
        key={String(dane.zapisany) + JSON.stringify(dane.dane)}
        wynik={dane}
        token={token}
        tylkoOdczyt={!moznaProwadzic}
        onZapisano={setDane}
      />

      <section>
        <div className="wiersz">
          <span className="meta">
            {dane.zapisany ? "Następny krok: arkusz oceny, PDF i EZD." : "Arkusz wymaga zapisanego wyniku i terminów."}
          </span>
          <button type="button" className={dane.zapisany ? "" : "jasny"} onClick={onDalej}>
            Dalej: arkusz oceny
          </button>
        </div>
      </section>
    </>
  );
}
