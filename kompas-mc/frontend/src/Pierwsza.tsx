import { useEffect, useState } from "react";
import {
  pobierzPdfPierwszej,
  pobierzPierwsza,
  zapiszPierwsza,
  type BrakArkusza,
  type DanePierwszej,
  type EgzaminPierwszej,
  type Pracownik,
  type ProcesOceny,
  type PrzedluzeniePierwszej,
  type PrzeslankaEgzaminu,
  type SladReguly,
  type SprawozdaniePierwszej,
  type StanPierwszejOceny,
  type Termin,
} from "./api";
import { Pole, bladArkusza } from "./Arkusz";
import { Zrodla } from "./Krok1";
import { Wybor } from "./Ocena";
import { PoleDaty, poprawnaData, zapiszPlik } from "./Wynik";

const data = (iso: string) => iso.split("-").reverse().join(".");

const NAZWY_TERMINOW: Record<string, string> = {
  termin_rozmowy_wstepnej: "Rozmowa wstępna (termin)",
  pierwsza_ocena_od: "Pierwsza ocena od",
  pierwsza_ocena_do: "Pierwsza ocena do",
  termin_sprawozdania_bazowy_od: "Sprawozdanie, okno bazowe od",
  termin_sprawozdania_bazowy_do: "Sprawozdanie, okno bazowe do",
  termin_sprawozdania_od: "Sprawozdanie od",
  termin_sprawozdania_do: "Sprawozdanie do",
};

const DATY: [keyof DanePierwszej, string][] = [
  ["data_rozmowy_wstepnej", "Rozmowa wstępna"],
  ["wyznaczony_termin_sprawozdania", "Wyznaczony termin sprawozdania (ostatni dzień)"],
  ["termin_sprawozdania_od", "Początek terminu sprawozdania, gdy inny niż domyślny"],
  ["data_zlozenia_sprawozdania", "Złożenie sprawozdania"],
  ["sprawozdanie_okres_od", "Sprawozdanie za okres od"],
  ["sprawozdanie_okres_do", "Sprawozdanie za okres do"],
  ["data_rozmowy_oceniajacej", "Rozmowa oceniająca"],
  ["data_sporzadzenia_oceny", "Sporządzenie oceny"],
  ["data_zapoznania_z_ocena", "Zapoznanie ocenianego z oceną"],
  ["data_konca_zatrudnienia", "Koniec umowy na czas określony"],
  ["data_ustalenia_oceny_zastepstwa", "Ustalenie pierwszej oceny przy zastępstwie"],
];

const SPRAWOZDANIE: [keyof SprawozdaniePierwszej, string][] = [
  ["zadania", "Zadania"],
  ["problemy_i_rozwiazania", "Problemy i rozwiązania"],
  ["nowe_umiejetnosci_i_wiedza", "Nowe umiejętności i wiedza"],
  ["propozycje_usprawnien", "Propozycje usprawnień"],
];

const EGZAMIN = [
  { wartosc: "tak", tekst: "zdany" },
  { wartosc: "nie", tekst: "niezdany" },
  { wartosc: "nie_dotyczy", tekst: "nie dotyczy" },
] as const;

const PRZESLANKI: Record<PrzeslankaEgzaminu, string> = {
  ksap_bez_wniosku: "absolwent KSAP bez wniosku o mianowanie",
  zastepstwo: "zatrudnienie na zastępstwo",
  wyzsze_stanowisko: "wyższe stanowisko w służbie cywilnej",
};

const PRZYCZYNY: Record<PrzedluzeniePierwszej["przyczyna"], string> = {
  usprawiedliwiona_nieobecnosc: "usprawiedliwiona nieobecność",
  obowiazki_poza_miejscem_pracy: "obowiązki poza miejscem pracy",
  przedluzenie_umowy: "przedłużenie umowy",
};

const PUSTE_SPRAWOZDANIE: SprawozdaniePierwszej = { zadania: "", problemy_i_rozwiazania: "", nowe_umiejetnosci_i_wiedza: "", propozycje_usprawnien: "" };

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

/** Wysyłamy komplet danych z GET; puste sprawozdanie idzie jako null, bo API wymaga wszystkich czterech pól. */
function doZapisu(d: DanePierwszej): DanePierwszej {
  const s = d.sprawozdanie;
  const pusteSprawozdanie = !s || Object.values(s).every((v) => !v.trim());
  return { ...d, sprawozdanie: d.sprawozdanie_niezlozone || pusteSprawozdanie ? null : s };
}

function Formularz({
  stan,
  token,
  osoba,
  edycja,
  onZapisano,
}: {
  stan: StanPierwszejOceny;
  token: string;
  osoba: Pracownik;
  edycja: boolean;
  onZapisano: (s: StanPierwszejOceny) => void;
}) {
  const [d, setD] = useState<DanePierwszej>({ ...stan.dane, egzamin: stan.dane.egzamin ?? stan.egzamin });
  const [braki, setBraki] = useState<BrakArkusza[]>(stan.formularz.braki);
  const [czekam, setCzekam] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const ustaw = (z: Partial<DanePierwszej>) => setD((p) => ({ ...p, ...z }));
  const egz = d.egzamin;
  const prz = d.przedluzenie;
  const ustawPrz = (z: Partial<PrzedluzeniePierwszej>) => ustaw({ przedluzenie: { ...(prz as PrzedluzeniePierwszej), ...z } });
  const sprawozdanie = d.sprawozdanie ?? PUSTE_SPRAWOZDANIE;

  const daty = [
    ...DATY.map(([k]) => d[k] as string | null),
    prz?.nowy_termin,
    prz?.data_zawiadomienia,
    prz?.okres_od,
    prz?.okres_do,
    prz?.nowy_termin_od,
  ];
  const zlaData = daty.some((x) => !poprawnaData(x));
  const brakPrzeslanki = egz?.wynik === "nie_dotyczy" && !egz.przeslanka;
  const brakUzasadnienia = stan.uzasadnienie_wymagane && !d.uzasadnienie?.trim();
  const niepelnePrzedluzenie = prz !== null && (!prz.nowy_termin || !prz.data_zawiadomienia);
  const zablokowany = czekam || zlaData || brakPrzeslanki || brakUzasadnienia || niepelnePrzedluzenie;
  const brakPola = Object.fromEntries(braki.map((b) => [b.id, b]));

  async function zapisz(zatwierdz: boolean) {
    setCzekam(true);
    setBlad(null);
    try {
      onZapisano(await zapiszPierwsza(token, stan.proces_id, doZapisu(d), zatwierdz));
    } catch (err) {
      const b = bladArkusza(err);
      setBlad(b.tekst);
      if (b.braki) setBraki(b.braki);
    } finally {
      setCzekam(false);
    }
  }

  async function pobierz(plik: "arkusz.pdf" | "zawiadomienie.pdf") {
    setBlad(null);
    try {
      zapiszPlik(await pobierzPdfPierwszej(token, stan.proces_id, plik), `${plik === "arkusz.pdf" ? "arkusz-pierwszej-oceny" : "zawiadomienie-5"}-${osoba.nazwisko}.pdf`);
    } catch (err) {
      setBlad(bladArkusza(err).tekst);
    }
  }

  return (
    <>
      {braki.length > 0 && (
        <section>
          <h2>Braki ({braki.length})</h2>
          <p className="meta">PDF i zatwierdzenie wymagają kompletnego arkusza.</p>
          <ul className="lista-brakow">
            {braki.map((b) => (
              <li key={b.id}>
                <strong>{b.etykieta}:</strong> {b.komunikat}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>Daty, sprawozdanie i egzamin</h2>
        <fieldset className="formularz" disabled={!edycja || czekam}>
          <div className="siatka-dat">
            {DATY.map(([k, nazwa]) => (
              <PoleDaty key={k} nazwa={nazwa} wartosc={d[k] as string | null} onZmiana={(v) => ustaw({ [k]: v } as Partial<DanePierwszej>)} />
            ))}
          </div>
          {zlaData && <p className="blad">Podaj datę w formacie RRRR-MM-DD, np. 2026-11-21.</p>}

          <label className="zaznacz">
            <input type="checkbox" checked={d.sprawozdanie_niezlozone} onChange={(e) => ustaw({ sprawozdanie_niezlozone: e.target.checked })} />
            <span>Sprawozdanie niezłożone (świadomy zapis braku)</span>
          </label>
          {!d.sprawozdanie_niezlozone &&
            SPRAWOZDANIE.map(([k, nazwa]) => (
              <label key={k} className="etykieta">
                Sprawozdanie: {nazwa.toLowerCase()}
                <textarea rows={2} value={sprawozdanie[k]} onChange={(e) => ustaw({ sprawozdanie: { ...sprawozdanie, [k]: e.target.value } })} />
              </label>
            ))}

          <div className="etykieta">Egzamin kończący służbę przygotowawczą</div>
          <Wybor
            etykieta="Egzamin"
            opcje={EGZAMIN.map((o) => ({ ...o }))}
            wartosc={egz?.wynik ?? null}
            zablokowane={!edycja}
            onWybierz={(w) => ustaw({ egzamin: w ? ({ wynik: w, przeslanka: null } as EgzaminPierwszej) : null })}
          />
          {egz?.wynik === "nie_dotyczy" && (
            <>
              <div className="etykieta">Przesłanka z § 10 ust. 3 (wymagana)</div>
              <Wybor
                etykieta="Przesłanka egzaminu"
                opcje={(Object.keys(PRZESLANKI) as PrzeslankaEgzaminu[]).map((w) => ({ wartosc: w, tekst: PRZESLANKI[w] }))}
                wartosc={egz.przeslanka}
                zablokowane={!edycja}
                onWybierz={(w) => ustaw({ egzamin: { wynik: "nie_dotyczy", przeslanka: w } })}
              />
              {egz.przeslanka && <Zrodla adnotacje={[stan.przeslanki_egzaminu[egz.przeslanka]]} />}
              {brakPrzeslanki && <p className="blad">Wskaż przesłankę dla „nie dotyczy”.</p>}
            </>
          )}

          <label className="zaznacz">
            <input
              type="checkbox"
              checked={prz !== null}
              onChange={(e) =>
                ustaw({
                  przedluzenie: e.target.checked
                    ? { nowy_termin: "", data_zawiadomienia: "", przyczyna: "usprawiedliwiona_nieobecnosc", okres_od: null, okres_do: null, nowy_termin_od: null }
                    : null,
                })
              }
            />
            <span>Przedłużenie terminu sprawozdania (zawiadomienie § 5)</span>
          </label>
          {prz && (
            <div className="nowy-przyklad">
              <div className="siatka-dat">
                <PoleDaty nazwa="Nowy termin" wartosc={prz.nowy_termin || null} onZmiana={(v) => ustawPrz({ nowy_termin: v ?? "" })} />
                <PoleDaty nazwa="Data zawiadomienia" wartosc={prz.data_zawiadomienia || null} onZmiana={(v) => ustawPrz({ data_zawiadomienia: v ?? "" })} />
                <PoleDaty nazwa="Nieobecność od" wartosc={prz.okres_od} onZmiana={(v) => ustawPrz({ okres_od: v })} />
                <PoleDaty nazwa="Nieobecność do" wartosc={prz.okres_do} onZmiana={(v) => ustawPrz({ okres_do: v })} />
                <PoleDaty nazwa="Nowy początek terminu" wartosc={prz.nowy_termin_od} onZmiana={(v) => ustawPrz({ nowy_termin_od: v })} />
              </div>
              <div className="etykieta">Przyczyna</div>
              <Wybor
                etykieta="Przyczyna przedłużenia"
                opcje={(Object.keys(PRZYCZYNY) as PrzedluzeniePierwszej["przyczyna"][]).map((w) => ({ wartosc: w, tekst: PRZYCZYNY[w] }))}
                wartosc={prz.przyczyna}
                zablokowane={!edycja}
                onWybierz={(w) => w && ustawPrz({ przyczyna: w })}
              />
            </div>
          )}

          <label className="etykieta">
            Uzasadnienie oceny{stan.uzasadnienie_wymagane ? " (wymagane przy ocenie negatywnej)" : " (opcjonalnie)"}
            <textarea rows={3} value={d.uzasadnienie ?? ""} onChange={(e) => ustaw({ uzasadnienie: e.target.value || null })} />
          </label>
          <Zrodla adnotacje={[stan.podstawa_uzasadnienia]} />

          {stan.wnioski_dostepne ? (
            <label className="etykieta">
              Wnioski dotyczące rozwoju zawodowego (pisze przełożony)
              <textarea rows={3} value={d.wnioski_rozwojowe ?? ""} onChange={(e) => ustaw({ wnioski_rozwojowe: e.target.value || null })} />
            </label>
          ) : (
            <p className="meta">Wnioski rozwojowe można sporządzić tylko po pozytywnej pierwszej ocenie.</p>
          )}
          <Zrodla adnotacje={[stan.podstawa_wnioskow]} />
        </fieldset>
      </section>

      {stan.formularz.sekcje
        .filter((s) => s.widoczna)
        .map((s) => (
          <section key={s.tytul}>
            <h2>{s.tytul}</h2>
            <div className="pola-arkusza">
              {s.pola
                .filter((p) => p.widoczne)
                .map((p) => (
                  <Pole
                    key={p.id}
                    p={p}
                    wartosc={p.edytowalne ? (d.pola[p.id] ?? p.wartosc ?? null) : p.wartosc}
                    brak={brakPola[p.id]}
                    edycja={edycja && !czekam && p.edytowalne}
                    onZmiana={(v) => ustaw({ pola: { ...d.pola, [p.id]: v } })}
                  />
                ))}
            </div>
          </section>
        ))}

      <section>
        <h2>Dokument</h2>
        <div className="wiersz">
          <div className="etykiety">
            <button type="button" className="jasny" disabled={!stan.formularz.pdf_dostepny} onClick={() => pobierz("arkusz.pdf")}>
              Pobierz arkusz PDF
            </button>
            {stan.zawiadomienie_dostepne && (
              <button type="button" className="jasny" onClick={() => pobierz("zawiadomienie.pdf")}>
                Pobierz zawiadomienie § 5 (PDF)
              </button>
            )}
          </div>
          {edycja && (
            <div className="etykiety">
              <button type="button" className="jasny" disabled={zablokowany} onClick={() => zapisz(false)}>
                Zapisz
              </button>
              <button type="button" disabled={zablokowany} onClick={() => zapisz(true)}>
                {czekam ? "Zapisuję…" : "Zatwierdź arkusz"}
              </button>
            </div>
          )}
        </div>
        {blad && <p className="blad">{blad}</p>}
        <details className="pozostale">
          <summary>Przypisy wzoru</summary>
          <ol className="slad">
            {Object.entries(stan.formularz.przypisy).map(([nr, tekst]) => (
              <li key={nr} value={Number(nr)} className="meta">
                {tekst}
              </li>
            ))}
          </ol>
        </details>
      </section>
    </>
  );
}

export function Pierwsza({
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
  const [stan, setStan] = useState<StanPierwszejOceny | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    pobierzPierwsza(token, proces.id)
      .then(setStan)
      .catch((err) => setBlad(bladArkusza(err).tekst));
  }, [token, proces.id]);

  const naglowek = (
    <section>
      <div className="wiersz">
        <div>
          <div className="etykieta">Krok 7 z 8 · Wynik, terminy i arkusz pierwszej oceny</div>
          <h2>
            {osoba.imie} {osoba.nazwisko}
          </h2>
          <p className="opis">pierwsza ocena · arkusz z załącznika nr 2{stan && ` (${stan.wersja_regul})`}</p>
        </div>
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do rozmowy
        </button>
      </div>
      {stan && <p className="brak">{stan.formularz.komunikat_podpis} Podpisy składa się odręcznie na wydruku.</p>}
      {stan?.formularz.zatwierdzony && <p className="sukces">Arkusz zatwierdzony.</p>}
      {blad && <p className="blad">{blad}</p>}
      {!stan && !blad && <p className="meta">Wczytuję pierwszą ocenę…</p>}
    </section>
  );
  if (!stan) return naglowek;

  const o = stan.obliczenie;
  const t = stan.terminy;
  const terminy = Object.entries(t).filter(([, v]) => v && typeof v === "object" && "data" in (v as object)) as [string, Termin][];
  const takNie = (v: unknown) => (v === null || v === undefined ? "—" : v ? "tak" : "nie");

  return (
    <>
      {naglowek}

      <section>
        <h2>Wynik pierwszej oceny</h2>
        {o ? (
          <>
            <p className="wartosc">
              <span className={`status ${o.wynik}`}>ocena {o.wynik}</span> średnia {o.srednia.replace(".", ",")}
              {o.poziom && ` · ${o.poziom}`}
            </p>
            <p className="meta">Rozstrzyga: {o.regula_rozstrzygajaca.zrodlo.lokalizator}</p>
            <Zrodla adnotacje={[o.regula_rozstrzygajaca.zrodlo]} />
          </>
        ) : (
          <p className="meta">Wynik policzy się po zapisaniu ocen cząstkowych wszystkich kryteriów, sprawozdania i egzaminu.</p>
        )}
        {stan.warunki.length > 0 && (
          <ul className="przeslanki">
            {stan.warunki.map((w) => (
              <li key={w.id}>
                <div className="wiersz-przeslanki">
                  <span className={`status ${w.spelniony ? "pozytywna" : "negatywna"}`}>{w.spelniony ? "spełniony" : "niespełniony"}</span>
                  <span>{w.opis}</span>
                </div>
                <Zrodla adnotacje={[w.zrodlo]} />
              </li>
            ))}
          </ul>
        )}
        <p className="meta">
          Skala pierwszej oceny 3/5/7 pkt. Poziomy modelu przechodzą na nią tak:{" "}
          {Object.entries(stan.mapowanie.wartosci)
            .map(([z, na]) => `${z}→${na}`)
            .join(", ")}{" "}
          ({stan.wersja_metodyki}).
        </p>
        <Zrodla adnotacje={stan.mapowanie.adnotacje} />
        {o && (
          <details className="zadania-osp">
            <summary>Jak policzono wynik</summary>
            <Slad slad={o.slad} />
          </details>
        )}
      </section>

      <section>
        <h2>Terminy</h2>
        <table>
          <thead>
            <tr>
              <th>Termin</th>
              <th>Data</th>
              <th>Skąd</th>
            </tr>
          </thead>
          <tbody>
            {terminy.map(([k, v]) => (
              <tr key={k}>
                <td>{NAZWY_TERMINOW[k] ?? k}</td>
                <td>{data(v.data)}</td>
                <td>
                  <Slad slad={v.slad} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {typeof t.data_rozmowy_wstepnej === "string" && <p className="meta">Rozmowa wstępna odbyła się {data(t.data_rozmowy_wstepnej)}.</p>}
        <p className="meta">
          Sprawozdanie w terminie: {takNie(t.sprawozdanie_w_terminie)} · obejmuje co najmniej 7 miesięcy: {takNie(t.sprawozdanie_min_7_miesiecy)}
        </p>
        {t.slad.length > 0 && <Slad slad={t.slad} />}
        {t.uwagi.map((u) => (
          <p key={u} className="meta">
            {u}
          </p>
        ))}
        {t.braki.length > 0 && (
          <div className="brak">
            System nie zgaduje, brakuje danych:
            <ul>
              {t.braki.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <Formularz
        key={JSON.stringify(stan.dane) + String(stan.formularz.zatwierdzony)}
        stan={stan}
        token={token}
        osoba={osoba}
        edycja={moznaProwadzic}
        onZapisano={setStan}
      />

      {stan.wnioski_dostepne && (
        <section>
          <div className="wiersz">
            <span className="meta">Propozycje form rozwoju do wniosków.</span>
            <button type="button" className="jasny" onClick={onDalej}>
              Dalej: wnioski rozwojowe
            </button>
          </div>
        </section>
      )}
    </>
  );
}
