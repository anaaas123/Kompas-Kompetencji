import { useEffect, useState, type CSSProperties } from "react";
import {
  BladApi,
  pobierzOcene,
  pobierzKrok2,
  przygotujRozmowe,
  zapiszDecyzje,
  zapiszWskazniki,
  type KryteriumOceny,
  type PlanRozmowy,
  type OcenaWskaznika,
  type Pracownik,
  type ProcesOceny,
  type StanOceny,
  type Sugestia,
  type WskaznikOceny,
} from "./api";
import { NAZWA_SCIEZKI, Zrodla, nazwaKryterium, opisBledu } from "./Krok1";
import { AgendaRozbieznosci, LegendaPorownania, SamoocenaPrzyWskazniku, StatusSamoocenyPrzelozonego } from "./Samoocena";
import { CzatRozmowy } from "./Rozmowa";
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
  const [dopytaj, setDopytaj] = useState(false);
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
          {pytania.length > 1 && (
            <>
              <button type="button" className="link oc-brak" aria-expanded={dopytaj} onClick={() => setDopytaj((v) => !v)}>
                {dopytaj ? "Ukryj dopytania" : `Dopytaj (${pytania.length - 1})`}
              </button>
              <Zwijane otwarte={dopytaj}>
                <ul className="oc-pytania">
                  {pytania.slice(1).map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </Zwijane>
            </>
          )}
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
  onWskazniki,
}: {
  kr: KryteriumOceny;
  onWskazniki: () => void;
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
      <div className="oc-pod-kaflami">
        <h3>{nazwaKryterium(kr.nazwa)}</h3>
        <button type="button" className="link" onClick={onWskazniki}>
          Wróć do wskaźników
        </button>
      </div>
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

/** Notatka z rozmowy w sessionStorage karty (API jej nie zapisuje; arkusz bierze wnioski z kroku 7). */
function useNotatka(klucz: string): [string, (t: string) => void] {
  const [tekst, setTekst] = useState(() => sessionStorage.getItem(klucz) ?? "");
  useEffect(() => {
    if (tekst) sessionStorage.setItem(klucz, tekst);
  }, [klucz, tekst]);
  return [tekst, setTekst];
}

/** Temat rozmowy (§ 10): pytania z szablonów, notatka; przy „Rozwoju” szkic informacji zwrotnej i asystent. */
function EkranTematu({
  temat,
  plan,
  token,
  procesId,
  tylkoOdczyt,
}: {
  temat: Temat;
  plan: PlanRozmowy | null;
  token: string;
  procesId: number;
  tylkoOdczyt: boolean;
}) {
  const [notatka, setNotatka] = useNotatka(`kompas-notatka-${procesId}-${temat}`);
  const [czat, setCzat] = useState(false);
  const wszystkie = (plan?.pytania ?? []).filter((q) => tematPytania(q.id) === temat).map((q) => q.tresc);
  // Obowiązki: szablon pyt.osp.zadanie to jedno pytanie + treść zadania; pytanie raz, pod nim lista zadań z OSP.
  // ponytail: podział po stałym zwrocie z rozmowa.yaml; przy zmianie szablonu lista zadań pokaże całe pytania.
  const ZADANIE = " Zadanie z opisu stanowiska: ";
  const pytania = temat === "obowiazki" && wszystkie[0]?.includes(ZADANIE) ? [wszystkie[0].split(ZADANIE)[0]] : wszystkie;
  const zadaniaOsp = temat === "obowiazki" ? wszystkie.map((t) => (t.split(ZADANIE)[1] ?? "").replace(/^„|”\.?$/g, "")).filter(Boolean) : [];
  const zakres = (plan?.zakres ?? []).filter((z) => ZAKRES_TEMATU[temat].test(z.id));
  // Szkic informacji zwrotnej z bieżących ocen (plan liczony przy wejściu na ekran); zmiany zostają w karcie.
  const klucz = `kompas-szkic-${procesId}`;
  const zapisany = JSON.parse(sessionStorage.getItem(klucz) ?? "null") as { mocne: string; rozwoj: string } | null;
  const [mocne, setMocne] = useState(zapisany?.mocne ?? "");
  const [obszary, setObszary] = useState(zapisany?.rozwoj ?? "");
  useEffect(() => {
    if (!zapisany && plan) {
      setMocne(plan.informacja_zwrotna.mocne_strony.join("\n"));
      setObszary(plan.informacja_zwrotna.obszary_rozwoju.join("\n"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan]);
  useEffect(() => {
    if (mocne || obszary) sessionStorage.setItem(klucz, JSON.stringify({ mocne, rozwoj: obszary }));
  }, [klucz, mocne, obszary]);

  return (
    <div className="oc-ekran">
      <div className="oc-glowa">
        <p className="meta">Rozmowa oceniająca · {NAZWA_TEMATU[temat].toLowerCase()}</p>
        <h2 className="oc-tytul" tabIndex={-1}>
          {TYTUL_TEMATU[temat]}
        </h2>
        {zakres.map((z) => (
          <p key={z.id} className="meta">
            {z.punkt}
          </p>
        ))}
      </div>
      {zadaniaOsp.length > 0 && (
        <div className="oc-lista-zadan">
          <p className="etykieta">Główne zadania z opisu stanowiska</p>
          <ul className="oc-pytania">
            {zadaniaOsp.map((z) => (
              <li key={z} title={z}>
                {z}
              </li>
            ))}
          </ul>
        </div>
      )}
      {pytania.length > 0 && (
        <div className="oc-pytanie">
          <Ikona nazwa="pytanie" rozmiar={20} />
          <div>
            <p className="oc-pytanie-tytul">{zadaniaOsp.length > 0 ? "Przy każdym zadaniu możesz zapytać" : "Możesz zapytać"}</p>
            {pytania.length === 1 ? (
              <p>{pytania[0]}</p>
            ) : (
              <ul className="oc-pytania">
                {pytania.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <label className="etykieta oc-uwagi">
        Notatka z rozmowy (opcjonalnie)
        <textarea rows={3} value={notatka} disabled={tylkoOdczyt} onChange={(e) => setNotatka(e.target.value)} />
      </label>
      {temat === "rozwoj" && (
        <>
          <label className="etykieta oc-uwagi">
            Mocne strony (szkic z Twoich ocen)
            <textarea rows={3} value={mocne} disabled={tylkoOdczyt} onChange={(e) => setMocne(e.target.value)} />
          </label>
          <label className="etykieta oc-uwagi">
            Obszary rozwoju (szkic z Twoich ocen)
            <textarea
              rows={3}
              value={obszary}
              disabled={tylkoOdczyt}
              placeholder="Brak wskaźników poniżej oczekiwań. Dopisz, jeśli coś wyszło w rozmowie."
              onChange={(e) => setObszary(e.target.value)}
            />
          </label>
          <button type="button" className="link oc-brak" aria-expanded={czat} onClick={() => setCzat((v) => !v)}>
            {czat ? "Ukryj asystenta" : "Zapytaj asystenta o rozmowę"}
          </button>
          <Zwijane otwarte={czat}>
            <CzatRozmowy token={token} procesId={procesId} />
          </Zwijane>
        </>
      )}
      {zakres[0] && <Zrodla adnotacje={zakres.flatMap((z) => z.adnotacje)} />}
    </div>
  );
}

/* Rozmowa oceniająca jest jednym przebiegiem (§ 10 rozp. 2016): obowiązki, kryteria (tu wybór poziomów),
   cele, rozwój; ocena na piśmie (krok 7) powstaje z wniosków rozmowy (§ 11 ust. 2). Karol 23:50. */
type Temat = "obowiazki" | "sprawozdanie" | "cele" | "rozwoj";
const NAZWA_TEMATU: Record<Temat, string> = { obowiazki: "Obowiązki", sprawozdanie: "Sprawozdanie", cele: "Cele", rozwoj: "Rozwój" };
const TYTUL_TEMATU: Record<Temat, string> = {
  obowiazki: "Główne obowiązki w okresie oceny",
  sprawozdanie: "Sprawozdanie i egzamin",
  cele: "Cele z początku okresu",
  rozwoj: "Rozwój i informacja zwrotna",
};
/** Temat pytania z identyfikatora szablonu (konfiguracja/rozmowa.yaml). */
const tematPytania = (id: string): Temat | null =>
  id.startsWith("pyt.osp.zadanie")
    ? "obowiazki"
    : id.startsWith("pyt.sprawozdanie")
      ? "sprawozdanie"
      : id.startsWith("pyt.cele")
        ? "cele"
        : id.startsWith("pyt.rozwoj")
          ? "rozwoj"
          : null;
/** Punkt zakresu rozmowy (konfiguracja/rozmowa.yaml) należący do tematu. */
const ZAKRES_TEMATU: Record<Temat, RegExp> = { obowiazki: /obowiazki/, sprawozdanie: /sprawozdanie|egzamin/, cele: /cele/, rozwoj: /rozwoj/ };

type Krok = { typ: "temat"; temat: Temat } | { typ: "wskaznik"; kr: number; w: number } | { typ: "podsumowanie" };

const kroki = (dane: StanOceny, plan: PlanRozmowy | null): Krok[] => {
  const jest = (t: Temat) => (plan?.pytania ?? []).some((q) => tematPytania(q.id) === t);
  return [
    ...(jest("obowiazki") ? [{ typ: "temat", temat: "obowiazki" } as Krok] : []),
    ...(jest("sprawozdanie") ? [{ typ: "temat", temat: "sprawozdanie" } as Krok] : []),
    ...dane.kryteria.flatMap((kr, i) => kr.wskazniki.map((_, j): Krok => ({ typ: "wskaznik", kr: i, w: j }))),
    ...(jest("cele") ? [{ typ: "temat", temat: "cele" } as Krok] : []),
    { typ: "temat", temat: "rozwoj" },
    { typ: "podsumowanie" },
  ];
};

function etykietaDalej(k: Krok | undefined, dane: StanOceny): string {
  if (!k) return "";
  if (k.typ === "podsumowanie") return "Dalej: podsumowanie";
  if (k.typ === "temat") return `Dalej: ${NAZWA_TEMATU[k.temat].toLowerCase()}`;
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
          {k.typ === "podsumowanie"
            ? "Podsumowanie"
            : k.typ === "temat"
              ? NAZWA_TEMATU[k.temat]
              : `Kryterium ${k.kr + 1} z ${dane.kryteria.length}`}
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
          {lista.flatMap((x, i) => {
            // Wiersz na temat rozmowy, na kryterium (pierwszy wskaźnik) i na podsumowanie.
            if (x.typ === "wskaznik" && x.w !== 0) return [];
            const nr = lista.slice(0, i).filter((y) => y.typ !== "wskaznik" || y.w === 0).length + 1;
            const kr = x.typ === "wskaznik" ? dane.kryteria[x.kr] : null;
            const tu =
              x.typ === "wskaznik" ? k.typ === "wskaznik" && k.kr === x.kr : x.typ === "temat" ? k.typ === "temat" && k.temat === x.temat : k.typ === "podsumowanie";
            const nazwa = kr ? nazwaKryterium(kr.nazwa) : x.typ === "temat" ? NAZWA_TEMATU[x.temat] : "Podsumowanie";
            const stan = kr
              ? kr.decyzja
                ? `${kr.decyzja.punkty} pkt`
                : `${kr.wskazniki.filter(oceniony).length} z ${kr.wskazniki.length}`
              : x.typ === "podsumowanie"
                ? `${dane.kompletnosc.kryteria_z_decyzja} z ${dane.kompletnosc.kryteria}`
                : "";
            return [
              <li key={kr ? kr.kompetencja_id : x.typ === "temat" ? x.temat : "podsumowanie"}>
                <button type="button" aria-current={tu ? "step" : undefined} onClick={() => idz(i)}>
                  <span className={`oc-os-nr ${kr?.decyzja ? "gotowe" : ""}`} aria-hidden="true">
                    {kr?.decyzja ? <Ikona nazwa="ok" rozmiar={14} /> : nr}
                  </span>
                  <span className="oc-os-nazwa">{nazwa}</span>
                  {stan && <span className="meta">{stan}</span>}
                </button>
              </li>,
            ];
          })}
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
  const [plan, setPlan] = useState<PlanRozmowy | null>(null);
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
        .then(setPlan)
        .catch(() => setPlan(null));
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
  const lista = kroki(dane, plan);
  // Pytania przy wskaźniku: pierwsze na wierzchu, dopytania (standard, powtarzalność) pod „Dopytaj”.
  const pytaniaWskaznika = (id: string) => (plan?.pytania ?? []).filter((q) => q.powiazanie.wskaznik_id === id).map((q) => q.tresc);
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

  const pierwszyWskaznik = (i: number) => lista.findIndex((x) => x.typ === "wskaznik" && x.kr === i);

  let ekran;
  if (k.typ === "wskaznik") {
    const kr = dane.kryteria[k.kr];
    const w = kr.wskazniki[k.w];
    ekran = (
      <>
        <EkranWskaznika
          key={w.wskaznik_id}
          kr={kr}
          w={w}
          nr={k.w + 1}
          pytania={pytaniaWskaznika(w.wskaznik_id)}
          zadania={zadania[w.wskaznik_id] ?? []}
          tylkoOdczyt={tylkoOdczyt}
          czekam={czekam === w.wskaznik_id}
          blad={bledy[w.wskaznik_id]}
          onZapisz={(o) => zapiszWskaznik(w.wskaznik_id, o)}
        />
      </>
    );
  } else if (k.typ === "temat") {
    ekran = <EkranTematu key={k.temat} temat={k.temat} plan={plan} token={token} procesId={proces.id} tylkoOdczyt={tylkoOdczyt} />;
  } else {
    ekran = (
      <div className="oc-ekran">
        <h2 className="oc-tytul" tabIndex={-1}>
          Podsumowanie i punkty
        </h2>
        <p className="meta">
          Po rozmowie przyznaj punkty za każde kryterium (§ 11 ust. 1 pkt 1 rozporządzenia), biorąc pod uwagę jej wnioski (§ 11 ust. 2).
          Pod każdym kryterium widzisz poziomy z rozmowy i sugestię.
        </p>
        {dane.kryteria.map((kr, i) => {
          const p = poprzednie?.punkty[kr.kompetencja_id];
          return (
            <OcenaKryterium
              key={kr.kompetencja_id}
              kr={kr}
              skala={dane.skala}
              poprzednio={p !== undefined && poprzednie ? { punkty: p, data: poprzednie.data } : null}
              tylkoOdczyt={tylkoOdczyt}
              czekam={czekam === kr.kompetencja_id}
              blad={bledy[kr.kompetencja_id]}
              onZapisz={(d) => zapiszDecyzje1(kr.kompetencja_id, d)}
              onWskazniki={() => setKrok(pierwszyWskaznik(i))}
            />
          );
        })}
        <p className="meta">
          {kp.kryteria_z_decyzja === kp.kryteria
            ? "Wszystkie kryteria mają punkty. Dalej zobaczysz wynik, średnią i arkusz."
            : `Punkty przyznane: ${kp.kryteria_z_decyzja} z ${kp.kryteria} kryteriów.`}
        </p>
        {dane.samoocena_status === "przekazana" && <AgendaRozbieznosci stan={dane} />}
      </div>
    );
  }

  const nastepny = lista[biezacy + 1];

  return (
    <div className="k2 oc">
      <div className="k2-naglowek">
        <button type="button" className="link" onClick={onWstecz}>
          Zobacz kryteria (część I)
        </button>
        <p className="meta">Zakończenie oceny</p>
        <h1>Rozmowa oceniająca</h1>
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
          {k.typ !== "podsumowanie" && (
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
              Dalej: ocena na piśmie
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
