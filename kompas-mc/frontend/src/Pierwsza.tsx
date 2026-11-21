import { useEffect, useState } from "react";
import {
  pobierzPdfPierwszej,
  pobierzPierwsza,
  zapiszPierwsza,
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
import { PolaWzoru, bladArkusza, brakiPol } from "./Arkusz";
import { Zrodla } from "./Krok1";
import { Wybor } from "./Ocena";
import {
  Naglowek,
  Podsumowanie,
  PoleDaty,
  Sekcja,
  Slad,
  TabelaTerminow,
  Wczytywanie,
  Werdykt,
  data,
  poprawnaData,
  zapiszPlik,
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

function Formularz({
  stan,
  token,
  osoba,
  edycja,
  onZapisano,
  onWstecz,
  onDalej,
}: {
  stan: StanPierwszejOceny;
  token: string;
  osoba: Pracownik;
  edycja: boolean;
  onWstecz: () => void;
  onDalej: () => void;
  onZapisano: (s: StanPierwszejOceny) => void;
}) {
  const poczatkowe = { ...stan.dane, egzamin: stan.dane.egzamin ?? stan.egzamin };
  const [d, setD] = useState<DanePierwszej>(poczatkowe);
  const [braki, setBraki] = useState<BrakArkusza[]>(stan.formularz.braki);
  const [czekam, setCzekam] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const ustaw = (z: Partial<DanePierwszej>) => setD((p) => ({ ...p, ...z }));
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
      ? "sprawozdanie_okres_od"
      : tekst.includes("końca zatrudnienia")
        ? "data_konca_zatrudnienia"
        : tekst.includes("zastępstwo")
          ? "data_ustalenia_oceny_zastepstwa"
          : tekst.includes("rozmowy wstępnej")
            ? "data_rozmowy_wstepnej"
            : tekst.includes("wyznaczonej")
              ? "wyznaczony_termin_sprawozdania"
              : "data_zlozenia_sprawozdania";
    return { tekst, cel, grupa: "dane/daty", tylkoTermin: true };
  });
  const brakDaty = (cel: string, tekst: string, grupa: string): Brak => ({
    cel,
    tekst,
    grupa,
    opis: "Podaj datę w formacie RRRR-MM-DD.",
  });
  const lokalne: Brak[] = [];
  for (const [k, nazwa] of DATY) {
    if (!poprawnaData(d[k] as string | null)) lokalne.push(brakDaty(k, nazwa, "dane/daty"));
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
        lokalne.push(brakDaty("prz-" + k, nazwa, "dane/przedluzenie"));
      }
    }
  }
  if (egz?.wynik === "nie_dotyczy" && !egz.przeslanka)
    lokalne.push({ tekst: "Przesłanka dla egzaminu", cel: "przeslanka", grupa: "dane/egzamin" });
  if (!d.sprawozdanie_niezlozone && Object.values(sprawozdanie).some((v) => v.trim())) {
    for (const [k, nazwa] of SPRAWOZDANIE) {
      if (!sprawozdanie[k].trim())
        lokalne.push({
          tekst: `Sprawozdanie: ${nazwa.toLowerCase()}`,
          cel: "sprawozdanie-" + k,
          grupa: "dane/sprawozdanie",
        });
    }
  }
  const uzasadnienieWymagane = stan.uzasadnienie_wymagane || braki.some((b) => b.id === "uzasadnienie");
  if (uzasadnienieWymagane && !d.uzasadnienie?.trim()) lokalne.push({ tekst: "Uzasadnienie oceny", cel: "uzasadnienie" });

  const celeDat: Record<string, string> = {
    "rozmowa_wstepna.data": "data_rozmowy_wstepnej",
    "termin_sprawozdania.od": "termin_sprawozdania_od",
    "termin_sprawozdania.do": "wyznaczony_termin_sprawozdania",
    "okres_pierwszej_oceny.do": "data_konca_zatrudnienia",
    "dokonanie_oceny.przelozony.data": "data_sporzadzenia_oceny",
    "rozmowa_oceniajaca.data": "data_rozmowy_oceniajacej",
    "zapoznanie.oceniany.data": "data_zapoznania_z_ocena",
    sprawozdanie_okres: "sprawozdanie_okres_od",
    sprawozdanie_w_terminie: "data_zlozenia_sprawozdania",
    data_zlozenia_sprawozdania: "data_zlozenia_sprawozdania",
  };
  const polaBraki = brakiPol(
    stan.formularz,
    d.pola,
    braki.filter((b) => b.id !== "uzasadnienie"),
    (b) => {
      if (b.id === "aktualne_decyzje") return { cel: "zapis", grupa: undefined };
      if (b.id === "sprawozdanie")
        return { cel: d.sprawozdanie_niezlozone ? "sprawozdanie" : "sprawozdanie-zadania", grupa: "dane/sprawozdanie" };
      if (b.id === "egzamin") return { cel: "egzamin", grupa: "dane/egzamin" };
      const cel =
        celeDat[b.id] ??
        (b.id.endsWith(".data") && b.id.startsWith("potwierdzenie_rozmowy")
          ? b.id.includes("wstepnej")
            ? "data_rozmowy_wstepnej"
            : "data_rozmowy_oceniajacej"
          : null);
      if (cel) return { cel, grupa: "dane/daty" };
    },
  );
  const lista = [...lokalne, ...polaBraki, ...terminyBraki];
  const ruszone = JSON.stringify(d) !== JSON.stringify(poczatkowe);
  const edytowalne = stan.formularz.sekcje.flatMap((s) => s.pola).filter((p) => p.edytowalne);
  const zlaDataPola = edytowalne.some(
    (p) => p.rodzaj === "data" && !poprawnaData(p.id in d.pola ? d.pola[p.id] : p.wartosc),
  );
  const blokadaZapisu = !edycja || czekam || lokalne.length > 0 || zlaDataPola;
  const blokadaZatwierdzenia = blokadaZapisu || polaBraki.length > 0;
  const pdf = !czekam && !ruszone && stan.formularz.pdf_dostepny && !lista.some((b) => !b.tylkoTermin);
  const zatwierdzony = stan.formularz.zatwierdzony && !ruszone;
  const takNie = (v: unknown) => (v == null ? "jeszcze nie ustalono" : v ? "tak" : "nie");

  async function zapisz(zatwierdz: boolean) {
    if (blokadaZapisu || (zatwierdz && blokadaZatwierdzenia)) return;
    setCzekam(true);
    setBlad(null);
    try {
      const po = await zapiszPierwsza(token, stan.proces_id, doZapisu(d), zatwierdz);
      setD({ ...po.dane, egzamin: po.dane.egzamin ?? po.egzamin });
      setBraki(po.formularz.braki);
      onZapisano(po);
    } catch (err) {
      const b = bladArkusza(err);
      setBlad(b.tekst);
      if (b.braki) setBraki(b.braki);
    } finally {
      setCzekam(false);
    }
  }
  async function pobierz(plik: "arkusz.pdf" | "zawiadomienie.pdf") {
    if (czekam || (plik === "arkusz.pdf" ? !pdf : !stan.zawiadomienie_dostepne || ruszone)) return;
    setBlad(null);
    setCzekam(true);
    try {
      zapiszPlik(
        await pobierzPdfPierwszej(token, stan.proces_id, plik),
        `${plik === "arkusz.pdf" ? "arkusz-pierwszej-oceny" : "zawiadomienie-5"}-${osoba.nazwisko}.pdf`,
      );
    } catch (err) {
      const b = bladArkusza(err);
      setBlad(b.tekst);
      if (b.braki) setBraki(b.braki);
    } finally {
      setCzekam(false);
    }
  }
  return (
    <Podsumowanie
      key={JSON.stringify(braki)}
      braki={lista}
      blad={blad}
      podpis={stan.formularz.komunikat_podpis}
      onWstecz={onWstecz}
      dzieci={
        <>
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
          <Sekcja id="dane" tytul="Daty i dane">
            <Sekcja id="dane/daty" tytul="Daty oceny i sprawozdania">
              <fieldset className="formularz" disabled={!edycja || czekam}>
                <div className="siatka-dat">
                  {DATY.map(([k, nazwa]) => (
                    <PoleDaty
                      key={k}
                      id={k}
                      nazwa={nazwa}
                      wartosc={d[k] as string | null}
                      onZmiana={(v) => ustaw({ [k]: v } as Partial<DanePierwszej>)}
                    />
                  ))}
                </div>
              </fieldset>
            </Sekcja>
            <Sekcja id="dane/sprawozdanie" tytul="Sprawozdanie">
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
                    </label>
                  ))}
              </fieldset>
            </Sekcja>
            <Sekcja id="dane/egzamin" tytul="Egzamin">
              <fieldset id="egzamin" tabIndex={-1} className="formularz" disabled={!edycja || czekam}>
                <div className="etykieta">Egzamin kończący służbę przygotowawczą</div>
                <Wybor
                  etykieta="Egzamin"
                  opcje={EGZAMIN.map((o) => ({ ...o }))}
                  wartosc={egz?.wynik ?? null}
                  zablokowane={!edycja || czekam}
                  onWybierz={(w) => ustaw({ egzamin: w ? ({ wynik: w, przeslanka: null } as EgzaminPierwszej) : null })}
                />
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
            <Sekcja id="dane/przedluzenie" tytul="Przedłużenie terminu">
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
          </Sekcja>
          <PolaWzoru
            formularz={stan.formularz}
            wartosci={d.pola}
            braki={lista}
            edycja={edycja && !czekam}
            ustaw={(id, v) => ustaw({ pola: { ...d.pola, [id]: v } })}
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
            {stan.obliczenie && (
              <>
                <Slad slad={stan.obliczenie.slad} />
                <Zrodla adnotacje={[stan.obliczenie.regula_rozstrzygajaca.zrodlo]} />
              </>
            )}
          </Sekcja>
        </>
      }
      bok={
        <>
          <Werdykt wynik={stan.obliczenie} warunki={stan.warunki} />
          {!stan.obliczenie && (
            <p className="meta">Do wyliczenia wyniku potrzebne są oceny cząstkowe, dane sprawozdania i egzaminu.</p>
          )}
          <label className="etykieta">
            Uzasadnienie {uzasadnienieWymagane ? "(wymagane)" : "(opcjonalnie)"}
            <textarea
              id="uzasadnienie"
              rows={3}
              required={uzasadnienieWymagane}
              disabled={!edycja || czekam}
              value={d.uzasadnienie ?? ""}
              onChange={(e) => ustaw({ uzasadnienie: e.target.value || null })}
            />
          </label>
          <Zrodla adnotacje={[stan.podstawa_uzasadnienia]} />
          {stan.wnioski_dostepne && (
            <div>
              <label className="etykieta">
                Wnioski rozwojowe
                <textarea
                  rows={3}
                  disabled={!edycja || czekam}
                  value={d.wnioski_rozwojowe ?? ""}
                  onChange={(e) => ustaw({ wnioski_rozwojowe: e.target.value || null })}
                />
              </label>
              <Zrodla adnotacje={[stan.podstawa_wnioskow]} />
            </div>
          )}
          {zatwierdzony && <p className="sukces">Arkusz zatwierdzony.</p>}
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
          {ruszone && <span className="meta">Masz niezapisane zmiany. Zapisz szkic, żeby przeliczyć wynik i terminy.</span>}
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
          {stan.wnioski_dostepne && (
            <button type="button" className="link" onClick={onDalej}>
              Dalej: wnioski rozwojowe
            </button>
          )}
        </>
      }
      glowna={
        zatwierdzony || !edycja ? (
          <button type="button" disabled={!pdf} onClick={() => pobierz("arkusz.pdf")}>
            Pobierz arkusz (PDF)
          </button>
        ) : (
          <button type="button" disabled={blokadaZatwierdzenia} onClick={() => zapisz(true)}>
            Zatwierdź arkusz
          </button>
        )
      }
    />
  );
}

export function Pierwsza({ token, osoba, proces, moznaProwadzic, onWstecz, onDalej }: Krok7Props) {
  const [stan, setStan] = useState<StanPierwszejOceny | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  useEffect(() => {
    let aktywny = true;
    setStan(null);
    setBlad(null);
    pobierzPierwsza(token, proces.id)
      .then((s) => {
        if (aktywny) setStan(s);
      })
      .catch((err) => {
        if (aktywny) setBlad(bladArkusza(err).tekst);
      });
    return () => {
      aktywny = false;
    };
  }, [token, proces.id]);
  return (
    <div className="oc-ekran k7">
      <Naglowek
        osoba={osoba}
        tytul="Podsumowanie pierwszej oceny"
        opis="Pierwsza ocena · arkusz z załącznika nr 2"
        wstecz="Wróć do rozmowy"
        onWstecz={onWstecz}
      />
      {stan && stan.proces_id === proces.id ? (
        <Formularz
          key={proces.id}
          stan={stan}
          token={token}
          osoba={osoba}
          edycja={moznaProwadzic}
          onZapisano={setStan}
          onWstecz={onWstecz}
          onDalej={onDalej}
        />
      ) : (
        <Wczytywanie blad={blad} />
      )}
    </div>
  );
}
