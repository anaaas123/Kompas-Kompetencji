import { useEffect, useState } from "react";
import { MapaKompetencji } from "./Kompetencje";
import {
  pobierzCykl,
  pobierzKrok1,
  pobierzMapeKompetencji,
  pobierzPracownikow,
  pobierzProcesy,
  pobierzTerminy,
  type MapaKompetencji as Mapa,
  type Pracownik,
} from "./api";
import type { Sesja } from "./Konto";
import { SzkieletListy, WierszListy } from "./Lista";
import { Ikona } from "./Ikona";
import { Kafel, PasekUdzialow, type Udzial } from "./Wykresy";
import { data, osoby, podzial, poTerminie, wkrotce, doZrobienia, type FiltrPracownikow, type Sprawa } from "./zespol-dane";
import "./widoki.css";

/**
 * Sprawy osób w zakresie użytkownika: przełożony podwładnych, HR wszystkich, oceniany siebie.
 * Proces w toku i termin z API; dla osób bez procesu ścieżka proponowana z analizy kroku 1.
 */
export function useSprawy(sesja: Sesja, onWyloguj: () => void) {
  const [sprawy, setSprawy] = useState<Sprawa[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    let aktualne = true;
    (async () => {
      try {
        const [ludzie, procesy, terminy, cykl] = await Promise.all([
          pobierzPracownikow(sesja.token),
          pobierzProcesy(sesja.token),
          // Brak terminów albo etapów nie blokuje widoku; liczby powiedzą wtedy, czego nie wiadomo.
          pobierzTerminy(sesja.token).catch(() => []),
          pobierzCykl(sesja.token).catch(() => []),
        ]);
        const wynik = await Promise.all(
          ludzie.map(async (osoba): Promise<Sprawa> => {
            const proces = procesy.find((p) => p.osoba_id === osoba.osoba_id && p.status === "W_TOKU") ?? null;
            const termin = (proces && terminy.find((t) => t.proces_id === proces.id)) || null;
            const c = cykl.find((x) => x.osoba_id === osoba.osoba_id) ?? null;
            if (proces) return { osoba, proces, proponowana: proces.sciezka, termin, cykl: c };
            // Ścieżkę podaje /api/cykl; analiza kroku 1 tylko wtedy, gdy etapu brak.
            if (c) return { osoba, proces: null, proponowana: c.sciezka, termin: null, cykl: c };
            const analiza = await pobierzKrok1(sesja.token, osoba.osoba_id).catch(() => null);
            return { osoba, proces: null, proponowana: analiza?.sciezka.proponowana ?? null, termin: null, cykl: null };
          }),
        );
        // Najpierw najbliższy termin z cyklu (po terminie na górze), osoby bez terminu na końcu.
        const dniDo = (s: Sprawa) => s.cykl?.dni_do_terminu ?? s.termin?.dni_do_terminu ?? 99999;
        wynik.sort((a, b) => dniDo(a) - dniDo(b));
        if (aktualne) setSprawy(wynik);
      } catch (err) {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać danych zespołu.");
      }
    })();
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj]);

  return { sprawy, blad };
}

/** Wybrana komórka: cały zakres (urząd albo zespół przełożonego), departament albo wydział. */
interface Wybor {
  departament?: string;
  wydzial?: string;
}

const komorkaWyboru = (w: Wybor) => (w.wydzial ? `${w.departament} / ${w.wydzial}` : w.departament);

function wZakresie(s: Sprawa, w: Wybor): boolean {
  const { departament, wydzial } = podzial(s.osoba.komorka);
  return (!w.departament || departament === w.departament) && (!w.wydzial || wydzial === w.wydzial);
}

function policz(lista: Sprawa[]) {
  return {
    osob: lista.length,
    poTerminie: lista.filter(poTerminie),
    wkrotce: lista.filter(wkrotce),
    teraz: lista.filter(doZrobienia),
    pozytywne: lista.filter((s) => s.osoba.ostatnia_ocena_okresowa?.wynik === "pozytywna").length,
    negatywne: lista.filter((s) => s.osoba.ostatnia_ocena_okresowa?.wynik === "negatywna").length,
    bezOceny: lista.filter((s) => !s.osoba.ostatnia_ocena_okresowa).length,
  };
}

const kto = (s: Sprawa) => `${s.osoba.imie} ${s.osoba.nazwisko}`;
const czynnoscZDniem = (s: Sprawa) => (s.cykl?.termin ? `${s.cykl.czynnosc}, ${data(s.cykl.termin.data)}` : s.cykl?.czynnosc ?? "");

/**
 * Zespół: analiza komórki, bez listy osób (osoby są w „Pracownicy”). Odpowiada w 10 sekund: kto jest po terminie,
 * co jest najbliżej, co trzeba zrobić teraz, jak wypadły ostatnie oceny i która komórka ma zaległości.
 * Każda liczba ma podstawę (osoba i czynność albo źródło). Kliknięcie liczby albo komórki otwiera listę z filtrem.
 */
export function Zespol({
  sesja,
  onPracownicy,
  onWyloguj,
  onWybierz,
}: {
  sesja: Sesja;
  onPracownicy: (f: FiltrPracownikow) => void;
  onWyloguj: () => void;
  onWybierz?: (p: Pracownik) => void;
}) {
  const { sprawy, blad } = useSprawy(sesja, onWyloguj);
  const [wybor, setWybor] = useState<Wybor>({});
  // Mapa kompetencji (#33) tylko dla przełożonego: HR nie ma prawa do treści ocen (zadanie MC, minimalizacja danych).
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const przelozony = sesja.uzytkownik.rola === "przelozony";
  useEffect(() => {
    if (przelozony) pobierzMapeKompetencji(sesja.token).then(setMapa).catch(() => setMapa(null));
  }, [sesja.token, przelozony]);
  const hr = sesja.uzytkownik.rola === "hr";
  const korzen = hr ? "Cały urząd" : "Mój zespół";

  if (blad) return <p className="blad">{blad}</p>;
  if (!sprawy)
    return (
      <div className="widok">
        <h1>Zespół</h1>
        <SzkieletListy wiersze={3} />
      </div>
    );

  const zakres = sprawy.filter((s) => wZakresie(s, wybor));
  const l = policz(zakres);
  const komorka = komorkaWyboru(wybor);
  const doListy = (f: FiltrPracownikow = {}) => () => onPracownicy({ komorka, ...f });
  const najblizszy = [...l.wkrotce].sort((a, b) => (a.cykl?.dni_do_terminu ?? 0) - (b.cykl?.dni_do_terminu ?? 0))[0];
  const bezEtapu = zakres.filter((s) => !s.cykl).length;

  // Komórki podrzędne: departamenty w całym zakresie, wydziały w departamencie; posortowane po zaległości.
  const podrzedne = wybor.wydzial
    ? []
    : [...new Set(zakres.map((s) => (wybor.departament ? podzial(s.osoba.komorka).wydzial : podzial(s.osoba.komorka).departament)))]
        .map((nazwa) => {
          const w: Wybor = wybor.departament ? { departament: wybor.departament, wydzial: nazwa } : { departament: nazwa };
          return { nazwa, wybor: w, liczby: policz(zakres.filter((s) => wZakresie(s, w))) };
        })
        .sort(
          (a, b) =>
            b.liczby.poTerminie.length - a.liczby.poTerminie.length ||
            b.liczby.wkrotce.length - a.liczby.wkrotce.length ||
            a.nazwa.localeCompare(b.nazwa, "pl"),
        );

  const oceny: Udzial[] = [
    { nazwa: "pozytywna", liczba: l.pozytywne, ton: "dobrze", onClick: doListy({ ocena: "pozytywna" }) },
    { nazwa: "negatywna", liczba: l.negatywne, ton: "zle", onClick: doListy({ ocena: "negatywna" }) },
    { nazwa: "jeszcze bez oceny", liczba: l.bezOceny, ton: "pusty", onClick: doListy({ ocena: "brak" }) },
  ];

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <h1>Zespół</h1>
        <nav className="okruszki" aria-label="Wybrana komórka">
          <button type="button" className="link" aria-current={!wybor.departament ? "page" : undefined} onClick={() => setWybor({})}>
            {korzen}
          </button>
          {wybor.departament && (
            <>
              <Ikona nazwa="dalej" rozmiar={16} />
              <button
                type="button"
                className="link"
                aria-current={!wybor.wydzial ? "page" : undefined}
                onClick={() => setWybor({ departament: wybor.departament })}
              >
                {wybor.departament}
              </button>
            </>
          )}
          {wybor.wydzial && (
            <>
              <Ikona nazwa="dalej" rozmiar={16} />
              <span aria-current="page">{wybor.wydzial}</span>
            </>
          )}
        </nav>
        <p className="meta">
          {osoby(l.osob)} · etapy i terminy z reguł ocen{bezEtapu ? ` · bez ustalonego etapu: ${bezEtapu}` : ""}
        </p>
      </div>

      <div className="kafle">
        <Kafel
          etykieta="Po terminie"
          wartosc={l.poTerminie.length}
          ton={l.poTerminie.length ? "zle" : undefined}
          opis={
            l.poTerminie.length
              ? l.poTerminie.slice(0, 2).map((s) => `${kto(s)}: ${czynnoscZDniem(s)}`).join(" · ") +
                (l.poTerminie.length > 2 ? ` i ${l.poTerminie.length - 2} więcej` : "")
              : "Nikt nie przekroczył terminu."
          }
          onClick={l.poTerminie.length ? doListy({ termin: "po_terminie" }) : undefined}
        />
        <Kafel
          etykieta="Termin w ciągu 14 dni"
          wartosc={l.wkrotce.length}
          ton={l.wkrotce.length ? "uwaga" : undefined}
          opis={najblizszy ? `Najbliższy: ${kto(najblizszy)}, ${czynnoscZDniem(najblizszy)}` : "Żaden termin nie wypada w ciągu 14 dni."}
          onClick={l.wkrotce.length ? doListy({ termin: "wkrotce" }) : undefined}
        />
        <Kafel
          etykieta="Do zrobienia teraz"
          wartosc={l.teraz.length}
          opis={
            l.teraz.length
              ? `ustalenie kryteriów: ${l.teraz.filter((s) => s.cykl?.etap === "kryteria").length} · ocena końcowa: ${
                  l.teraz.filter((s) => s.cykl?.etap === "ocena").length
                }`
              : "Wszyscy są w okresie oceny."
          }
          onClick={l.teraz.length ? () => onPracownicy({ komorka }) : undefined}
        />
      </div>

      {mapa && <MapaKompetencji mapa={mapa} ludzie={zakres.map((s) => s.osoba)} onWybierz={onWybierz} />}

      <PasekUdzialow tytul="Ostatnia ocena okresowa" podstawa="kartoteka QNT; kliknij liczbę, aby zobaczyć osoby" udzialy={oceny} />

      {podrzedne.length > 0 && (
        <div className="sekcja">
          <h2>{wybor.departament ? "Wydziały" : hr ? "Departamenty" : "Komórki"}</h2>
          <div className="lista">
            {podrzedne.map((k) => (
              <WierszListy
                key={k.nazwa}
                lewa={<Ikona nazwa="osoby" />}
                tytul={k.nazwa}
                znacznik={
                  k.liczby.poTerminie.length > 0 && <span className="status negatywna">po terminie {k.liczby.poTerminie.length}</span>
                }
                opis={
                  <>
                    {osoby(k.liczby.osob)} · termin w 14 dni: {k.liczby.wkrotce.length} · do zrobienia teraz: {k.liczby.teraz.length}
                    <br />
                    ostatnie oceny: pozytywne {k.liczby.pozytywne} · negatywne {k.liczby.negatywne} · bez oceny {k.liczby.bezOceny}
                  </>
                }
                onClick={() => setWybor(k.wybor)}
              />
            ))}
          </div>
        </div>
      )}

      <button type="button" className="jasny do-listy" onClick={doListy()}>
        Pracownicy: {wybor.wydzial ?? wybor.departament ?? korzen.toLowerCase()} ({osoby(l.osob)})
      </button>
    </div>
  );
}
