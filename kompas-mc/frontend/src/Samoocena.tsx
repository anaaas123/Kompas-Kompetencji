import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzSamoocene,
  przekazSamoocene,
  zapiszSamoocene,
  type PozycjaSamooceny,
  type Pracownik,
  type PrzykladSamooceny,
  type Samoocena,
  type StanOceny,
  type WskaznikOceny,
  type WskaznikSamooceny,
} from "./api";
import { opisBledu } from "./Krok1";
import { PostepKrokow } from "./Wykresy";
import { data } from "./zespol-dane";
import "./samoocena.css";

/**
 * Samoocena (#9): ekran pracownika „Moja samoocena” oraz porównanie z oceną przełożonego w krokach 3 i 6.
 * Samoocena nie wpływa na sugestię ani na ocenę (reguła samoocena.poza-sugestia). Porównanie: dwa znaczniki na
 * jednej skali 1–9 (pełny = przełożony, pusty = pracownik); bursztyn tylko przy różnicy ≥ 4, zawsze z tekstem.
 */

const PROG = 4;
const POZIOMY = [1, 3, 5, 7, 9];
const pozycjaNaSkali = (p: number) => `${((p - 1) / 8) * 100}%`;

// ---------------------------------------------------------------- porównanie na skali

export function PorownanieSkali({
  przelozony,
  pracownik,
  rozbieznosc,
}: {
  przelozony: number | null;
  pracownik: { poziom: number | null; brak_zdania: boolean } | null | undefined;
  rozbieznosc: boolean | null | undefined;
}) {
  const samo = pracownik?.poziom ?? null;
  const roznica = samo !== null && przelozony !== null ? Math.abs(samo - przelozony) : null;
  const podpis = [
    pracownik?.brak_zdania ? "Samoocena: nie mam zdania" : samo !== null ? `Samoocena ${samo}` : "Samoocena: brak odpowiedzi",
    przelozony !== null ? `Twoja ocena ${przelozony}` : "Twoja ocena: jeszcze niewybrana",
    roznica !== null ? `różnica ${roznica} pkt` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const lewo = samo !== null && przelozony !== null ? Math.min(samo, przelozony) : null;
  const prawo = samo !== null && przelozony !== null ? Math.max(samo, przelozony) : null;

  return (
    <div className={`porownanie ${rozbieznosc ? "rozbieznosc" : ""}`}>
      <div className="skala" role="img" aria-label={podpis}>
        <span className="os" />
        {POZIOMY.map((p) => (
          <span key={p} className="kreska" style={{ left: pozycjaNaSkali(p) }}>
            <span className="liczba">{p}</span>
          </span>
        ))}
        {lewo !== null && prawo !== null && lewo !== prawo && (
          <span className="odcinek-roznicy" style={{ left: pozycjaNaSkali(lewo), right: `calc(100% - ${pozycjaNaSkali(prawo)})` }} />
        )}
        {przelozony !== null && <span className="znak przelozony" style={{ left: pozycjaNaSkali(przelozony) }} />}
        {samo !== null && (
          <span className={`znak pracownik ${samo === przelozony ? "nad" : ""}`} style={{ left: pozycjaNaSkali(samo) }} />
        )}
      </div>
      <p className="podpis-porownania">
        {podpis}
        {rozbieznosc && <span className="do-omowienia">do omówienia</span>}
      </p>
    </div>
  );
}

export function LegendaPorownania() {
  return (
    <p className="legenda-porownania">
      <span className="znak-legendy przelozony" aria-hidden="true" /> Twoja ocena
      <span className="znak-legendy pracownik" aria-hidden="true" /> Samoocena pracownika
      <span className="meta">Bursztynowy odcinek: różnica co najmniej {PROG} pkt. Samoocena nie wpływa na sugestię ani na ocenę.</span>
    </p>
  );
}

/** Pasek nad krokiem 3: status samooceny dla przełożonego. */
export function StatusSamoocenyPrzelozonego({ status }: { status: StanOceny["samoocena_status"] }) {
  if (!status) return null;
  const tekst =
    status === "przekazana"
      ? "Pracownik przekazał samoocenę. Zobaczysz ją przy wskaźniku po wybraniu swojego poziomu."
      : status === "szkic"
        ? "Pracownik wypełnia samoocenę. Zobaczysz ją po przekazaniu."
        : "Pracownik nie rozpoczął samooceny.";
  return (
    <p className={`status-samooceny ${status}`}>
      <strong>Samoocena: </strong>
      {tekst}
    </p>
  );
}

/**
 * Krok 3: samoocena przy wskaźniku. Odsłania się po wyborze poziomu przez przełożonego (żeby nie zakotwiczać
 * oceny); „Pokaż teraz” odsłania wcześniej.
 */
export function SamoocenaPrzyWskazniku({ w }: { w: WskaznikOceny }) {
  const [pokaz, setPokaz] = useState(false);
  if (!w.samoocena) return null;
  const ocenil = w.ocena?.poziom != null || w.ocena?.brak_podstaw;
  if (!ocenil && !pokaz) {
    return (
      <p className="samoocena-zwinieta">
        Samoocena pracownika czeka na Twój wybór poziomu.{" "}
        <button type="button" className="link" onClick={() => setPokaz(true)}>
          Pokaż teraz
        </button>
      </p>
    );
  }
  return (
    <div className="samoocena-wskaznika">
      <PorownanieSkali przelozony={w.ocena?.poziom ?? null} pracownik={w.samoocena} rozbieznosc={w.rozbieznosc} />
      {w.samoocena.przyklad && <PrzykladPracownika p={w.samoocena.przyklad} />}
    </div>
  );
}

function PrzykladPracownika({ p }: { p: PrzykladSamooceny }) {
  return (
    <div className="przyklad-pracownika">
      <span className="etykieta">Przykład pracownika</span>
      <p>
        <span className="etykieta">Sytuacja:</span> {p.sytuacja} <span className="etykieta">Działanie:</span> {p.dzialanie}{" "}
        <span className="etykieta">Rezultat:</span> {p.rezultat}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- krok 6: agenda rozbieżności

function pytanie(w: WskaznikOceny): string {
  const s = w.samoocena;
  const o = w.ocena;
  if (!s || s.poziom === null || !o || o.poziom === null) return "Czy w tym okresie była okazja zaobserwować to zachowanie?";
  if (s.poziom > o.poziom)
    return "Jaka sytuacja z pracy stoi za samooceną? Czy jest przykład, którego przełożony jeszcze nie zna?";
  return "Które działania przełożony widzi jako mocną stronę? Czy pracownik uwzględnił je w samoocenie?";
}

/** Krok 6: samoocena przy rozmowie. Najpierw rozbieżności z pytaniem i obu opisami poziomów, reszta zwinięta. */
export function AgendaRozbieznosci({ stan }: { stan: StanOceny }) {
  if (stan.samoocena_status !== "przekazana") {
    return stan.samoocena_status ? <StatusSamoocenyPrzelozonego status={stan.samoocena_status} /> : null;
  }
  const wszystkie = stan.kryteria.flatMap((k) => k.wskazniki.map((w) => ({ k: k.nazwa, w })));
  const porownane = wszystkie.filter(({ w }) => w.rozbieznosc !== null && w.rozbieznosc !== undefined);
  const rozbiezne = porownane.filter(({ w }) => w.rozbieznosc);
  const reszta = wszystkie.filter(({ w }) => !w.rozbieznosc);

  return (
    <section className="agenda">
      <h2>Samoocena na rozmowie</h2>
      <p className="meta">
        {wszystkie.length} wskaźników · porównano {porownane.length} (oba poziomy podane) · do omówienia {rozbiezne.length}{" "}
        (różnica co najmniej {PROG} pkt). Samoocena nie zmienia oceny.
      </p>
      <LegendaPorownania />
      {rozbiezne.length === 0 && <p>Przy żadnym wskaźniku różnica nie przekracza {PROG - 1} pkt.</p>}
      <ol className="lista-agendy">
        {rozbiezne.map(({ k, w }) => {
          const opis = (p: number | null | undefined) => w.poziomy.find((x) => x.poziom === p);
          const samo = opis(w.samoocena?.poziom);
          const moja = opis(w.ocena?.poziom);
          return (
            <li key={w.wskaznik_id}>
              <span className="etykieta">{k}</span>
              <strong>{w.nazwa}</strong>
              <PorownanieSkali przelozony={w.ocena?.poziom ?? null} pracownik={w.samoocena} rozbieznosc />
              <div className="dwa-opisy">
                {samo && (
                  <p>
                    <span className="etykieta">Samoocena {samo.poziom}: {samo.etykieta}</span>
                    {samo.opis}
                  </p>
                )}
                {moja && (
                  <p>
                    <span className="etykieta">Twoja ocena {moja.poziom}: {moja.etykieta}</span>
                    {moja.opis}
                  </p>
                )}
              </div>
              <p className="pytanie-agendy">{pytanie(w)}</p>
              {w.samoocena?.przyklad && <PrzykladPracownika p={w.samoocena.przyklad} />}
            </li>
          );
        })}
      </ol>
      {reszta.length > 0 && (
        <details className="pozostale">
          <summary>Pozostałe wskaźniki ({reszta.length})</summary>
          <ul className="lista-agendy zwarta">
            {reszta.map(({ w }) => (
              <li key={w.wskaznik_id}>
                <strong>{w.nazwa}</strong>
                <PorownanieSkali przelozony={w.ocena?.poziom ?? null} pracownik={w.samoocena} rozbieznosc={w.rozbieznosc} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- ekran pracownika

function bladSamooceny(err: unknown): string {
  if (err instanceof BladApi && err.status === 409)
    return typeof err.detail === "string" ? err.detail : "Samoocena jest niedostępna albo już przekazana.";
  const bledy = err instanceof BladApi ? (err.detail as { bledy?: string[] } | null)?.bledy : undefined;
  return Array.isArray(bledy) ? bledy.join(" ") : opisBledu(err);
}

function grupuj(wskazniki: WskaznikSamooceny[]) {
  const kryteria: { nazwa: string; wskazniki: WskaznikSamooceny[] }[] = [];
  for (const w of wskazniki) {
    const k = kryteria.find((x) => x.nazwa === w.kryterium);
    if (k) k.wskazniki.push(w);
    else kryteria.push({ nazwa: w.kryterium, wskazniki: [w] });
  }
  return kryteria;
}

/**
 * „Moja samoocena”: jeden przebieg z „Dalej”, ekran na kryterium, na końcu podsumowanie i „Przekaż”.
 * Każdy wybór zapisuje się od razu jako szkic.
 */
export function MojaSamoocena({
  token,
  osoba,
  procesId,
  onWroc,
}: {
  token: string;
  osoba: Pracownik;
  procesId: number;
  onWroc: () => void;
}) {
  const [s, setS] = useState<Samoocena | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [ekran, setEkran] = useState(0);
  const [czekam, setCzekam] = useState(false);
  const [potwierdz, setPotwierdz] = useState(false);

  useEffect(() => {
    pobierzSamoocene(token, procesId)
      .then(setS)
      .catch((err) => setBlad(bladSamooceny(err)));
  }, [token, procesId]);

  const glowa = (
    <div className="naglowek-samooceny">
      <button type="button" className="link" onClick={onWroc}>
        Wróć do karty
      </button>
      <h1>Moja samoocena</h1>
      <p className="opis">
        {osoba.imie} {osoba.nazwisko} · {osoba.stanowisko}
      </p>
    </div>
  );

  if (!s) return <div className="widok-samooceny">{glowa}{blad ? <p className="blad">{blad}</p> : <p className="meta">Wczytuję…</p>}</div>;

  const kryteria = grupuj(s.wskazniki);
  const przekazana = s.status === "przekazana";
  const podsumowanie = ekran >= kryteria.length;

  async function zapisz(wskaznikId: string, p: PozycjaSamooceny | null) {
    setCzekam(true);
    setBlad(null);
    try {
      setS(await zapiszSamoocene(token, procesId, { [wskaznikId]: p }));
    } catch (err) {
      setBlad(bladSamooceny(err));
    } finally {
      setCzekam(false);
    }
  }

  async function przekaz() {
    setCzekam(true);
    setBlad(null);
    try {
      setS(await przekazSamoocene(token, procesId));
      setPotwierdz(false);
    } catch (err) {
      setBlad(bladSamooceny(err));
    } finally {
      setCzekam(false);
    }
  }

  if (przekazana) {
    return (
      <div className="widok-samooceny">
        {glowa}
        <p className="sukces">
          Przekazano {s.przekazano ? data(s.przekazano) : ""}. Przełożony omówi samoocenę z Tobą na rozmowie oceniającej.
          Odpowiedzi nie można już zmienić.
        </p>
        <Podsumowanie kryteria={kryteria} />
      </div>
    );
  }

  return (
    <div className="widok-samooceny">
      {glowa}
      {ekran === 0 && (
        <p className="wstep-samooceny">
          To nie jest egzamin i nie zmienia oceny. Przy każdym wskaźniku wybierz opis najbliższy Twojej pracy w tym okresie
          albo „Nie mam zdania”. Przełożony zobaczy odpowiedzi dopiero po przekazaniu, HR nie zobaczy ich wcale.
        </p>
      )}
      <div className="postep-samooceny">
        <span className="meta">
          {podsumowanie ? "Podsumowanie" : `Kryterium ${ekran + 1} z ${kryteria.length}`} · odpowiedzi {s.wypelniono} z {s.wybrano}
        </span>
        <PostepKrokow krok={ekran + 1} krokow={kryteria.length + 1} etykieta="Postęp samooceny" />
      </div>

      {!podsumowanie && (
        <section className="kryterium-samooceny">
          <h2>{kryteria[ekran].nazwa}</h2>
          {kryteria[ekran].wskazniki.map((w) => (
            <WskaznikDoSamooceny key={w.wskaznik_id} w={w} czekam={czekam} onZapisz={(p) => zapisz(w.wskaznik_id, p)} />
          ))}
        </section>
      )}

      {podsumowanie && (
        <section>
          <h2>Podsumowanie</h2>
          <Podsumowanie kryteria={kryteria} />
          {s.wypelniono < s.wybrano && (
            <p className="brak">
              Brakuje {s.wybrano - s.wypelniono} odpowiedzi. Przy każdym wskaźniku wybierz poziom albo „Nie mam zdania”.
            </p>
          )}
          {potwierdz && (
            <p className="potwierdzenie">Po przekazaniu nie zmienisz odpowiedzi. Przełożony zobaczy je przy swojej ocenie.</p>
          )}
        </section>
      )}

      {blad && <p className="blad">{blad}</p>}

      <div className="przyciski-samooceny">
        {ekran > 0 ? (
          <button type="button" className="link" onClick={() => { setEkran(ekran - 1); setPotwierdz(false); }}>
            Wstecz
          </button>
        ) : (
          <span />
        )}
        {!podsumowanie && (
          <button type="button" onClick={() => setEkran(ekran + 1)}>
            Dalej
          </button>
        )}
        {podsumowanie && !potwierdz && (
          <button type="button" disabled={s.wypelniono < s.wybrano} onClick={() => setPotwierdz(true)}>
            Przekaż przełożonemu
          </button>
        )}
        {podsumowanie && potwierdz && (
          <button type="button" disabled={czekam} onClick={przekaz}>
            {czekam ? "Przekazuję…" : "Tak, przekaż"}
          </button>
        )}
      </div>
    </div>
  );
}

function WskaznikDoSamooceny({
  w,
  czekam,
  onZapisz,
}: {
  w: WskaznikSamooceny;
  czekam: boolean;
  onZapisz: (p: PozycjaSamooceny | null) => void;
}) {
  const p = w.pozycja;
  const [przyklad, setPrzyklad] = useState<PrzykladSamooceny | null>(null);
  const zapiszPoziom = (poziom: number | null, brak = false) =>
    onZapisz({ poziom, brak_zdania: brak, przyklad: p?.przyklad ?? null });
  const pelny = przyklad && przyklad.sytuacja.trim() && przyklad.dzialanie.trim() && przyklad.rezultat.trim();

  return (
    <div className="wskaznik-samooceny">
      <strong>{w.nazwa}</strong>
      <div className="poziomy-samooceny" role="radiogroup" aria-label={w.nazwa}>
        {w.poziomy.map((o) => (
          <button
            key={o.poziom}
            type="button"
            role="radio"
            aria-checked={p?.poziom === o.poziom}
            disabled={czekam}
            className="poziom-samooceny"
            onClick={() => zapiszPoziom(o.poziom)}
          >
            <span className="numer-poziomu">{o.poziom}</span>
            <span>
              <strong>{o.etykieta}</strong>
              <span className="opis-poziomu">{o.opis}</span>
            </span>
          </button>
        ))}
        <button
          type="button"
          role="radio"
          aria-checked={!!p?.brak_zdania}
          disabled={czekam}
          className="poziom-samooceny bez-zdania"
          onClick={() => zapiszPoziom(null, true)}
        >
          <span className="numer-poziomu">–</span>
          <span>
            <strong>Nie mam zdania</strong>
            <span className="opis-poziomu">Nie obniża to oceny.</span>
          </span>
        </button>
      </div>

      {p?.przyklad && !przyklad && (
        <div className="przyklad-pracownika">
          <span className="etykieta">Twój przykład</span>
          <p>
            {p.przyklad.sytuacja} → {p.przyklad.dzialanie} → {p.przyklad.rezultat}
          </p>
          <button type="button" className="link" disabled={czekam} onClick={() => onZapisz({ ...p, przyklad: null })}>
            Usuń przykład
          </button>
        </div>
      )}
      {p && !p.przyklad && !przyklad && (
        <button type="button" className="link" onClick={() => setPrzyklad({ sytuacja: "", dzialanie: "", rezultat: "" })}>
          Dodaj przykład z pracy (opcjonalnie)
        </button>
      )}
      {przyklad && (
        <div className="nowy-przyklad">
          {(
            [
              ["sytuacja", "Co się wydarzyło?"],
              ["dzialanie", "Co zrobiłeś lub zrobiłaś?"],
              ["rezultat", "Jaki był rezultat?"],
            ] as const
          ).map(([klucz, etykieta]) => (
            <label key={klucz} className="etykieta">
              {etykieta}
              <textarea rows={2} value={przyklad[klucz]} onChange={(e) => setPrzyklad({ ...przyklad, [klucz]: e.target.value })} />
            </label>
          ))}
          <p className="meta zero">Bez nazwisk, numerów spraw i danych innych osób.</p>
          <div className="wiersz">
            <button type="button" className="link" onClick={() => setPrzyklad(null)}>
              Anuluj
            </button>
            <button
              type="button"
              className="jasny"
              disabled={!pelny || czekam || !p}
              onClick={() => {
                if (!p || !pelny) return;
                onZapisz({
                  ...p,
                  przyklad: { sytuacja: przyklad.sytuacja.trim(), dzialanie: przyklad.dzialanie.trim(), rezultat: przyklad.rezultat.trim() },
                });
                setPrzyklad(null);
              }}
            >
              Zapisz przykład
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Podsumowanie({ kryteria }: { kryteria: { nazwa: string; wskazniki: WskaznikSamooceny[] }[] }) {
  return (
    <ul className="podsumowanie-samooceny">
      {kryteria.flatMap((k) =>
        k.wskazniki.map((w) => {
          const p = w.pozycja;
          const opis = p?.poziom != null ? w.poziomy.find((x) => x.poziom === p.poziom) : null;
          return (
            <li key={w.wskaznik_id}>
              <span>
                <span className="etykieta">{k.nazwa}</span>
                {w.nazwa}
              </span>
              <strong>{p?.brak_zdania ? "nie mam zdania" : opis ? `${opis.poziom} · ${opis.etykieta}` : "brak odpowiedzi"}</strong>
            </li>
          );
        }),
      )}
    </ul>
  );
}
