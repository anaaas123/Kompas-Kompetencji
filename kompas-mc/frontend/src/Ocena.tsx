import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzOcene,
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
import { NAZWA_SCIEZKI, Zrodla, opisBledu } from "./Krok1";
import { LegendaPorownania, SamoocenaPrzyWskazniku, StatusSamoocenyPrzelozonego } from "./Samoocena";

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

function Wskaznik({
  w,
  tylkoOdczyt,
  czekam,
  blad,
  onZapisz,
}: {
  w: WskaznikOceny;
  tylkoOdczyt: boolean;
  czekam: boolean;
  blad?: string;
  onZapisz: (o: OcenaWskaznika) => void;
}) {
  const [dodaje, setDodaje] = useState(false);
  const przyklady = w.ocena?.przyklady ?? [];
  const wybrany = w.poziomy.find((p) => p.poziom === w.ocena?.poziom);
  const zablokowane = tylkoOdczyt || czekam;

  return (
    <li className="kryterium">
      <strong>{w.nazwa}</strong>
      <div className="wiersz">
        <Wybor
          etykieta={`Poziom: ${w.nazwa}`}
          opcje={w.poziomy.map((p) => ({ wartosc: p.poziom, tekst: String(p.poziom), opis: `${p.poziom}: ${p.etykieta}` }))}
          wartosc={w.ocena?.poziom ?? null}
          zablokowane={zablokowane}
          onWybierz={(poziom) => onZapisz({ poziom, brak_podstaw: false, przyklady })}
        />
        <Wybor
          etykieta="Brak podstaw do oceny"
          opcje={[{ wartosc: "brak", tekst: "brak podstaw do oceny" }]}
          wartosc={w.ocena?.brak_podstaw ? "brak" : null}
          zablokowane={zablokowane}
          onWybierz={(b) => onZapisz({ poziom: null, brak_podstaw: b !== null, przyklady })}
        />
      </div>
      {wybrany && (
        <p>
          <span className="etykieta">{wybrany.etykieta}:</span> {wybrany.opis}
        </p>
      )}
      <SamoocenaPrzyWskazniku w={w} />
      <details className="zadania-osp">
        <summary>Opisy poziomów</summary>
        {w.poziomy.map((p) => (
          <p key={p.poziom} className="meta">
            {p.poziom} – {p.etykieta}: {p.opis}
          </p>
        ))}
      </details>

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
        <button type="button" className="link" onClick={() => setDodaje(true)}>
          Dodaj przykład
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
      {w.ostrzezenia.map((o) => (
        <p key={o} className="brak">
          {o}
        </p>
      ))}
      {blad && <p className="blad">{blad}</p>}
    </li>
  );
}

function tekstSugestii(s: Sugestia): string {
  if (s.status === "POZIOM") return `Sugestia: ${s.punkty} pkt`;
  if (s.status === "REMIS") return `Sugestia: ${(s.punkty_remisu ?? []).join(" albo ")} pkt`;
  return "Sugestia: niewystarczające dane";
}

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
  const s = kr.sugestia;
  const wymagane = wymagaUzasadnienia(s, punkty);

  return (
    <div className="decyzja">
      <div className="wiersz-przeslanki">
        <strong>{tekstSugestii(s)}</strong>
        <span className="status uwaga">{s.metodyka}</span>
      </div>
      <p className="meta">{s.opis}</p>

      {d && !edytuje && (
        <div className="sukces">
          Ocena cząstkowa: {d.punkty} pkt ({skala.etykiety[String(d.punkty)]})
          {d.zgodna_z_sugestia === false && d.uzasadnienie && <> · uzasadnienie: {d.uzasadnienie}</>} · zapisał{" "}
          {d.zapisal}
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
      {!d && tylkoOdczyt && <p className="meta">Przełożony nie zapisał jeszcze oceny cząstkowej.</p>}

      {!tylkoOdczyt && edytuje && (
        <div className="nowy-przyklad">
          <div className="etykieta">Ocena cząstkowa (decyzja przełożonego)</div>
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
              Uzasadnienie odejścia od sugestii (wymagane)
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
              onClick={() =>
                punkty !== null && onZapisz({ punkty, uzasadnienie: wymagane ? uzasadnienie.trim() : null })
              }
            >
              Zapisz ocenę cząstkową
            </button>
          </div>
        </div>
      )}
      {blad && <p className="blad">{blad}</p>}
    </div>
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
  const [blad, setBlad] = useState<string | null>(null);
  const [bledy, setBledy] = useState<Record<string, string>>({});
  const [czekam, setCzekam] = useState<string | null>(null);

  useEffect(() => {
    pobierzOcene(token, proces.id)
      .then(setDane)
      .catch((err) => setBlad(bladZapisu(err)));
  }, [token, proces.id]);

  if (!dane) {
    return <section>{blad ? <p className="blad">{blad}</p> : <p className="meta">Wczytuję ocenę…</p>}</section>;
  }

  const tylkoOdczyt = !moznaProwadzic;
  const k = dane.kompletnosc;

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

  return (
    <>
      <section>
        <div className="wiersz">
          <div>
            <div className="etykieta">Kroki 3–5 z 8 · Ocena kryteriów</div>
            <h2>
              {osoba.imie} {osoba.nazwisko}
            </h2>
            <p className="opis">
              {NAZWA_SCIEZKI[dane.sciezka]} · arkusz {dane.arkusz === "PIERWSZA" ? "pierwszej oceny" : dane.arkusz}
            </p>
          </div>
          <button type="button" className="link" onClick={onWstecz}>
            Wróć do kroku 2
          </button>
        </div>
        <p className="meta">
          Ocenione wskaźniki: {k.wskazniki_ocenione} z {k.wskazniki_wybrane} · oceny cząstkowe: {k.kryteria_z_decyzja} z{" "}
          {k.kryteria}
        </p>
        <StatusSamoocenyPrzelozonego status={dane.samoocena_status} />
        {dane.samoocena_status === "przekazana" && <LegendaPorownania />}
      </section>

      <section>
        <h2>Jak oceniać</h2>
        <ul className="zadania">
          {dane.instrukcja.map((i) => (
            <li key={i.tekst}>
              {i.tekst}
              <Zrodla adnotacje={[i.adnotacja]} />
            </li>
          ))}
        </ul>
      </section>

      {dane.kryteria.map((kr) => (
        <section key={kr.kompetencja_id}>
          <div className="wiersz">
            <h2>{kr.nazwa}</h2>
            <span className="meta">{kr.rodzaj === "OBOWIAZKOWE" ? "obowiązkowe" : "dodatkowe"}</span>
          </div>
          <ul className="wskazniki">
            {kr.wskazniki.map((w) => (
              <Wskaznik
                key={w.wskaznik_id}
                w={w}
                tylkoOdczyt={tylkoOdczyt}
                czekam={czekam === w.wskaznik_id}
                blad={bledy[w.wskaznik_id]}
                onZapisz={(o) => zapiszWskaznik(w.wskaznik_id, o)}
              />
            ))}
          </ul>
          <DecyzjaKryterium
            key={kr.decyzja?.zapisano ?? "brak"}
            kr={kr}
            skala={dane.skala}
            tylkoOdczyt={tylkoOdczyt}
            czekam={czekam === kr.kompetencja_id}
            blad={bledy[kr.kompetencja_id]}
            onZapisz={(d) => zapiszDecyzje1(kr.kompetencja_id, d)}
          />
        </section>
      ))}

      <section>
        <div className="wiersz">
          <span className="meta">
            {k.kryteria_z_decyzja === k.kryteria
              ? "Wszystkie kryteria mają ocenę cząstkową."
              : `Oceny cząstkowe: ${k.kryteria_z_decyzja} z ${k.kryteria}. Wynik policzy się po ocenach wszystkich kryteriów.`}
          </span>
          <button type="button" onClick={onDalej}>
            Dalej: rozmowa oceniająca
          </button>
        </div>
      </section>

      <section>
        <h2>Metodyka sugestii</h2>
        <p>
          <span className="status uwaga">{dane.metodyka.status}</span>
        </p>
        <p>{dane.metodyka.opis}</p>
        <Zrodla adnotacje={dane.metodyka.adnotacje} />
        <p className="meta">Skala ocen: {dane.skala.punkty.join(", ")} pkt</p>
        <Zrodla adnotacje={dane.skala.adnotacje} />
      </section>
    </>
  );
}
