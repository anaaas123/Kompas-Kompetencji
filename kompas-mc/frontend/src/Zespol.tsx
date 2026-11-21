import { useEffect, useState } from "react";
import { MapaKompetencji, nazwaKryterium } from "./Kompetencje";
import {
  pobierzCykl,
  pobierzKrok1,
  pobierzMapeKompetencji,
  pobierzPracownikow,
  pobierzProcesy,
  pobierzTerminy,
  type EtapOsoby,
  type MapaKompetencji as Mapa,
  type Pracownik,
} from "./api";
import type { Sesja } from "./Konto";
import { SzkieletListy, WierszListy } from "./Lista";
import { Ikona } from "./Ikona";
import { Kafel, OsTerminow, PasekUdzialow, type PunktOsi, type Udzial } from "./Wykresy";
import {
  data,
  kiedy,
  nastepnyKrok,
  osoby,
  podzial,
  poTerminie,
  wkrotce,
  doZrobienia,
  NAZWA_ETAPU,
  NAZWA_SCIEZKI,
  type FiltrPracownikow,
  type Sprawa,
} from "./zespol-dane";
import "./widoki.css";
import "./zespol.css";

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

const ETAPY: EtapOsoby["etap"][] = ["kryteria", "okres", "ocena", "brak_danych"];
/** Zasięg osi terminów w dniach. */
const HORYZONT = 90;

function policz(lista: Sprawa[]) {
  return {
    osob: lista.length,
    etapy: Object.fromEntries(ETAPY.map((e) => [e, lista.filter((s) => s.cykl?.etap === e).length])) as Record<EtapOsoby["etap"], number>,
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

/** Pole CSV: tekst zaczynający się od =, +, -, @ dostaje apostrof (Excel nie wykona go jako formuły). */
function poleCsv(v: string | number): string {
  if (typeof v === "number") return String(v);
  const t = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
  return /[;"\r\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
}

/** Zestawienie osób w zakresie; dla przełożonego punkty kryteriów z mapy kompetencji. Separator „;”, BOM dla Excela. */
function zestawienieCsv(lista: Sprawa[], mapa: Mapa | null): string {
  const punkty = (s: Sprawa) => mapa?.osoby.find((o) => o.osoba_id === s.osoba.osoba_id)?.punkty ?? {};
  const kryteria = (mapa?.kryteria ?? []).filter((k) => lista.some((s) => punkty(s)[k.kompetencja_id] !== undefined));
  const naglowek = ["osoba", "stanowisko", "departament", "wydział", "ścieżka", "czynność", "termin", "dni do terminu", "ostatnia ocena"];
  const wiersze = lista.map((s) => {
    const { departament, wydzial } = podzial(s.osoba.komorka);
    const sciezka = s.cykl?.sciezka ?? s.proponowana;
    const ocena = s.osoba.ostatnia_ocena_okresowa;
    return [
      kto(s),
      s.osoba.stanowisko,
      departament,
      wydzial,
      sciezka ? NAZWA_SCIEZKI[sciezka] : "",
      s.cykl?.czynnosc ?? nastepnyKrok(s),
      s.cykl?.termin ? data(s.cykl.termin.data) : "",
      s.cykl?.dni_do_terminu ?? "",
      ocena ? `${ocena.wynik}, ${data(ocena.data)}` : "brak",
      ...kryteria.map((k) => punkty(s)[k.kompetencja_id] ?? ""),
    ];
  });
  const tabela = [[...naglowek, ...kryteria.map((k) => nazwaKryterium(k.nazwa))], ...wiersze];
  return "\uFEFF" + tabela.map((w) => w.map(poleCsv).join(";")).join("\r\n") + "\r\n";
}

function pobierzPlik(nazwa: string, tresc: string) {
  const url = URL.createObjectURL(new Blob([tresc], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nazwa;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); // Firefox i Safari czytają adres po kliknięciu
}

/** Mały pasek etapów w wierszu komórki: same proporcje, liczby są w opisie wiersza i w legendzie wyżej. */
function MiniPasekEtapow({ etapy }: { etapy: Record<EtapOsoby["etap"], number> }) {
  return (
    <span className="mini-pasek" role="img" aria-label={`Etapy: ${ETAPY.map((e) => `${NAZWA_ETAPU[e]} ${etapy[e]}`).join(", ")}`}>
      {ETAPY.filter((e) => etapy[e] > 0).map((e) => (
        <span key={e} className={`odcinek ${e}`} style={{ flexGrow: etapy[e] }} />
      ))}
    </span>
  );
}

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

  const etapy: Udzial[] = ETAPY.map((e) => ({
    nazwa: NAZWA_ETAPU[e],
    liczba: l.etapy[e],
    ton: e,
    onClick: doListy({ etap: e }),
  }));
  const zEtapem = l.osob - bezEtapu;

  const zTerminem = zakres.filter((s) => s.cykl?.termin && s.cykl.dni_do_terminu !== null);
  const punkty: PunktOsi[] = zTerminem.map((s) => {
    const c = s.cykl!;
    const dni = c.dni_do_terminu!;
    return {
      klucz: s.osoba.osoba_id,
      znak: `${s.osoba.imie.charAt(0)}${s.osoba.nazwisko.charAt(0)}`,
      tytul: kto(s),
      opis: `${c.czynnosc}, ${data(c.termin!.data)} (${kiedy(dni)}) · ${NAZWA_ETAPU[c.etap]}`,
      dni,
      ton: c.etap,
      onClick: onWybierz ? () => onWybierz(s.osoba) : undefined,
    };
  });
  const pozniej = punkty.filter((p) => p.dni > HORYZONT).length;

  const oceny: Udzial[] = [
    { nazwa: "pozytywna", liczba: l.pozytywne, ton: "dobrze", onClick: doListy({ ocena: "pozytywna" }) },
    { nazwa: "negatywna", liczba: l.negatywne, ton: "zle", onClick: doListy({ ocena: "negatywna" }) },
    { nazwa: "jeszcze bez oceny", liczba: l.bezOceny, ton: "pusty", onClick: doListy({ ocena: "brak" }) },
  ];

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <div className="wiersz-tytulu">
          <h1>Zespół</h1>
          <button
            type="button"
            className="jasny"
            onClick={() => pobierzPlik(`zestawienie-zespolu-${new Date().toISOString().slice(0, 10)}.csv`, zestawienieCsv(zakres, mapa))}
          >
            Pobierz zestawienie (CSV)
          </button>
        </div>
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

      <section className="etapy-terminy">
        <h2>Etapy i terminy</h2>
        <PasekUdzialow
          tytul="Etap cyklu oceny"
          podstawa={`${osoby(zEtapem)} z etapem z reguł ocen${bezEtapu ? `, bez etapu: ${bezEtapu}` : ""}; kliknij odcinek albo nazwę, aby zobaczyć osoby`}
          udzialy={etapy}
        />
        <figure className="udzialy">
          <figcaption>
            <span className="kafel-etykieta">Terminy w najbliższych {HORYZONT} dniach</span>
            <span className="meta">
              na osi: {osoby(punkty.length - pozniej)} · później niż za {HORYZONT} dni: {pozniej} · bez terminu: {l.osob - zTerminem.length}; kolor
              punktu to etap z paska wyżej, kliknięcie otwiera kartę
            </span>
          </figcaption>
          <OsTerminow punkty={punkty} horyzont={HORYZONT} />
        </figure>
      </section>

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
                    <MiniPasekEtapow etapy={k.liczby.etapy} />
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
