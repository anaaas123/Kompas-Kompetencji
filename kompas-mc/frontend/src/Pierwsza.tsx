import { useEffect, useState } from "react";
import {
  pobierzPdfPierwszej,
  pobierzPierwsza,
  zapiszPierwsza,
  zakonczPierwsza,
  type BrakArkusza,
  type DanePierwszej,
  type EgzaminPierwszej,
  type Pracownik,
  type PrzedluzeniePierwszej,
  type PrzeslankaEgzaminu,
  type SprawozdaniePierwszej,
  type StanPierwszejOceny,
  type Termin,
} from "./api";
import { DatyWzoru, PolaWzoru, bladArkusza, brakiPol, pobierzPrzelozonego, podpowiedziPol } from "./Arkusz";
import { PropozycjeZwarte } from "./Wnioski";
import { Zrodla, nazwaKryterium } from "./Krok1";
import { Wybor } from "./Ocena";
import {
  BladPola,
  Naglowek,
  Podsumowanie,
  PoleDaty,
  PoleOpisowe,
  Sekcja,
  Slad,
  TabelaTerminow,
  Wczytywanie,
  Werdykt,
  data,
  dzienZapisu,
  type ZRozmowy,
  zRozmowy,
  zachowajDateZapoznania,
  poprawnaData,
  zapiszPlik,
  drukujDoPodpisu,
  type Brak,
  type Krok7Props,
} from "./Wynik";
import "./krok7.css";

const NAZWY_TERMINOW: Record<string, string> = {
  termin_rozmowy_wstepnej: "Rozmowa wstępna (termin)",
  pierwsza_ocena_od: "Pierwsza ocena od",
  pierwsza_ocena_do: "Pierwsza ocena do",
  termin_sprawozdania_bazowy_od: "Sprawozdanie, okno bazowe od",
  termin_sprawozdania_bazowy_do: "Sprawozdanie, okno bazowe do",
  termin_sprawozdania_od: "Sprawozdanie od",
  termin_sprawozdania_do: "Sprawozdanie do",
};

const DATY = [
  ["data_rozmowy_wstepnej", "Rozmowa wstępna", "wyjatki"],
  ["wyznaczony_termin_sprawozdania", "Wyznaczony termin sprawozdania (ostatni dzień)", "raport"],
  ["termin_sprawozdania_od", "Początek terminu sprawozdania, gdy inny niż domyślny", "wyjatki"],
  ["data_zlozenia_sprawozdania", "Złożenie sprawozdania", "raport"],
  ["sprawozdanie_okres_od", "Sprawozdanie za okres od", "raport"],
  ["sprawozdanie_okres_do", "Sprawozdanie za okres do", "raport"],
  ["data_rozmowy_oceniajacej", "Rozmowa oceniająca", "daty"],
  ["data_sporzadzenia_oceny", "Sporządzenie oceny", "daty"],
  ["data_konca_zatrudnienia", "Koniec umowy na czas określony", "wyjatki"],
  ["data_ustalenia_oceny_zastepstwa", "Ustalenie pierwszej oceny przy zastępstwie", "wyjatki"],
] as const;

function grupaDaty(cel: string) {
  return DATY.find(([k]) => k === cel)?.[2];
}

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

const PUSTE_SPRAWOZDANIE: SprawozdaniePierwszej = {
  zadania: "",
  problemy_i_rozwiazania: "",
  nowe_umiejetnosci_i_wiedza: "",
  propozycje_usprawnien: "",
};

/** Wysyłamy komplet danych z GET; puste sprawozdanie idzie jako null, bo API wymaga wszystkich czterech pól. */
function doZapisu(d: DanePierwszej): DanePierwszej {
  const s = d.sprawozdanie;
  const pusteSprawozdanie = !s || Object.values(s).every((v) => !v.trim());
  return { ...d, sprawozdanie: d.sprawozdanie_niezlozone || pusteSprawozdanie ? null : s };
}

function daneFormularza(stan: StanPierwszejOceny, edycja: boolean) {
  const dane = { ...stan.dane, egzamin: stan.dane.egzamin ?? stan.egzamin };
  const dataKierujacego = "dokonanie_oceny.kierujacy.data";
  // We wzorze API powtarza tu datę sporządzenia. W szkicu liczy się data wpisana przez użytkownika.
  if (edycja && !stan.formularz.zatwierdzony && !(dataKierujacego in dane.pola)) {
    dane.pola = { ...dane.pola, [dataKierujacego]: null };
  }
  return dane;
}

function Formularz({
  stan,
  token,
  osoba,
  edycja,
  onZapisano,
  przelozony,
  onZmienOcene,
  onWstecz,
  rozmowa,
  zakonczony,
}: {
  przelozony?: Pracownik;
  onZmienOcene?: () => void;
  stan: StanPierwszejOceny;
  token: string;
  osoba: Pracownik;
  edycja: boolean;
  onWstecz: () => void;
  rozmowa: ZRozmowy | null;
  zakonczony: boolean;
  onZapisano: (s: StanPierwszejOceny) => void;
}) {
  const poczatkowe = daneFormularza(stan, edycja);
  const [d, setD] = useState<DanePierwszej>(() => edycja && !stan.formularz.zatwierdzony ? {
    ...poczatkowe,
    data_rozmowy_oceniajacej: poczatkowe.data_rozmowy_oceniajacej ?? rozmowa?.data ?? null,
    data_sporzadzenia_oceny: poczatkowe.data_sporzadzenia_oceny ?? dzienZapisu(new Date()),
    wnioski_rozwojowe: stan.wnioski_dostepne && !poczatkowe.wnioski_rozwojowe?.trim()
      ? rozmowa?.wnioski ?? null : poczatkowe.wnioski_rozwojowe,
    pola: { ...poczatkowe.pola, ...podpowiedziPol(stan.formularz, przelozony) },
  } : poczatkowe);
  const [braki, setBraki] = useState<BrakArkusza[]>(stan.formularz.braki);
  const [sprawdzoneDane, setSprawdzoneDane] = useState(stan.dane);
  const [czekam, setCzekam] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  // Zakończenie (§ 11 ust. 1): datę zapoznania wpisuje się po podpisie ocenianego na wydruku, więc pole startuje puste.
  const [dataZapoznania, setDataZapoznania] = useState<string | null>(null);
  const [zakonczono, setZakonczono] = useState<string | null>(null);
  const ustaw = (z: Partial<DanePierwszej>) => setD((p) => ({ ...p, ...z }));
  const ustawWnioski = (tekst: string) => ustaw({ wnioski_rozwojowe: tekst || null });
  const egz = d.egzamin;
  const prz = d.przedluzenie;
  const ustawPrz = (z: Partial<PrzedluzeniePierwszej>) =>
    ustaw({ przedluzenie: { ...(prz as PrzedluzeniePierwszej), ...z } });
  const sprawozdanie = d.sprawozdanie ?? PUSTE_SPRAWOZDANIE;

  const t = stan.terminy;
  const terminy: [string, Termin][] = [];
  for (const [k, nazwa] of Object.entries(NAZWY_TERMINOW)) {
    const v = t[k];
    if (v && typeof v === "object" && "data" in v) terminy.push([nazwa, v]);
  }
  const terminyBraki: Brak[] = t.braki.map((tekst) => {
    const cel = tekst.includes("początku lub końca")
      ? (d.sprawozdanie_okres_od ? "sprawozdanie_okres_do" : "sprawozdanie_okres_od")
      : tekst.includes("końca zatrudnienia")
        ? "data_konca_zatrudnienia"
        : tekst.includes("zastępstwo")
          ? "data_ustalenia_oceny_zastepstwa"
          : tekst.includes("rozmowy wstępnej")
            ? "data_rozmowy_wstepnej"
            : tekst.includes("wyznaczonej")
              ? "wyznaczony_termin_sprawozdania"
              : "data_zlozenia_sprawozdania";
    return { tekst: `Terminy: ${tekst}`, cel, grupa: grupaDaty(cel), tylkoTermin: true };
  }).filter((b) => !(d[b.cel as keyof DanePierwszej] && !stan.dane[b.cel as keyof DanePierwszej]));
  const brakDaty = (cel: string, tekst: string, grupa: string): Brak => ({
    cel,
    tekst: `${grupa === "wyjatki" ? "Pozostałe daty i wyjątki" : grupa === "raport" ? "Sprawozdanie" : "Daty oceny"}: ${tekst}`,
    grupa,
    opis: "Podaj datę w formacie RRRR-MM-DD.",
  });
  const lokalne: Brak[] = [];
  for (const [k, nazwa, grupa] of DATY) {
    if (!poprawnaData(d[k])) lokalne.push(brakDaty(k, nazwa, grupa));
  }
  if (prz) {
    for (const [k, nazwa] of [
      ["nowy_termin", "Nowy termin"],
      ["data_zawiadomienia", "Data zawiadomienia"],
      ["okres_od", "Nieobecność od"],
      ["okres_do", "Nieobecność do"],
      ["nowy_termin_od", "Nowy początek terminu"],
    ] as const) {
      if (!poprawnaData(prz[k]) || (!prz[k] && (k === "nowy_termin" || k === "data_zawiadomienia"))) {
        lokalne.push(brakDaty("prz-" + k, nazwa, "wyjatki"));
      }
    }
  }
  if (egz?.wynik === "nie_dotyczy" && !egz.przeslanka)
    lokalne.push({ tekst: "Przesłanka dla egzaminu", cel: "przeslanka", grupa: "egzamin-sekcja" });
  if (!d.sprawozdanie_niezlozone && Object.values(sprawozdanie).some((v) => v.trim())) {
    for (const [k, nazwa] of SPRAWOZDANIE) {
      if (!sprawozdanie[k].trim())
        lokalne.push({
          tekst: `Sprawozdanie: ${nazwa.toLowerCase()}`,
          cel: "sprawozdanie-" + k,
          grupa: "raport",
        });
    }
  }
  const uzasadnienieWymagane = stan.uzasadnienie_wymagane || braki.some((b) => b.id === "uzasadnienie");
  if (uzasadnienieWymagane && !d.uzasadnienie?.trim()) lokalne.push({ tekst: "Uzasadnienie oceny", cel: "uzasadnienie" });

  const celeDat: Record<string, (typeof DATY)[number][0]> = {
    "rozmowa_wstepna.data": "data_rozmowy_wstepnej",
    "termin_sprawozdania.od": "termin_sprawozdania_od",
    "termin_sprawozdania.do": "wyznaczony_termin_sprawozdania",
    "okres_pierwszej_oceny.do": "data_konca_zatrudnienia",
    "dokonanie_oceny.przelozony.data": "data_sporzadzenia_oceny",
    "rozmowa_oceniajaca.data": "data_rozmowy_oceniajacej",
    sprawozdanie_okres: "sprawozdanie_okres_od",
    sprawozdanie_w_terminie: "data_zlozenia_sprawozdania",
    data_zlozenia_sprawozdania: "data_zlozenia_sprawozdania",
  };
  function dataPola(id: string) {
    if (id.startsWith("potwierdzenie_rozmowy") && id.endsWith(".data")) {
      return id.includes("wstepnej") ? "data_rozmowy_wstepnej" : "data_rozmowy_oceniajacej";
    }
    return celeDat[id];
  }
  const polaWzoru = stan.formularz.sekcje.flatMap((s) => s.pola);
  // API powtarza datę sporządzenia przy kierującym. Do pól podpisu nie wpisujemy domyślnej daty.
  const dataKierujacego = "dokonanie_oceny.kierujacy.data";
  const polaBraki = brakiPol(
    stan.formularz,
    { ...d.pola, [dataKierujacego]: d.pola[dataKierujacego] || d.data_sporzadzenia_oceny },
    braki.filter((b) => {
      if (b.id === "aktualne_decyzje") return false;
      if (b.id === "sprawozdanie" && (d.sprawozdanie_niezlozone || Object.values(sprawozdanie).every((v) => v.trim()))) return false;
      if (b.id === "sprawozdanie_okres" && (d.sprawozdanie_okres_od !== sprawdzoneDane.sprawozdanie_okres_od ||
        d.sprawozdanie_okres_do !== sprawdzoneDane.sprawozdanie_okres_do)) return false;
      const k = dataPola(b.id);
      return !k || d[k] === sprawdzoneDane[k] || !d[k] || b.komunikat.startsWith("Uzupełnij pole");
    }),
    (b) => {
      if (b.id === "uzasadnienie") return { cel: "uzasadnienie", grupa: undefined };
      if (b.id === "wnioski_rozwojowe") return { cel: "wnioski_rozwojowe", grupa: undefined };
      if (b.id === "sprawozdanie")
        return { cel: d.sprawozdanie_niezlozone ? "sprawozdanie" : "sprawozdanie-zadania", grupa: "raport" };
      if (b.id === "egzamin") return { cel: "egzamin", grupa: "egzamin-sekcja" };
      const cel = dataPola(b.id);
      if (cel) return { cel, grupa: grupaDaty(cel) };
    },
    (p) => {
      const k = dataPola(p.id);
      if (k && p.id.endsWith(".data") && (d[k] !== poczatkowe[k] || !p.wartosc)) return d[k];
      if (p.id === "uzasadnienie") return d.uzasadnienie;
      if (p.id === "wnioski_rozwojowe") return d.wnioski_rozwojowe;
      if (p.id === "egzamin") return egz?.wynik;
      if (p.id.endsWith(".imie_nazwisko_lub_pieczatka") && !p.wartosc) {
        const osoba = p.id.includes(".kierujacy.") ? "kierujacy_komorka" : p.id.includes(".przelozony.") ? "bezposredni_przelozony" : "oceniany";
        const czesci = ["imie", "nazwisko"].map((k) => {
          const id = osoba + "." + k;
          return id in d.pola ? d.pola[id] : polaWzoru.find((x) => x.id === id)?.wartosc;
        });
        if (czesci.every((v) => v?.trim())) return czesci.join(" ");
      }
    },
  );
  const lista = [...lokalne, ...polaBraki, ...terminyBraki];
  const ruszone = JSON.stringify(d) !== JSON.stringify(poczatkowe) || braki.some((b) => b.id === "aktualne_decyzje");
  const edytowalne = polaWzoru.filter((p) => p.edytowalne);
  const zlaDataPola = edytowalne.some(
    (p) => p.rodzaj === "data" && !poprawnaData(p.id in d.pola ? d.pola[p.id] : p.wartosc),
  );
  function polaDat(grupa: "daty" | "raport" | "wyjatki") {
    return (
      <fieldset className="formularz" disabled={!edycja || czekam}>
        <div className="siatka-dat">
          {DATY.filter(([, , g]) => g === grupa).map(([k, nazwa]) => (
            <PoleDaty key={k} id={k} nazwa={nazwa} wartosc={d[k]} onZmiana={(v) => ustaw({ [k]: v })} />
          ))}
        </div>
      </fieldset>
    );
  }
  const blokadaZapisu = !edycja || czekam || lokalne.length > 0 || zlaDataPola;
  const blokadaZatwierdzenia = blokadaZapisu || polaBraki.length > 0;
  const pdf = !czekam && !ruszone && stan.formularz.pdf_dostepny && !lista.some((b) => !b.tylkoTermin);
  const zatwierdzony = stan.formularz.zatwierdzony && !ruszone;
  const oceny = polaWzoru.filter((p) => p.widoczne && p.id.startsWith("ocena_czastkowa.") && p.wartosc);
  const warunki = stan.warunki.map((w) => {
    if (w.spelniony || !["pierwsza-limit-trojek", "pierwsza-minimum-sredniej"].includes(w.id)) return w;
    const kryteria = w.id === "pierwsza-limit-trojek" ? oceny.filter((p) => Number(p.wartosc) === Math.min(...p.warianty.map(Number))) : oceny;
    return { ...w, szczegoly: kryteria.map((p) => `${nazwaKryterium(p.etykieta)}: ${p.wartosc} pkt`).join(", ") };
  });
  const takNie = (v: unknown) => (v == null ? "jeszcze nie ustalono" : v ? "tak" : "nie");

  async function zapisz(zatwierdz: boolean) {
    if (blokadaZapisu || (zatwierdz && blokadaZatwierdzenia)) return;
    setCzekam(true);
    setBlad(null);
    try {
      const pola = Object.fromEntries(edytowalne.map((p) => [
        p.id, p.id in d.pola ? d.pola[p.id] : p.rodzaj === "data" ? null : p.wartosc,
      ]));
      const po = await zapiszPierwsza(token, stan.proces_id, doZapisu({
        ...zachowajDateZapoznania(d, stan.dane.data_zapoznania_z_ocena),
        pola, wnioski_rozwojowe: stan.wnioski_dostepne ? d.wnioski_rozwojowe : null,
      }), zatwierdz);
      const poZapisie = daneFormularza(po, edycja);
      if (!stan.wnioski_dostepne && po.wnioski_dostepne && !po.formularz.zatwierdzony && !poZapisie.wnioski_rozwojowe?.trim()) {
        poZapisie.wnioski_rozwojowe = rozmowa?.wnioski ?? null;
      }
      setD(poZapisie);
      setSprawdzoneDane(po.dane);
      setBraki(po.formularz.braki);
      onZapisano(po);
    } catch (err) {
      const b = bladArkusza(err);
      setBlad(b.tekst);
      if (b.braki) {
        setSprawdzoneDane(d);
        setBraki(b.braki);
      }
    } finally {
      setCzekam(false);
    }
  }
  async function zakoncz(dzien: string) {
    if (czekam) return;
    setBlad(null);
    setCzekam(true);
    try {
      await zakonczPierwsza(token, stan.proces_id, dzien);
      setZakonczono(dzien);
    } catch (err) {
      setBlad(bladArkusza(err).tekst);
    } finally {
      setCzekam(false);
    }
  }
  async function pobierz(plik: "arkusz.pdf" | "zawiadomienie.pdf", doDruku = false) {
    if (czekam || (plik === "arkusz.pdf" ? !pdf : !stan.zawiadomienie_dostepne || ruszone)) return;
    setBlad(null);
    setCzekam(true);
    try {
      const nazwa = `${plik === "arkusz.pdf" ? "arkusz-pierwszej-oceny" : "zawiadomienie-5"}-${osoba.nazwisko}.pdf`;
      if (doDruku) await drukujDoPodpisu(() => pobierzPdfPierwszej(token, stan.proces_id, plik), nazwa);
      else zapiszPlik(await pobierzPdfPierwszej(token, stan.proces_id, plik), nazwa);
    } catch (err) {
      const b = bladArkusza(err);
      setBlad(b.tekst);
      if (b.braki) setBraki(b.braki);
    } finally {
      setCzekam(false);
    }
  }
  const edycjaPol = {
    formularz: stan.formularz, wartosci: d.pola, braki: lista, edycja: edycja && !czekam,
    ustaw: (id: string, v: string | null) => ustaw({ pola: { ...d.pola, [id]: v } }),
  };
  return (
    <Podsumowanie
      key={JSON.stringify(braki)}
      braki={lista}
      blad={blad}
      onWstecz={onWstecz}
      dzieci={
        <>
          <PoleOpisowe id="uzasadnienie" etykieta={`Uzasadnienie oceny ${uzasadnienieWymagane ? "(wymagane)" : "(opcjonalnie)"}`}
            wartosc={d.uzasadnienie} wymagane={uzasadnienieWymagane} blokada={!edycja || czekam} wiersze={3}
            szkicZRozmowy={rozmowa?.szkicUzasadnienia}
            onZmiana={(tekst) => ustaw({ uzasadnienie: tekst || null })} />
          {stan.wnioski_dostepne && (
            <div className="sekcja">
              <PoleOpisowe id="wnioski_rozwojowe" etykieta="Wnioski rozwojowe" wartosc={d.wnioski_rozwojowe}
                blokada={!edycja || czekam} wiersze={5} onZmiana={ustawWnioski} />
              {edycja && <PropozycjeZwarte token={token} procesId={stan.proces_id}
                wartosc={d.wnioski_rozwojowe} blokada={czekam} onZmiana={ustawWnioski} />}
            </div>
          )}
          <TabelaTerminow terminy={terminy} slad={t.slad}>
            {typeof t.data_rozmowy_wstepnej === "string" && (
              <p>Rozmowa wstępna odbyła się {data(t.data_rozmowy_wstepnej)}.</p>
            )}
            <p>
              Sprawozdanie w terminie: {takNie(t.sprawozdanie_w_terminie)}. Obejmuje co najmniej 7 miesięcy:{" "}
              {takNie(t.sprawozdanie_min_7_miesiecy)}.
            </p>
            {t.uwagi.map((u) => (
              <p className="meta" key={u}>
                {u}
              </p>
            ))}
          </TabelaTerminow>
          <Sekcja id="daty" tytul="Daty (z wcześniejszych kroków)">
            {polaDat("daty")}
            <DatyWzoru {...edycjaPol} />
          </Sekcja>
          <Sekcja id="raport" tytul="Sprawozdanie">
            {polaDat("raport")}
            <fieldset className="formularz" disabled={!edycja || czekam}>
              <label className="zaznacz">
                <input
                  id="sprawozdanie"
                  type="checkbox"
                  checked={d.sprawozdanie_niezlozone}
                  onChange={(e) => ustaw({ sprawozdanie_niezlozone: e.target.checked })}
                />
                <span>Sprawozdanie nie zostało złożone</span>
              </label>
              {!d.sprawozdanie_niezlozone &&
                SPRAWOZDANIE.map(([k, nazwa]) => (
                  <label key={k} className="etykieta">
                    Sprawozdanie: {nazwa.toLowerCase()}
                    <textarea
                      id={"sprawozdanie-" + k}
                      rows={2}
                      value={sprawozdanie[k]}
                      onChange={(e) => ustaw({ sprawozdanie: { ...sprawozdanie, [k]: e.target.value } })}
                    />
                    <BladPola cel={"sprawozdanie-" + k} />
                  </label>
                ))}
            </fieldset>
          </Sekcja>
          <Sekcja id="egzamin-sekcja" tytul="Egzamin">
            <fieldset id="egzamin" tabIndex={-1} className="formularz" disabled={!edycja || czekam}>
              <div className="etykieta">Egzamin kończący służbę przygotowawczą</div>
              <Wybor
                etykieta="Egzamin"
                opcje={EGZAMIN.map((o) => ({ ...o }))}
                wartosc={egz?.wynik ?? null}
                zablokowane={!edycja || czekam}
                onWybierz={(w) => ustaw({ egzamin: w ? ({ wynik: w, przeslanka: null } as EgzaminPierwszej) : null })}
              />
              <BladPola cel="egzamin" />
              {egz?.wynik === "nie_dotyczy" && (
                <>
                  <div id="przeslanka" tabIndex={-1} className="etykieta">
                    Przesłanka z § 10 ust. 3 (wymagana)
                  </div>
                  <Wybor
                    etykieta="Przesłanka egzaminu"
                    opcje={(Object.keys(PRZESLANKI) as PrzeslankaEgzaminu[]).map((w) => ({
                      wartosc: w,
                      tekst: PRZESLANKI[w],
                    }))}
                    wartosc={egz.przeslanka}
                    zablokowane={!edycja || czekam}
                    onWybierz={(w) => ustaw({ egzamin: { wynik: "nie_dotyczy", przeslanka: w } })}
                  />
                  {!egz.przeslanka && <p className="blad">Wskaż przesłankę dla „nie dotyczy”.</p>}
                </>
              )}
            </fieldset>
            {egz?.wynik === "nie_dotyczy" && egz.przeslanka && (
              <Zrodla adnotacje={[stan.przeslanki_egzaminu[egz.przeslanka]]} />
            )}
          </Sekcja>
          <Sekcja id="wyjatki" tytul="Pozostałe daty i wyjątki">
            {polaDat("wyjatki")}
            <fieldset className="formularz" disabled={!edycja || czekam}>
              <label className="zaznacz">
                <input
                  type="checkbox"
                  checked={prz !== null}
                  onChange={(e) =>
                    ustaw({
                      przedluzenie: e.target.checked
                        ? {
                            nowy_termin: "",
                            data_zawiadomienia: "",
                            przyczyna: "usprawiedliwiona_nieobecnosc",
                            okres_od: null,
                            okres_do: null,
                            nowy_termin_od: null,
                          }
                        : null,
                    })
                  }
                />
                <span>Przedłużenie terminu sprawozdania (zawiadomienie § 5)</span>
              </label>
              {prz && (
                <div className="nowy-przyklad">
                  <div className="siatka-dat">
                    <PoleDaty
                      id="prz-nowy_termin"
                      nazwa="Nowy termin"
                      wartosc={prz.nowy_termin || null}
                      onZmiana={(v) => ustawPrz({ nowy_termin: v ?? "" })}
                    />
                    <PoleDaty
                      id="prz-data_zawiadomienia"
                      nazwa="Data zawiadomienia"
                      wartosc={prz.data_zawiadomienia || null}
                      onZmiana={(v) => ustawPrz({ data_zawiadomienia: v ?? "" })}
                    />
                    <PoleDaty
                      id="prz-okres_od"
                      nazwa="Nieobecność od"
                      wartosc={prz.okres_od}
                      onZmiana={(v) => ustawPrz({ okres_od: v })}
                    />
                    <PoleDaty
                      id="prz-okres_do"
                      nazwa="Nieobecność do"
                      wartosc={prz.okres_do}
                      onZmiana={(v) => ustawPrz({ okres_do: v })}
                    />
                    <PoleDaty
                      id="prz-nowy_termin_od"
                      nazwa="Nowy początek terminu"
                      wartosc={prz.nowy_termin_od}
                      onZmiana={(v) => ustawPrz({ nowy_termin_od: v })}
                    />
                  </div>
                  <div className="etykieta">Przyczyna</div>
                  <Wybor
                    etykieta="Przyczyna przedłużenia"
                    opcje={(Object.keys(PRZYCZYNY) as PrzedluzeniePierwszej["przyczyna"][]).map((w) => ({
                      wartosc: w,
                      tekst: PRZYCZYNY[w],
                    }))}
                    wartosc={prz.przyczyna}
                    zablokowane={!edycja || czekam}
                    onWybierz={(w) => w && ustawPrz({ przyczyna: w })}
                  />
                </div>
              )}
            </fieldset>
          </Sekcja>
          <PolaWzoru
            {...edycjaPol}
            ustawWiele={(pola) => ustaw({ pola: { ...d.pola, ...pola } })}
          />
          <Sekcja id="obliczenie" tytul="Jak policzono wynik">
            <p>Skala pierwszej oceny: 3, 5 lub 7 pkt.</p>
            <p>
              Poziomy modelu i odpowiadające im punkty:{" "}
              {Object.entries(stan.mapowanie.wartosci)
                .map(([z, na]) => `${z} → ${na}`)
                .join(", ")}
              .
            </p>
            <Zrodla adnotacje={stan.mapowanie.adnotacje} />
            {stan.obliczenie && <Slad slad={stan.obliczenie.slad} />}
          </Sekcja>
        </>
      }
      bok={
        <>
          <Werdykt wynik={stan.obliczenie} warunki={warunki} onZmienOcene={edycja ? onZmienOcene : undefined} />
          {!stan.obliczenie && (
            <p className="meta">Do wyliczenia wyniku potrzebne są oceny cząstkowe, dane sprawozdania i egzaminu.</p>
          )}
          {zakonczono ? (
            <p className="sukces">
              Ocena zakończona: zapoznanie z oceną {data(zakonczono)}. Oryginał wraz ze sprawozdaniem trafia do akt, kopia do ocenianego (§ 11 ust. 2).
            </p>
          ) : zatwierdzony && (
            <>
              <p className="sukces">Arkusz zatwierdzony. Wydrukuj go do podpisu i zapoznaj ocenianego z oceną (§ 11 ust. 1).</p>
              {edycja && !zakonczony && (
                <>
                  <PoleDaty id="data-zapoznania" nazwa="Data zapoznania ocenianego z oceną" wartosc={dataZapoznania} onZmiana={setDataZapoznania} />
                  <button
                    type="button"
                    className="jasny"
                    disabled={czekam || !dataZapoznania || !poprawnaData(dataZapoznania)}
                    onClick={() => dataZapoznania && zakoncz(dataZapoznania)}
                  >
                    Zakończ ocenę
                  </button>
                </>
              )}
            </>
          )}
        </>
      }
      akcje={
        <>
          <div id="zapis" tabIndex={-1}>
            {edycja ? (
              <button type="button" className="jasny" disabled={blokadaZapisu} onClick={() => zapisz(false)}>
                Zapisz szkic
              </button>
            ) : (
              <span className="meta">Arkusz uzupełnia przełożony.</span>
            )}
          </div>
          {stan.formularz.pdf_dostepny && edycja && !zatwierdzony && (
            <button type="button" className="link" disabled={!pdf} onClick={() => pobierz("arkusz.pdf")}>
              Pobierz zapisany arkusz (PDF)
            </button>
          )}
          {stan.zawiadomienie_dostepne && (
            <button type="button" className="link" disabled={czekam || ruszone} onClick={() => pobierz("zawiadomienie.pdf")}>
              Pobierz zawiadomienie § 5 (PDF)
            </button>
          )}
        </>
      }
      glowna={
        zakonczony || zakonczono ? (
          <div className="k7-zakonczona"><strong>Ocena zakończona</strong>
            {pdf && <button type="button" onClick={() => pobierz("arkusz.pdf")}>Pobierz arkusz (PDF)</button>}
          </div>
        ) : zatwierdzony || !edycja ? (
          <span className="k7-zakonczona">
            <button type="button" className="link" disabled={!pdf} onClick={() => pobierz("arkusz.pdf")}>Pobierz PDF</button>
            <button type="button" disabled={!pdf} onClick={() => pobierz("arkusz.pdf", true)}>Drukuj do podpisu</button>
          </span>
        ) : (
          <button type="button" disabled={blokadaZatwierdzenia} onClick={() => zapisz(true)}>
            Zatwierdź arkusz
          </button>
        )
      }
    />
  );
}

export function Pierwsza({ token, osoba, proces, moznaProwadzic, onWstecz, onZmienOcene, zalogowanyId }: Krok7Props) {
  const zakonczony = proces.status !== "W_TOKU";
  const edycja = moznaProwadzic && !zakonczony;
  const [rozmowa, setRozmowa] = useState<ZRozmowy | null>(null);
  const [przelozony, setPrzelozony] = useState<Pracownik>();
  const [stan, setStan] = useState<StanPierwszejOceny | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  useEffect(() => {
    let aktywny = true;
    setStan(null);
    setBlad(null);
    Promise.all([
      pobierzPierwsza(token, proces.id),
      edycja ? pobierzPrzelozonego(token, osoba, zalogowanyId).catch(() => undefined) : undefined,
      edycja ? zRozmowy(token, proces.id).catch(() => null) : null,
    ])
      .then(([s, kierownik, dzien]) => {
        if (aktywny) {
          setRozmowa(dzien);
          setPrzelozony(kierownik);
          setStan(s);
        }
      })
      .catch((err) => {
        if (aktywny) setBlad(bladArkusza(err).tekst);
      });
    return () => {
      aktywny = false;
    };
  }, [token, proces.id, edycja, osoba, zalogowanyId]);
  return (
    <div className="oc-ekran k7">
      <Naglowek
        osoba={osoba}
        tytul="Zakończenie oceny"
        opis="Pierwsza ocena · części III–VI arkusza z załącznika nr 2"
        wstecz="Wróć do rozmowy"
        onWstecz={onWstecz}
      />
      {stan && stan.proces_id === proces.id ? (
        <Formularz
          key={proces.id}
          stan={stan}
          token={token}
          osoba={osoba}
          edycja={edycja}
          przelozony={przelozony}
          onZmienOcene={onZmienOcene}
          onZapisano={setStan}
          onWstecz={onWstecz}
          rozmowa={rozmowa}
          zakonczony={zakonczony}
        />
      ) : (
        <Wczytywanie blad={blad} />
      )}
    </div>
  );
}
