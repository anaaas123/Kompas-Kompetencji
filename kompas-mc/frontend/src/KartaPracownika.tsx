import { useEffect, useState } from "react";
import {
  pobierzKrok1,
  pobierzNotatki,
  pobierzOcene,
  pobierzPracownikow,
  pobierzProcesy,
  pobierzSamoocene,
  pobierzTerminy,
  type AnalizaKroku1,
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
import { PostepKrokow } from "./Wykresy";
import { data, kiedy, lat, lataStazu, stazTekst, NAZWA_SCIEZKI, podzial } from "./zespol-dane";
import "./widoki.css";

/**
 * Karta pracownika (przed krokiem 1): kim jest, jak idzie ocena, co dalej. Dane z QNT (kadry), z analizy
 * opisu stanowiska (krok 1), z procesu i jego terminu, z ocen kryteriów i z notatek przełożonego.
 * Każda sekcja pojawia się tylko, gdy API ma dla niej dane; jedyny przycisk główny jest w „Następny krok”.
 */

/** Etapy procesu jak w nagłówkach kroków (Krok N z 8). */
const ETAPY: [number, number, string][] = [
  [1, 1, "Analiza opisu stanowiska"],
  [2, 2, "Kryteria i wskaźniki"],
  [3, 5, "Ocena kryteriów"],
  [6, 6, "Rozmowa oceniająca"],
  [7, 7, "Wynik, terminy i arkusz"],
  [8, 8, "Wnioski rozwojowe"],
];
const KROKOW = 8;

const PODPOWIEDZI: Record<string, string[]> = {
  okresowa: [
    "Co omawia się na rozmowie oceniającej?",
    "Kiedy ocena okresowa jest negatywna?",
    "Ile kryteriów dodatkowych można wybrać?",
  ],
  pierwsza: [
    "Kiedy przeprowadza się rozmowę wstępną?",
    "Kto sporządza pierwszą ocenę?",
    "Co się dzieje po negatywnej pierwszej ocenie?",
  ],
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
}

export function KartaPracownika({
  sesja,
  osoba,
  onWroc,
  onOcen,
  onSamoocena,
  onZapytaj,
  onWyloguj,
}: {
  sesja: Sesja;
  osoba: Pracownik;
  onWroc: () => void;
  onOcen: () => void;
  /** Pracownik otwiera „Moją samoocenę” procesu (#9). */
  onSamoocena?: (procesId: number) => void;
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
        const [analiza, procesy, terminy, ludzie, notatki] = await Promise.all([
          pobierzKrok1(token, osoba.osoba_id).catch(() => null),
          pobierzProcesy(token),
          pobierzTerminy(token).catch(() => []),
          pobierzPracownikow(token),
          // Notatki widzi tylko przełożony; HR i oceniany dostają 403.
          pobierzNotatki(token, osoba.osoba_id).catch(() => []),
        ]);
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
  const rokOd = osoba.data_zatrudnienia.slice(0, 4);
  const przelozonyTo =
    osoba.przelozony_id === sesja.uzytkownik.osoba_id
      ? "Ty"
      : dane?.przelozony
        ? `${dane.przelozony.imie} ${dane.przelozony.nazwisko}`
        : osoba.przelozony_id;

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
        </div>
      </div>

      {blad && <p className="blad">{blad}</p>}
      {!blad && !dane && <SzkieletListy wiersze={3} />}

      {dane && (
        <div className="dwie">
          <div className="sekcje-karty">
            <p className="streszczenie">
              {osoba.stanowisko.charAt(0).toUpperCase() + osoba.stanowisko.slice(1)} od {rokOd} r. ({stazTekst(staz)}),{" "}
              {osoba.korpus === "urzednik_sc" ? "urzędnik" : "pracownik"} służby cywilnej, umowa na czas{" "}
              {osoba.rodzaj_umowy === "nieokreslony" ? "nieokreślony" : "określony"}.{" "}
              {osoba.kieruje_pracownikami ? "Kieruje zespołem." : "Nie kieruje zespołem."}
              {dane.analiza?.osp && <> {dane.analiza.osp.cel.tekst}</>}
            </p>

            <Proces dane={dane} onOcen={onOcen} />
            <WynikiKryteriow ocena={dane.ocena} />

            <div className="sekcja">
              <h2>Poprzednie oceny</h2>
              <div className="lista">
                {osoba.ostatnia_ocena_okresowa && (
                  <WierszListy
                    lewa={<Ikona nazwa="dokument" />}
                    tytul="Ocena okresowa"
                    znacznik={
                      <span className={`status ${osoba.ostatnia_ocena_okresowa.wynik}`}>
                        {osoba.ostatnia_ocena_okresowa.wynik}
                      </span>
                    }
                    opis={`sporządzona ${data(osoba.ostatnia_ocena_okresowa.data)}`}
                  />
                )}
                {osoba.pierwsza_ocena && (
                  <WierszListy
                    lewa={<Ikona nazwa="dokument" />}
                    tytul="Pierwsza ocena"
                    opis={
                      osoba.pierwsza_ocena.egzamin_sluzba_przygotowawcza === "zaliczony"
                        ? "egzamin ze służby przygotowawczej zaliczony"
                        : osoba.pierwsza_ocena.egzamin_sluzba_przygotowawcza === "brak"
                          ? "egzamin ze służby przygotowawczej jeszcze niezdany"
                          : "służba przygotowawcza nie dotyczy"
                    }
                  />
                )}
                {!osoba.ostatnia_ocena_okresowa && !osoba.pierwsza_ocena && (
                  <p className="meta">W kartotece QNT nie ma jeszcze żadnej oceny.</p>
                )}
              </div>
            </div>

            {dane.analiza?.osp && (
              <div className="sekcja">
                <h2>Opis stanowiska</h2>
                <p className="meta zero">
                  OSP {dane.analiza.osp.symbol} · {departament}
                </p>
                <span className="kafel-etykieta">Zadania dominujące</span>
                <ol className="zadania-karty">
                  {dane.analiza.osp.zadania_dominujace.map((z) => (
                    <li key={z.nr}>{z.tekst}</li>
                  ))}
                </ol>
                {dane.analiza.osp.kompetencje_miekkie.lista.length > 0 && (
                  <>
                    <span className="kafel-etykieta">Kompetencje miękkie z opisu</span>
                    <div className="etykiety">
                      {dane.analiza.osp.kompetencje_miekkie.lista.map((k) => (
                        <span key={k} className="znacznik">
                          {k}
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

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
              <NastepnyKrok dane={dane} prowadzi={prowadzi} onOcen={onOcen} />
            )}

            {dane.analiza?.arkusz_okresowy.arkusz && (
              <div className="ramka">
                <span className="kafel-etykieta">Arkusz oceny</span>
                <strong>Arkusz {dane.analiza.arkusz_okresowy.arkusz}</strong>
                <p className="meta zero">{dane.analiza.arkusz_okresowy.uzasadnienie}</p>
              </div>
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
                <dt>Przełożony</dt>
                <dd>{przelozonyTo}</dd>
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
                {(PODPOWIEDZI[dane.proces?.sciezka ?? dane.analiza?.sciezka.proponowana ?? "okresowa"] ?? []).map((q) => (
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

function Proces({ dane, onOcen }: { dane: Dane; onOcen: () => void }) {
  const p = dane.proces;
  if (!p) return null;
  const t = dane.termin;
  return (
    <div className="sekcja">
      <div className="wiersz-tytulu">
        <h2>
          {NAZWA_SCIEZKI[p.sciezka].charAt(0).toUpperCase() + NAZWA_SCIEZKI[p.sciezka].slice(1)}
          {p.arkusz !== "PIERWSZA" && <> · arkusz {p.arkusz}</>}
        </h2>
        <span className={`status ${p.status === "W_TOKU" ? "uwaga" : "neutralna"}`}>
          {p.status === "W_TOKU" ? "w toku" : p.status.toLowerCase()}
        </span>
      </div>
      <PostepKrokow krok={p.krok} krokow={KROKOW} etykieta="Postęp oceny" />
      <LiniaSamooceny ocena={dane.ocena} />
      <p className="meta zero">
        Krok {p.krok} z {KROKOW} · rozpoczęta {data(p.rozpoczeto)} przez {p.rozpoczal}
        {t?.najblizszy_termin && (
          <>
            {" "}
            · {t.najblizszy_termin.nazwa} do {data(t.najblizszy_termin.data)} ({kiedy(t.dni_do_terminu!)})
          </>
        )}
      </p>
      <ol className="etapy">
        {ETAPY.map(([od, do_, nazwa]) => {
          const stan = p.krok > do_ ? "zrobiony" : p.krok >= od ? "biezacy" : "przyszly";
          const tresc = (
            <>
              <span className={`znak-etapu ${stan}`} aria-hidden="true">
                {stan === "zrobiony" ? <Ikona nazwa="ok" rozmiar={16} /> : od}
              </span>
              <span className="nazwa-etapu">{nazwa}</span>
              <span className="meta">{stan === "zrobiony" ? "zrobione" : stan === "biezacy" ? "teraz" : ""}</span>
            </>
          );
          return (
            <li key={nazwa} className={stan}>
              {stan === "biezacy" && p.status === "W_TOKU" ? (
                <button type="button" className="etap" onClick={onOcen}>
                  {tresc}
                  <Ikona nazwa="dalej" rozmiar={20} />
                </button>
              ) : (
                <div className="etap">{tresc}</div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function NastepnyKrok({ dane, prowadzi, onOcen }: { dane: Dane; prowadzi: boolean; onOcen: () => void }) {
  const p = dane.proces;
  const etap = p && ETAPY.find(([od, do_]) => p.krok >= od && p.krok <= do_);
  const proponowana = dane.analiza?.sciezka.proponowana ?? null;
  const tytul = p
    ? p.status === "W_TOKU"
      ? etap?.[2] ?? `Krok ${p.krok}`
      : "Ocena zakończona"
    : proponowana
      ? `Rozpocznij ${NAZWA_SCIEZKI[proponowana]}`
      : "Ustal ścieżkę oceny";
  const przycisk = !prowadzi ? "Zobacz ocenę" : p && p.status === "W_TOKU" ? "Kontynuuj ocenę" : "Rozpocznij ocenę";
  return (
    <div className="ramka nastepny">
      <span className="kafel-etykieta">Następny krok</span>
      <strong>{tytul}</strong>
      {dane.termin?.najblizszy_termin && (
        <span className={dane.termin.zagrozony ? "termin zagrozony" : "termin"}>
          {dane.termin.najblizszy_termin.nazwa} do {data(dane.termin.najblizszy_termin.data)} ({kiedy(dane.termin.dni_do_terminu!)})
        </span>
      )}
      <button type="button" onClick={onOcen}>
        {przycisk}
      </button>
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
