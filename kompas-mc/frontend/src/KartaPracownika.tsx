import { useEffect, useState, type ReactNode } from "react";
import {
  pobierzCykl,
  pobierzKrok1,
  pobierzMapeKompetencji,
  pobierzNotatki,
  pobierzOcene,
  pobierzPracownikow,
  pobierzProcesy,
  pobierzSamoocene,
  pobierzTerminy,
  type AnalizaKroku1,
  type EtapOsoby,
  type MapaKompetencji,
  type Notatka,
  type Pracownik,
  type ProcesOceny,
  type Samoocena,
  type StanOceny,
  type TerminProcesu,
} from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { SzkieletListy, WierszListy } from "./Lista";
import { OcenyCzastkowe } from "./Kompetencje";
import { OpisOsoby } from "./OpisOsoby";
import { data, kiedy, lat, lataStazu, podzial } from "./zespol-dane";
import "./widoki.css";

/**
 * Karta pracownika (przed krokiem 1): kim jest, jak idzie ocena, co dalej. Dane z QNT (kadry), z analizy
 * opisu stanowiska (krok 1), z procesu i jego terminu, z ocen kryteriów i z notatek przełożonego.
 * Każda sekcja pojawia się tylko, gdy API ma dla niej dane; jedyny przycisk główny jest w „Następny krok”.
 */

/** Trzy etapy cyklu z rozporządzeń (rada UX 21.11): kolejność = indeks etapu z /api/cykl. */
const ETAPY_CYKLU: Record<"okresowa" | "pierwsza", [string, string, string]> = {
  okresowa: ["Ustalenie kryteriów", "Okres oceny", "Ocena: rozmowa i arkusz"],
  pierwsza: ["Rozmowa wstępna", "Okres przed pierwszą oceną", "Pierwsza ocena"],
};
const PODPOWIEDZI_PIERWSZA = [
  "Kiedy przeprowadza się rozmowę wstępną?",
  "Kto sporządza pierwszą ocenę?",
  "Co się dzieje po negatywnej pierwszej ocenie?",
];
const INDEKS_ETAPU: Record<EtapOsoby["etap"], number> = { kryteria: 0, okres: 1, ocena: 2, brak_danych: -1 };

const PODPOWIEDZI: Record<EtapOsoby["etap"], string[]> = {
  kryteria: ["Jak ustalić kryteria oceny okresowej?", "Ile kryteriów dodatkowych można wybrać?", "Kiedy przeprowadza się rozmowę wstępną?"],
  okres: ["Co zrobić, gdy zmienia się oceniający?", "Kiedy można przesunąć termin oceny?", "Jak dokumentować przykłady zachowań?"],
  ocena: ["Co omawia się na rozmowie oceniającej?", "Kiedy ocena okresowa jest negatywna?", "Ile dni ma pracownik na sprzeciw od oceny okresowej?"],
  brak_danych: ["Kto podlega ocenie okresowej?", "Kto podlega pierwszej ocenie?", "Co zrobić, gdy brakuje danych kadrowych?"],
};

interface Dane {
  analiza: AnalizaKroku1 | null;
  proces: ProcesOceny | null;
  termin: TerminProcesu | null;
  ocena: StanOceny | null;
  /** Własna samoocena (konto pracownika); dla innych ról null. */
  samoocena: Samoocena | null;
  notatki: Notatka[];
  przelozony: Pracownik | null;
  /** Etap cyklu i następna czynność z /api/cykl (#23). */
  cykl: EtapOsoby | null;
  /** Mapa kompetencji (#33): tylko przełożony; oceny cząstkowe ostatniej oceny z akt. */
  mapa: MapaKompetencji | null;
}

export function KartaPracownika({
  sesja,
  osoba,
  onWroc,
  onOcen,
  onSamoocena,
  onZapytaj,
  onWyloguj,
  cele,
}: {
  sesja: Sesja;
  osoba: Pracownik;
  onWroc: () => void;
  /** Proces w toku (#49): App otwiera jego bieżący krok; null = krok 1; "krok2" = kryteria procesu (etap na karcie, #55). */
  onOcen: (proces: ProcesOceny | null, etap?: "krok2") => void;
  /** Pracownik otwiera „Moją samoocenę” procesu (#9). */
  onSamoocena?: (procesId: number) => void;
  /** Sekcja celów rozwojowych osoby (#11, komponent z gałęzi celów); bez niej sekcji nie ma. */
  cele?: ReactNode;
  onZapytaj: (pytanie: string) => void;
  onWyloguj: () => void;
}) {
  const [dane, setDane] = useState<Dane | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const token = sesja.token;
  const prowadzi = sesja.uzytkownik.rola === "przelozony";

  useEffect(() => {
    let aktualne = true;
    (async () => {
      try {
        const [analiza, procesy, terminy, ludzie, notatki, cykl] = await Promise.all([
          pobierzKrok1(token, osoba.osoba_id).catch(() => null),
          pobierzProcesy(token),
          pobierzTerminy(token).catch(() => []),
          pobierzPracownikow(token),
          // Notatki widzi tylko przełożony; HR i oceniany nie pytają (API dałoby 403).
          prowadzi ? pobierzNotatki(token, osoba.osoba_id).catch(() => []) : Promise.resolve([] as Notatka[]),
          pobierzCykl(token).catch(() => []),
        ]);
        const mapa = prowadzi ? await pobierzMapeKompetencji(token).catch(() => null) : null;
        const wlasne = procesy.filter((p) => p.osoba_id === osoba.osoba_id);
        const proces = wlasne.find((p) => p.status === "W_TOKU") ?? wlasne[wlasne.length - 1] ?? null;
        // Ocena kryteriów istnieje dopiero po zapisaniu kroku 2.
        const ocena = proces ? await pobierzOcene(token, proces.id).catch(() => null) : null;
        // Samoocena: tylko konto pracownika (własny proces); przed krokiem 2 API zwraca 409.
        const samoocena =
          proces && sesja.uzytkownik.rola === "oceniany" ? await pobierzSamoocene(token, proces.id).catch(() => null) : null;
        if (!aktualne) return;
        setDane({
          analiza,
          proces,
          termin: (proces && terminy.find((t) => t.proces_id === proces.id)) || null,
          ocena,
          notatki,
          przelozony: ludzie.find((p) => p.osoba_id === osoba.przelozony_id) ?? null,
          samoocena,
          cykl: cykl.find((c) => c.osoba_id === osoba.osoba_id) ?? null,
          mapa,
        });
      } catch (err) {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać danych pracownika.");
      }
    })();
    return () => {
      aktualne = false;
    };
  }, [token, osoba, onWyloguj]);

  const { wydzial, departament } = podzial(osoba.komorka);
  const staz = lataStazu(osoba.data_zatrudnienia);
  const przelozonyTo =
    osoba.przelozony_id === sesja.uzytkownik.osoba_id
      ? "Ty"
      : dane?.przelozony
        ? `${dane.przelozony.imie} ${dane.przelozony.nazwisko}`
        : null;
  const wToku = dane?.proces?.status === "W_TOKU" ? dane.proces : null;
  /** Etap cyklu (#55): ocena → bieżący krok procesu (#49), kryteria i okres → krok 2, bez procesu → krok 1. */
  const otworzEtap = (i: number) => (i === 2 || !wToku ? onOcen(wToku) : onOcen(wToku, "krok2"));

  return (
    <div className="widok karta">
      <button type="button" className="link wstecz" onClick={onWroc}>
        <Ikona nazwa="wstecz" rozmiar={20} />
        Wróć
      </button>

      <div className="karta-glowa">
        <span className="inicjaly duze" aria-hidden="true">
          {osoba.imie.charAt(0)}
          {osoba.nazwisko.charAt(0)}
        </span>
        <div>
          <h1>
            {osoba.imie} {osoba.nazwisko}
          </h1>
          <p className="opis">
            {osoba.stanowisko} · {wydzial}
          </p>
          <OpisOsoby sesja={sesja} osoba={osoba} />
        </div>
      </div>

      {blad && <p className="blad">{blad}</p>}
      {!blad && !dane && <SzkieletListy wiersze={3} />}

      {dane && (
        <div className="dwie">
          <div className="sekcje-karty">
            <Cykl
              dane={dane}
              osoba={osoba}
              sciezka={dane.cykl?.sciezka ?? dane.proces?.sciezka ?? dane.analiza?.sciezka.proponowana ?? null}
              onEtap={prowadzi ? otworzEtap : undefined}
              wToku={wToku !== null}
            />
            {cele}
            <WynikiKryteriow ocena={dane.ocena} />

            {dane.analiza?.osp && <OpisStanowiska osp={dane.analiza.osp} />}

            {dane.notatki.length > 0 && (
              <div className="sekcja">
                <h2>Notatki przełożonego</h2>
                <ul className="notatki">
                  {dane.notatki.map((n) => (
                    <li key={n.id}>
                      <span className="meta">
                        {data(n.czas)} · {n.autor}
                      </span>
                      <p>{n.tresc}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <aside className="bok-karty">
            {dane.samoocena && onSamoocena ? (
              <NastepnySamoocena s={dane.samoocena} onOtworz={() => onSamoocena(dane.samoocena!.proces_id)} />
            ) : (
              <NastepnyKrok
                dane={dane}
                prowadzi={prowadzi}
                onOcen={() => onOcen(wToku)}
                przelozony={dane.przelozony}
              />
            )}

            <div className="sekcja">
              <h2>Dane kadrowe</h2>
              <dl className="dane-kadrowe">
                <dt>Zatrudnienie</dt>
                <dd>
                  od {data(osoba.data_zatrudnienia)}, na czas {osoba.rodzaj_umowy === "nieokreslony" ? "nieokreślony" : "określony"}
                  {osoba.data_konca_zatrudnienia && <>, do {data(osoba.data_konca_zatrudnienia)}</>}
                </dd>
                <dt>Staż</dt>
                <dd>{staz < 1 ? "poniżej roku" : lat(staz)}</dd>
                <dt>Korpus służby cywilnej</dt>
                <dd>{osoba.korpus === "urzednik_sc" ? "urzędnik" : "pracownik"}</dd>
                <dt>Komórka</dt>
                <dd>
                  {wydzial}
                  <br />
                  <span className="meta">{departament}</span>
                </dd>
                {przelozonyTo && (
                  <>
                    <dt>Przełożony</dt>
                    <dd>{przelozonyTo}</dd>
                  </>
                )}
                <dt>Kieruje pracownikami</dt>
                <dd>{osoba.kieruje_pracownikami ? "tak" : "nie"}</dd>
                {osoba.zmiana_oceniajacego && (
                  <>
                    <dt>Zmiana oceniającego</dt>
                    <dd>{data(osoba.zmiana_oceniajacego.data)}</dd>
                  </>
                )}
                {osoba.absolwent_ksap && (
                  <>
                    <dt>Absolwent KSAP</dt>
                    <dd>tak{osoba.wniosek_o_mianowanie ? ", z wnioskiem o mianowanie" : ""}</dd>
                  </>
                )}
                {osoba.zastepstwo && (
                  <>
                    <dt>Zastępstwo</dt>
                    <dd>tak</dd>
                  </>
                )}
                {(osoba.nieobecnosci?.length ?? 0) > 0 && (
                  <>
                    <dt>Nieobecności</dt>
                    <dd>
                      {osoba.nieobecnosci!.map((n) => (
                        <span key={n.od} className="blok">
                          {n.rodzaj}: {data(n.od)}–{data(n.do)}
                        </span>
                      ))}
                    </dd>
                  </>
                )}
              </dl>
              <p className="meta zero">Źródło: kartoteka QNT</p>
            </div>

            <div className="sekcja">
              <h2>Zapytaj asystenta</h2>
              <div className="lista ciasna">
                {((dane.cykl?.sciezka ?? dane.proces?.sciezka) === "pierwsza"
                  ? PODPOWIEDZI_PIERWSZA
                  : PODPOWIEDZI[dane.cykl?.etap ?? "ocena"]
                ).map((q) => (
                  <WierszListy key={q} maly lewa={<Ikona nazwa="pytanie" />} tytul={q} onClick={() => onZapytaj(q)} />
                ))}
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

/**
 * Cykl oceny w trzech etapach z rozporządzeń i zdanie „Teraz: … do … · Potem: …” (rada UX 21.11).
 * Etap i termin podaje /api/cykl; front nic nie liczy. Przełożony klika etap zrobiony albo bieżący i przechodzi
 * do jego kroku (#55). Pod etapami poprzednie oceny z akt, bo są częścią tej samej oceny (Karol 21.11).
 */
function Cykl({
  dane,
  osoba,
  sciezka,
  onEtap,
  wToku,
}: {
  dane: Dane;
  osoba: Pracownik;
  sciezka: "okresowa" | "pierwsza" | null;
  onEtap?: (i: number) => void;
  /** Proces w toku w aplikacji; bez niego klikalny jest tylko bieżący etap, który zaczyna ocenę. */
  wToku: boolean;
}) {
  const c = dane.cykl;
  const etapy = ETAPY_CYKLU[sciezka ?? "okresowa"];
  const biezacy = c ? INDEKS_ETAPU[c.etap] : -1;
  const arkusz = sciezka !== "pierwsza" ? dane.analiza?.arkusz_okresowy : null;
  return (
    <div className="sekcja cykl">
      <h2>
        {sciezka === "pierwsza" ? "Pierwsza ocena" : "Ocena okresowa"}
        {/* Arkusz jako dopisek (Karol 21.11: „aż takie duże?”); uzasadnienie z przepisem jest w kroku 1. */}
        {arkusz?.arkusz && <span className="arkusz-dopisek"> · arkusz {arkusz.arkusz}</span>}
      </h2>
      {c && (
        <p className={`teraz ${c.po_terminie ? "po-terminie" : ""}`}>
          <strong>Teraz:</strong> {c.czynnosc}
          {c.termin && (
            <>
              {" "}
              do {data(c.termin.data)} ({c.dni_do_terminu !== null ? kiedy(c.dni_do_terminu) : ""})
            </>
          )}
          {biezacy >= 0 && biezacy < 2 && (
            <>
              {" "}
              · <strong>Potem:</strong> {etapy[biezacy + 1].toLowerCase()}
            </>
          )}
        </p>
      )}
      {/* Braki dat w kartotece to język przepisów; przełożonemu wystarczy jedna linia, szczegóły po rozwinięciu. */}
      {c && c.braki.length > 0 && (
        <details className="braki-karty">
          <summary>
            W kartotece QNT brakuje {c.braki.length === 1 ? "jednej daty" : `${c.braki.length} dat`}, więc termin może być
            niepełny
          </summary>
          <ul>
            {c.braki.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </details>
      )}
      {c && biezacy >= 0 && (
        <ol className="etapy">
          {etapy.map((nazwa, i) => {
            const stan = i < biezacy ? "zrobiony" : i === biezacy ? "biezacy" : "przyszly";
            const opis =
              stan === "zrobiony"
                ? i === 0 && c.kryteria_ustalone
                  ? `ustalone ${data(c.kryteria_ustalone)}`
                  : "zrobione"
                : stan === "biezacy"
                  ? c.termin
                    ? `do ${data(c.termin.data)}`
                    : "teraz"
                  : "";
            // Bez oceny w aplikacji etap „zrobione” nie ma czego pokazać, a okres oceny nie zaczyna oceny
            // (Następny krok mówi „zaczniesz bliżej terminu”); klik nie może otwierać nowej oceny.
            const klik = onEtap && stan !== "przyszly" && (wToku || (stan === "biezacy" && c.etap !== "okres"));
            const tresc = (
              <>
                <span className={`znak-etapu ${stan}`} aria-hidden="true">
                  {stan === "zrobiony" ? <Ikona nazwa="ok" rozmiar={16} /> : i + 1}
                </span>
                <span className="nazwa-etapu">{nazwa}</span>
                <span className="meta">{opis}</span>
                {klik && <Ikona nazwa="dalej" rozmiar={20} />}
              </>
            );
            return (
              <li key={nazwa} className={stan} aria-current={stan === "biezacy" ? "step" : undefined}>
                {klik ? (
                  <button type="button" className="etap" onClick={() => onEtap!(i)}>
                    {tresc}
                  </button>
                ) : (
                  <div className="etap">{tresc}</div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <LiniaSamooceny ocena={dane.ocena} />
      <PoprzednieOceny osoba={osoba} mapa={dane.mapa} pierwsza={sciezka === "pierwsza"} />
    </div>
  );
}

/**
 * Poprzednie oceny z kartoteki QNT; oceny cząstkowe ostatniej okresowej tylko dla przełożonego (mapa).
 * Na ścieżce pierwszej oceny rekord `pierwsza_ocena` opisuje bieżącą służbę przygotowawczą, nie poprzednią ocenę.
 */
function PoprzednieOceny({ osoba, mapa, pierwsza }: { osoba: Pracownik; mapa: MapaKompetencji | null; pierwsza: boolean }) {
  const o = osoba.ostatnia_ocena_okresowa;
  const p = pierwsza ? null : osoba.pierwsza_ocena;
  return (
    <div className="poprzednie">
      <span className="kafel-etykieta">Poprzednie oceny</span>
      {o && (
        <p className="zero">
          Ocena okresowa <span className={`status ${o.wynik}`}>{o.wynik}</span>{" "}
          <span className="meta">sporządzona {data(o.data)}</span>
        </p>
      )}
      {o && <OcenyCzastkowe mapa={mapa} osoba={osoba} bezNaglowka />}
      {p && (
        <p className="zero">
          Pierwsza ocena{" "}
          <span className="meta">
            {p.egzamin_sluzba_przygotowawcza === "zaliczony"
              ? "egzamin ze służby przygotowawczej zaliczony"
              : p.egzamin_sluzba_przygotowawcza === "brak"
                ? "egzamin ze służby przygotowawczej jeszcze niezdany"
                : "służba przygotowawcza nie dotyczy"}
          </span>
        </p>
      )}
      {!o && !p && (
        <p className="meta zero">
          {pierwsza ? "To pierwsza ocena, wcześniejszych nie ma." : "W kartotece QNT nie ma jeszcze żadnej oceny."}
        </p>
      )}
      <p className="meta zero">Źródło: kartoteka QNT</p>
    </div>
  );
}

/** Opis stanowiska widoczny, ale skrócony: cel i zadania dominujące w 2 liniach; reszta po „Cały opis stanowiska”. */
function OpisStanowiska({ osp }: { osp: NonNullable<AnalizaKroku1["osp"]> }) {
  const [caly, setCaly] = useState(false);
  return (
    <div className={`sekcja opis-stanowiska${caly ? "" : " skrocone"}`}>
      <h2>Opis stanowiska</h2>
      <p className="meta zero">
        Opis stanowiska pracy z kadr · {osp.zadania_dominujace.length} zadania dominujące
      </p>
      <span className="kafel-etykieta">Cel stanowiska</span>
      <p className="zero cel-stanowiska">{osp.cel.tekst}</p>
      <span className="kafel-etykieta">Zadania dominujące</span>
      <ol className="zadania-karty">
        {osp.zadania_dominujace.map((z) => (
          <li key={z.nr}>
            <span className="tekst-zadania">{z.tekst}</span>
          </li>
        ))}
      </ol>
      {caly && osp.kompetencje_miekkie.lista.length > 0 && (
        <>
          <span className="kafel-etykieta">Kompetencje miękkie z opisu</span>
          <div className="etykiety">
            {osp.kompetencje_miekkie.lista.map((k) => (
              <span key={k} className="znacznik">
                {k}
              </span>
            ))}
          </div>
        </>
      )}
      <button type="button" className="link" aria-expanded={caly} onClick={() => setCaly(!caly)}>
        {caly ? "Zwiń opis stanowiska" : "Cały opis stanowiska"}
      </button>
    </div>
  );
}

/** Przycisk nazwany czynnością według etapu (#25): w okresie oceny bez przycisku oceny. */
function NastepnyKrok({
  dane,
  prowadzi,
  onOcen,
  przelozony,
}: {
  dane: Dane;
  prowadzi: boolean;
  onOcen: () => void;
  przelozony: Pracownik | null;
}) {
  const c = dane.cykl;
  const p = dane.proces;
  const tytul = c?.czynnosc ?? (p ? `Ocena w toku · krok ${p.krok}` : "Ustal ścieżkę oceny");
  const przycisk = !c
    ? p
      ? "Kontynuuj ocenę"
      : "Rozpocznij ocenę"
    : c.etap === "kryteria"
      ? p
        ? "Dokończ ustalanie kryteriów"
        : c.sciezka === "pierwsza"
          ? "Rozpocznij pierwszą ocenę"
          : "Ustal kryteria"
      : c.etap === "ocena"
        ? p && p.krok >= 6
          ? "Sporządź ocenę na piśmie"
          : "Oceń kompetencje"
        : null;
  return (
    <div className="ramka nastepny">
      <span className="kafel-etykieta">Następny krok</span>
      <strong>{tytul}</strong>
      {c?.termin && (
        <span className={c.po_terminie ? "termin zagrozony" : "termin"}>
          {c.termin.nazwa} do {data(c.termin.data)}
          {c.dni_do_terminu !== null && <> ({kiedy(c.dni_do_terminu)})</>}
        </span>
      )}
      {c?.etap === "okres" && <span className="termin">Kryteria ustalone. Ocenę końcową zaczniesz bliżej terminu.</span>}
      {prowadzi && przycisk && (
        <button type="button" onClick={onOcen}>
          {przycisk}
        </button>
      )}
      {!prowadzi && (
        <span className="termin">
          Prowadzi przełożony{przelozony ? `: ${przelozony.imie} ${przelozony.nazwisko}` : ""}.
        </span>
      )}
      {!prowadzi && p && (
        <button type="button" className="jasny" onClick={onOcen}>
          Zobacz ocenę
        </button>
      )}
    </div>
  );
}

/** Konto pracownika: zamiast „Następnego kroku” procesu — własna samoocena (#9). */
function NastepnySamoocena({ s, onOtworz }: { s: Samoocena; onOtworz: () => void }) {
  const tytul =
    s.status === "przekazana"
      ? `Samoocena przekazana ${s.przekazano ? data(s.przekazano) : ""}`
      : s.status === "szkic"
        ? `Samoocena: odpowiedzi ${s.wypelniono} z ${s.wybrano}`
        : "Wypełnij samoocenę";
  return (
    <div className="ramka nastepny">
      <span className="kafel-etykieta">Następny krok</span>
      <strong>{tytul}</strong>
      <span className="termin">Samoocena nie zmienia oceny. Przełożony omówi ją z Tobą na rozmowie.</span>
      <button type="button" onClick={onOtworz}>
        {s.status === "przekazana" ? "Zobacz samoocenę" : s.status === "szkic" ? "Dokończ samoocenę" : "Rozpocznij samoocenę"}
      </button>
    </div>
  );
}

/** Przełożony: status samooceny i rozbieżności (≥ 4 pkt) z podstawą; HR i pracownik nie dostają tych pól. */
function LiniaSamooceny({ ocena }: { ocena: StanOceny | null }) {
  const st = ocena?.samoocena_status;
  if (!ocena || !st) return null;
  if (st !== "przekazana")
    return <p className="meta zero">Samoocena pracownika: {st === "szkic" ? "w przygotowaniu" : "nierozpoczęta"}.</p>;
  const w = ocena.kryteria.flatMap((k) => k.wskazniki);
  const porownane = w.filter((x) => x.rozbieznosc !== null && x.rozbieznosc !== undefined).length;
  const rozbiezne = w.filter((x) => x.rozbieznosc).length;
  return (
    <p className="meta zero">
      Samoocena przekazana · do omówienia {rozbiezne} z {porownane} porównanych wskaźników (różnica co najmniej 4 pkt)
    </p>
  );
}

/** Punkty kryteriów po decyzji przełożonego, na skali arkusza. Bez decyzji sekcji nie ma. */
function WynikiKryteriow({ ocena }: { ocena: StanOceny | null }) {
  const z = ocena?.kryteria.filter((k) => k.decyzja) ?? [];
  if (!ocena || z.length === 0) return null;
  const max = Math.max(...ocena.skala.punkty);
  return (
    <div className="sekcja">
      <h2>Oceny kryteriów</h2>
      <p className="meta zero">
        Decyzje przełożonego, skala 1–{max} pkt · {z.length} z {ocena.kryteria.length} kryteriów
      </p>
      <ul className="slupki">
        {z.map((k) => (
          <li key={k.kompetencja_id}>
            <span className="nazwa-slupka">{k.nazwa}</span>
            <span className="tor" title={`${k.nazwa}: ${k.decyzja!.punkty} z ${max} pkt`}>
              <span className="wypelnienie" style={{ width: `${(k.decyzja!.punkty / max) * 100}%` }} />
            </span>
            <strong className="wartosc-slupka">{k.decyzja!.punkty}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
