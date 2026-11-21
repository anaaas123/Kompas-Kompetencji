import { FormEvent, useEffect, useMemo, useState } from "react";
import { pobierzCykl, pobierzPracownikow, type EtapOsoby, type Pracownik } from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import { Kafel } from "./Wykresy";
import { data, dni, odmiana, osoby, wedlugKomorek } from "./zespol-dane";
import "./widoki.css";
import "./pulpit.css";

/**
 * Pulpit (strona główna) jak w makiecie v3: „Do zrobienia” to osoby z następną czynnością i terminem
 * z /api/cykl (początek okresu: kryteria albo rozmowa wstępna; koniec: rozmowa oceniająca i ocena).
 * Trzy kafle filtrują tę listę; kafla z zerem nie ma. Z prawej krótko o zespole i pytania o zasady,
 * na dole przyklejone pole „znajdź pracownika albo zapytaj”. Frontend niczego nie liczy z przepisów.
 */
const ZASADY = [
  "Co omawia się na rozmowie oceniającej?",
  "Kiedy ocena okresowa jest negatywna?",
  "Ile dni ma pracownik na sprzeciw od oceny okresowej?",
];
const DZIS = new Date().toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });

const NA_START = 5;

type Filtr = "wszystkie" | "po_terminie" | "kryteria" | "ocena";
const NAZWA_FILTRA: Record<Exclude<Filtr, "wszystkie">, string> = {
  po_terminie: "po terminie",
  kryteria: "ustalenie kryteriów",
  ocena: "do oceny",
};

interface Sprawa {
  osoba: Pracownik;
  e: EtapOsoby;
}

const doZrobienia = (s: Sprawa) => s.e.etap !== "okres";
const pasuje = (s: Sprawa, f: Filtr) => f === "wszystkie" || (f === "po_terminie" ? s.e.po_terminie : s.e.etap === f);

/** „po terminie 2 dni” na czerwono, „za 5 dni” na bursztynowo do 14 dni; dalsze terminy bez plakietki. */
function Plakietka({ e }: { e: EtapOsoby }) {
  const n = e.dni_do_terminu;
  if (n === null) return null;
  if (e.po_terminie) return <span className="status negatywna">po terminie {dni(-n)}</span>;
  if (n === 0) return <span className="status uwaga">dziś</span>;
  if (n <= 14) return <span className="status uwaga">za {dni(n)}</span>;
  return null;
}

export function Pulpit({
  sesja,
  onWybierz,
  onZapytaj,
  onWyloguj,
  onZespol,
  onPracownicy,
}: {
  sesja: Sesja;
  onWybierz: (p: Pracownik) => void;
  onZapytaj: (pytanie: string) => void;
  onWyloguj: () => void;
  onZespol: () => void;
  onPracownicy: () => void;
}) {
  const [sprawy, setSprawy] = useState<Sprawa[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [szukaj, setSzukaj] = useState("");
  const [filtr, setFiltr] = useState<Filtr>("wszystkie");
  const [wszystkie, setWszystkie] = useState(false);
  const rola = sesja.uzytkownik.rola;
  const zespol = rola !== "oceniany";

  useEffect(() => {
    let aktualne = true;
    Promise.all([pobierzPracownikow(sesja.token), pobierzCykl(sesja.token)])
      .then(([ludzie, cykl]) => {
        const po = new Map(ludzie.map((p) => [p.osoba_id, p]));
        const wynik = cykl.filter((e) => po.has(e.osoba_id)).map((e) => ({ osoba: po.get(e.osoba_id)!, e }));
        // Najpierw po terminie, potem najbliższy termin; brak terminu na końcu.
        wynik.sort(
          (a, b) =>
            Number(b.e.po_terminie) - Number(a.e.po_terminie) ||
            (a.e.dni_do_terminu ?? 1e9) - (b.e.dni_do_terminu ?? 1e9),
        );
        if (aktualne) setSprawy(wynik);
      })
      .catch((err) => {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać spraw.");
      });
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj]);

  const lista = useMemo(() => {
    if (!sprawy) return null;
    const q = szukaj.trim().toLowerCase();
    if (q) return sprawy.filter((s) => `${s.osoba.imie} ${s.osoba.nazwisko}`.toLowerCase().includes(q));
    return sprawy.filter((s) => doZrobienia(s) && pasuje(s, filtr));
  }, [sprawy, szukaj, filtr]);

  function wyslij(e: FormEvent) {
    e.preventDefault();
    const q = szukaj.trim();
    if (!q) return;
    // Jedna osoba pasuje do wpisu: otwórz ją; inaczej to pytanie do asystenta.
    if (lista && lista.length === 1) onWybierz(lista[0].osoba);
    else onZapytaj(q);
    setSzukaj("");
  }

  // Bez filtra i wyszukiwania najwyżej NA_START najpilniejszych: długa lista (HR) nie chowa się pod paskiem.
  const skrocona = !wszystkie && !szukaj && filtr === "wszystkie" && (lista?.length ?? 0) > NA_START;
  const przelacz = (f: Filtr) => setFiltr((obecny) => (obecny === f ? "wszystkie" : f));
  const ile = (f: Filtr) => sprawy?.filter((s) => doZrobienia(s) && pasuje(s, f)).length ?? 0;
  const najblizszy = (f: Filtr) => sprawy?.find((s) => doZrobienia(s) && pasuje(s, f) && s.e.termin);
  const kafle: { f: Exclude<Filtr, "wszystkie">; etykieta: string; ton?: "zle" | "uwaga" }[] = [
    { f: "po_terminie", etykieta: "Po terminie", ton: "zle" },
    { f: "kryteria", etykieta: "Ustal kryteria" },
    { f: "ocena", etykieta: "Do oceny" },
  ];
  const ludzie = sprawy?.map((s) => s.osoba) ?? [];
  const wydzialow = sprawy ? wedlugKomorek(sprawy, (s) => s.osoba.komorka).reduce((a, g) => a + g.wydzialy.length, 0) : 0;
  const ostatnia = (w: "pozytywna" | "negatywna") => ludzie.filter((p) => p.ostatnia_ocena_okresowa?.wynik === w).length;
  const wOkresie = sprawy?.filter((s) => !doZrobienia(s)).length ?? 0;

  return (
    <div className="pulpit">
      <div className="pulpit-naglowek">
        <h1>Na dziś</h1>
        <p className="meta">{DZIS}</p>
      </div>

      {zespol && sprawy && kafle.some((k) => ile(k.f) > 0) && (
        <div className="pulpit-kafle">
          {kafle
            .filter((k) => ile(k.f) > 0)
            .map((k) => {
              const n = najblizszy(k.f);
              return (
                <Kafel
                  key={k.f}
                  etykieta={k.etykieta}
                  wartosc={osoby(ile(k.f))}
                  ton={k.ton}
                  opis={n ? `Najbliżej: ${n.osoba.imie} ${n.osoba.nazwisko}, ${n.e.czynnosc.toLowerCase()} do ${data(n.e.termin!.data)}` : ""}
                  onClick={() => przelacz(k.f)}
                  wybrany={filtr === k.f}
                />
              );
            })}
        </div>
      )}

      <div className="pulpit-kolumny">
        <section className="sekcja">
          <div className="wiersz-tytulu">
            <h2>{szukaj ? "Wyniki wyszukiwania" : rola === "oceniany" ? "Twoja ocena" : rola === "hr" ? "Terminy w urzędzie" : "Do zrobienia"}</h2>
            {filtr !== "wszystkie" && !szukaj && (
              <button type="button" className="link" onClick={() => setFiltr("wszystkie")}>
                Tylko {NAZWA_FILTRA[filtr]} · pokaż wszystko
              </button>
            )}
          </div>
          {blad && <p className="blad">{blad}</p>}
          {!blad && lista === null && <SzkieletListy />}
          {lista?.length === 0 && (
            <p className="meta">
              {szukaj ? "Nikt nie pasuje do wpisu. Enter wyśle go jako pytanie do asystenta." : "Na dziś nic. Pozostali są w trakcie okresu oceny."}
            </p>
          )}
          {lista && lista.length > 0 && (
            <div className="lista">
              {(skrocona ? lista.slice(0, NA_START) : lista).map((s) => (
                <WierszListy
                  key={s.osoba.osoba_id}
                  lewa={<Inicjaly imie={s.osoba.imie} nazwisko={s.osoba.nazwisko} />}
                  tytul={`${s.osoba.imie} ${s.osoba.nazwisko}`}
                  znacznik={<Plakietka e={s.e} />}
                  opis={s.e.termin ? `${s.e.czynnosc} · do ${data(s.e.termin.data)}` : s.e.czynnosc}
                  onClick={() => onWybierz(s.osoba)}
                />
              ))}
            </div>
          )}
          {skrocona && (
            <button type="button" className="link pulpit-wiecej" onClick={() => setWszystkie(true)}>
              Pokaż wszystkie ({lista!.length})
            </button>
          )}
          {zespol && sprawy && !szukaj && wOkresie > 0 && (
            <button type="button" className="link pulpit-wiecej" onClick={onPracownicy}>
              {wOkresie} {odmiana(wOkresie, "osoba", "osoby", "osób")} w trakcie okresu oceny · wszyscy pracownicy
            </button>
          )}
        </section>

        <aside className="pulpit-boczna">
          {zespol && sprawy && (
            <section className="sekcja">
              <h2>{rola === "hr" ? "Urząd" : "Mój zespół"}</h2>
              <dl className="pulpit-fakty">
                <div>
                  <dt>Ludzie</dt>
                  <dd>
                    {osoby(ludzie.length)} · {wydzialow} {odmiana(wydzialow, "wydział", "wydziały", "wydziałów")}
                  </dd>
                </div>
                <div>
                  <dt>Ostatnie oceny</dt>
                  <dd>
                    {ostatnia("pozytywna")} poz. · {ostatnia("negatywna")} neg. · {ludzie.length - ostatnia("pozytywna") - ostatnia("negatywna")} bez oceny
                  </dd>
                </div>
              </dl>
              <button type="button" className="link pulpit-wiecej" onClick={onZespol}>
                Analiza zespołu
              </button>
            </section>
          )}
          <section className="sekcja">
            <h2>Zasady</h2>
            <div className="lista ciasna">
              {ZASADY.map((z) => (
                <WierszListy key={z} maly lewa={<Ikona nazwa="pytanie" />} tytul={z} onClick={() => onZapytaj(z)} />
              ))}
            </div>
          </section>
        </aside>
      </div>

      <div className="pulpit-pasek">
        <form className="pole-zapytania" role="search" onSubmit={wyslij}>
          <Ikona nazwa="szukaj" />
          <input
            value={szukaj}
            onChange={(e) => setSzukaj(e.target.value)}
            placeholder="Znajdź pracownika albo zapytaj o zasady oceny…"
            aria-label="Znajdź pracownika albo zapytaj o zasady oceny"
            autoComplete="off"
          />
          <button type="submit" className="wyslij" aria-label="Wyślij" disabled={!szukaj.trim()}>
            <Ikona nazwa="gora" />
          </button>
        </form>
      </div>
    </div>
  );
}
