import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzArkusz,
  pobierzKrok2,
  pobierzPracownikow,
  type Pracownik,
  pobierzArkuszPdf,
  pobierzWynik,
  pobierzZawiadomienie,
  zapiszWynik,
  type DaneWyniku,
  type WynikOkresowy,
  zapiszArkusz,
  zarejestrujEzd,
  zakonczOcene,
  type ZakonczenieOceny,
  type ArkuszOkresowy,
  type BrakArkusza,
  type PoleArkusza,
} from "./api";
import { nazwaKryterium } from "./Krok1";
import { PropozycjeZwarte } from "./Wnioski";
import { Zwijane } from "./Zwijane";
import {
  BladPola,
  BokOkresowej,
  DaneOkresowej,
  DATY_OKRESOWE,
  Naglowek,
  Podsumowanie,
  PoleDaty,
  PoleOpisowe,
  Sekcja,
  Wczytywanie,
  Werdykt,
  bladWyniku,
  data,
  dzienZapisu,
  zRozmowy,
  srednia,
  poprawnaData,
  zapiszPlik,
  drukujDoPodpisu,
  type Brak,
  type Krok7Props,
} from "./Wynik";
import "./krok7.css";

export function bladArkusza(err: unknown): { tekst: string; braki?: BrakArkusza[] } {
  if (err instanceof BladApi) {
    const d = err.detail as { komunikat?: string; braki?: BrakArkusza[] } | string | null;
    if (d && typeof d === "object" && d.komunikat) return { tekst: d.komunikat, braki: d.braki };
    if (typeof d === "string") return { tekst: d };
    if (err.status === 409) return { tekst: "Dane procesu zmieniły się. Otwórz arkusz ponownie." };
  }
  return { tekst: bladWyniku(err) };
}

function Wartosc({ p }: { p: PoleArkusza }) {
  if (p.rodzaj === "miejsce_na_podpis_odreczny") return <span className="meta">podpis odręczny na wydruku</span>;
  if (p.wartosc == null || p.wartosc === "") return <span className="meta">—</span>;
  if (p.rodzaj === "data") return <>{data(p.wartosc)}</>;
  if (p.rodzaj === "wybor_punktow") return <>{p.wartosc} pkt</>;
  if (p.rodzaj === "liczba_dziesietna") return <>{srednia(p.wartosc)}</>;
  if (p.id.startsWith("kryterium_") || p.id.endsWith(".kryterium")) return <>{nazwaKryterium(p.wartosc)}</>;
  return <span className="tekst-pola">{p.wartosc}</span>;
}

export function Pole({
  p,
  wartosc,
  brak,
  edycja,
  onZmiana,
}: {
  p: PoleArkusza;
  wartosc: string | null;
  brak?: BrakArkusza;
  edycja: boolean;
  onZmiana: (v: string | null) => void;
}) {
  // Tekst stały wzoru (oświadczenie, nazwa kryterium) bywa jednocześnie etykietą i wartością: pokazujemy go raz.
  const tenSamTekst = !edycja && (p.wartosc ?? "").trim().toLowerCase() === p.etykieta.trim().toLowerCase();
  if (tenSamTekst) {
    return (
      <div className="pole-arkusza">
        <Wartosc p={p} />
      </div>
    );
  }
  if (edycja && p.rodzaj === "data") {
    return (
      <div className="pole-arkusza">
        <PoleDaty nazwa={p.etykieta} wartosc={wartosc} onZmiana={onZmiana} />
        {brak && <p className="blad">{brak.komunikat}</p>}
      </div>
    );
  }
  return (
    <div className="pole-arkusza">
      <label className="etykieta">
        {p.etykieta}
        {edycja &&
          (p.rodzaj === "tekst_wielowierszowy" ? (
            <textarea
              rows={3}
              value={wartosc ?? ""}
              aria-invalid={!!brak}
              onChange={(e) => onZmiana(e.target.value || null)}
            />
          ) : (
            <input value={wartosc ?? ""} aria-invalid={!!brak} onChange={(e) => onZmiana(e.target.value || null)} />
          ))}
      </label>
      {!edycja && (
        <div>
          <Wartosc p={{ ...p, wartosc }} />
        </div>
      )}
      {brak && <p className="blad">{brak.komunikat}</p>}
    </div>
  );
}

type Formularz = Pick<ArkuszOkresowy, "sekcje" | "braki">;
type Wartosci = Record<string, string | null>;

export async function pobierzPrzelozonego(token: string, osoba: Pracownik, zalogowanyId?: string | null) {
  const osoby = await pobierzPracownikow(token);
  return osoby.find((p) => p.osoba_id === osoba.przelozony_id) ?? osoby.find((p) => p.osoba_id === zalogowanyId);
}

function edytowalnePola(formularz: Formularz) {
  return formularz.sekcje.flatMap((s) => s.pola).filter((p) => p.edytowalne);
}

export function podpowiedziPol(formularz: Formularz, przelozony?: Pracownik) {
  const zmiany: Wartosci = {};
  const pola = formularz.sekcje.flatMap((s) => s.pola);
  const nazwaUrzedu = pola.find((p) => p.id === "nazwa_urzedu")?.wartosc;
  const zapisaneMiejsca = new Set(pola.filter((p) => p.widoczne && p.id.endsWith(".miejscowosc") && p.wartosc?.trim())
    .map((p) => p.wartosc));
  const miejscowosc = zapisaneMiejsca.size === 1 ? [...zapisaneMiejsca][0] :
    !zapisaneMiejsca.size && nazwaUrzedu === "Ministerstwo Cyfryzacji" ? "Warszawa" : null;
  const dane: Wartosci = {
    imie: przelozony?.imie ?? null, nazwisko: przelozony?.nazwisko ?? null, stanowisko: przelozony?.stanowisko ?? null,
    komorka_organizacyjna: przelozony?.komorka ?? null,
  };
  for (const p of edytowalnePola(formularz)) {
    if (p.wartosc?.trim()) continue;
    if (miejscowosc && p.id.endsWith(".miejscowosc")) zmiany[p.id] = miejscowosc;
    else if (/^(bezposredni_przelozony|oceniajacy\.czesc_I{1,2})\./.test(p.id)) {
      const wartosc = dane[p.id.split(".").pop()!];
      if (wartosc) zmiany[p.id] = wartosc;
    } else if (przelozony && p.id === "wniosek_o_stopien.oceniajacy.imie_nazwisko_lub_pieczatka") {
      zmiany[p.id] = [przelozony.imie, przelozony.nazwisko].filter(Boolean).join(" ");
    }
  }
  return zmiany;
}

function nazwaSekcji(p: PoleArkusza, sekcja: string) {
  if (p.id.startsWith("kierujacy_komorka.")) return "Kierujący komórką";
  if (p.id.startsWith("bezposredni_przelozony.")) return "Bezpośredni przełożony";
  if (p.id.startsWith("oceniajacy.czesc_")) return `${sekcja} · oceniający`;
  if (p.id.startsWith("oceniany.")) return "Oceniany";
  return sekcja;
}

const ETYKIETA_IPRZ = "Wnioski do indywidualnego programu rozwoju zawodowego";

export function brakiPol(
  formularz: Formularz,
  pola: Wartosci,
  zSerwera: BrakArkusza[],
  powiazanie: (b: BrakArkusza) => Partial<Brak> | undefined,
  wartoscProcesu: (p: PoleArkusza) => string | null | undefined,
) {
  const lista: Brak[] = [];
  for (const [i, s] of formularz.sekcje.entries()) {
    if (!s.widoczna) continue;
    for (const p of s.pola.filter((p) => p.widoczne)) {
      const cel = p.edytowalne && p.id.endsWith(".miejscowosc")
        ? { cel: "miejscowosc" }
        : { cel: "pole-" + p.id, grupa: dataDoKorekty(p) ? "daty" : p.id === "wnioski_iprz" ? undefined : "pola/" + i };
      const tekst = cel.cel === "miejscowosc" ? "Arkusz: miejscowość" : `${nazwaSekcji(p, s.tytul)}: ${p.etykieta.charAt(0).toLocaleLowerCase("pl") + p.etykieta.slice(1)}`;
      const aktualna = p.edytowalne ? pola[p.id] : wartoscProcesu(p);
      const wartosc = aktualna === undefined ? p.wartosc : aktualna;
      const bledy = zSerwera.filter((b) => b.id === p.id);
      const wymagane = p.wymagane || bledy.some((b) => b.komunikat.startsWith("Uzupełnij pole"));
      const brak = { id: p.id, etykieta: p.etykieta, komunikat: "Uzupełnij pole." };
      const miejsce = { ...cel, tekst: p.id === "wnioski_iprz" ? ETYKIETA_IPRZ : tekst, ...(p.edytowalne ? {} : powiazanie(brak)) };
      if (p.edytowalne && p.rodzaj === "data" && !poprawnaData(wartosc)) {
        lista.push({ ...miejsce, opis: "Wpisz istniejącą datę w formacie RRRR-MM-DD." });
      } else if (wymagane && !wartosc?.trim()) {
        lista.push({ ...miejsce, opis: p.id.startsWith("urzednik.") ? "Brak danych kadrowych do wniosku o stopień." : "Uzupełnij pole." });
      }
      for (const b of bledy.filter((b) => !b.komunikat.startsWith("Uzupełnij pole"))) {
        lista.push({ ...miejsce, opis: b.komunikat });
      }
    }
  }
  for (const b of zSerwera.filter(
    (b) => !formularz.sekcje.some((s) => s.widoczna && s.pola.some((p) => p.widoczne && p.id === b.id)),
  )) {
    lista.push({ cel: "pola", tekst: b.etykieta, opis: b.komunikat, ...powiazanie(b) });
  }
  return lista;
}

interface EdycjaPol {
  wartosci: Wartosci;
  braki: Brak[];
  edycja: boolean;
  ustaw: (id: string, v: string | null) => void;
}

function PolaSekcji({ pola, wartosci, braki, edycja, ustaw }: EdycjaPol & { pola: PoleArkusza[] }) {
  // Poprawiane pole pozostaje na miejscu również po wpisaniu ostatniego brakującego znaku.
  const [doUzupelnienia] = useState(() => new Set(braki.map((b) => b.cel)));
  const [wszystkie, setWszystkie] = useState(false);
  const wazne = pola.filter((p) => doUzupelnienia.has("pole-" + p.id));
  const pozostale = pola.filter((p) => !doUzupelnienia.has("pole-" + p.id));
  const skrot = wazne.length > 0 && pozostale.length > 0;
  const noweBraki = pozostale.some((p) => braki.some((b) => b.cel === "pole-" + p.id));
  function pokaz(p: PoleArkusza) {
    const id = "pole-" + p.id;
    const brak = braki.find((b) => b.cel === id);
    return (
      <div key={id} id={id} tabIndex={-1}>
        <Pole
          p={p}
          wartosc={p.id in wartosci ? wartosci[p.id] : p.wartosc}
          brak={brak && { id: p.id, etykieta: p.etykieta, komunikat: brak.opis ?? "Uzupełnij pole." }}
          edycja={edycja && p.edytowalne && !p.id.startsWith("urzednik.")}
          onZmiana={(v) => ustaw(p.id, v)}
        />
      </div>
    );
  }
  return (
    <>
      <div className="pola-arkusza">{(skrot ? wazne : pola).map(pokaz)}</div>
      {skrot && (
        <>
          <button
            type="button"
            className="link"
            aria-expanded={wszystkie || noweBraki}
            disabled={noweBraki}
            onClick={() => setWszystkie(!wszystkie)}
          >
            {wszystkie || noweBraki ? "Ukryj pozostałe pola" : `Pozostałe pola (${pozostale.length})`}
          </button>
          <Zwijane otwarte={wszystkie || noweBraki}>
            <div className="pola-arkusza">{pozostale.map(pokaz)}</div>
          </Zwijane>
        </>
      )}
    </>
  );
}

function dataDoKorekty(p: PoleArkusza) {
  return p.edytowalne && p.rodzaj === "data" && !p.id.startsWith("urzednik.");
}

const ETYKIETY_DAT: Record<string, string> = {
  "dokonanie_oceny.kierujacy.data": "Data podpisu kierującego komórką",
  "wniosek_o_stopien.oceniajacy.data": "Data wniosku o stopień",
  "rozmowa_oceniajaca.data": "Rozmowa oceniająca",
};

export function DatyWzoru({ formularz, wartosci, edycja, ustaw }: EdycjaPol & { formularz: Formularz }) {
  return (
    <div className="pola-arkusza">
      {edytowalnePola(formularz).filter(dataDoKorekty).map((p) => (
        <div key={p.id} id={"pole-" + p.id} tabIndex={-1}>
          <Pole
            p={{ ...p, etykieta: ETYKIETY_DAT[p.id] ?? p.etykieta }}
            wartosc={p.id in wartosci ? wartosci[p.id] : p.wartosc}
            edycja={edycja}
            onZmiana={(v) => ustaw(p.id, v)}
          />
          <BladPola cel={"pole-" + p.id} />
        </div>
      ))}
    </div>
  );
}

export function PolaWzoru({ formularz, ustawWiele, maWynik = true, ...edycja }: EdycjaPol & {
  formularz: Formularz;
  ustawWiele: (pola: Wartosci) => void;
  maWynik?: boolean;
}) {
  const miejsca = edytowalnePola(formularz).filter((p) => p.id.endsWith(".miejscowosc"));
  const wartosc = (p: PoleArkusza) => p.id in edycja.wartosci ? edycja.wartosci[p.id] : p.wartosc;
  const wspolna = miejsca[0] && wartosc(miejsca[0]);
  const rozne = miejsca.some((p) => wartosc(p) !== wspolna);
  return (
    <>
      {miejsca.length > 0 && (
        <div className="sekcja k7-miejsca">
          <label className="etykieta">
            Miejscowość
            <input id="miejscowosc" disabled={!edycja.edycja} value={rozne ? "" : wspolna ?? ""}
              placeholder={rozne ? "Różne miejscowości w arkuszu" : undefined}
              onChange={(e) => ustawWiele(Object.fromEntries(miejsca.map((p) => [p.id, e.target.value || null])))}
            />
          </label>
          {rozne && <p className="meta">W arkuszu zapisano różne miejscowości. Wpisana tutaj nazwa obejmie cały arkusz.</p>}
          <BladPola cel="miejscowosc" />
        </div>
      )}
      <Sekcja id="pola" tytul="Pola arkusza">
        {formularz.sekcje.map((s, i) => {
          const pola = s.pola.filter((p) => p.widoczne && !miejsca.includes(p) && !dataDoKorekty(p)
            && p.id !== "wnioski_iprz" && p.id !== "wnioski_rozwojowe"
            && !(maWynik && (p.id === "uzasadnienie" || p.id === "pouczenie")));
          return s.widoczna && pola.length > 0 && (
            <Sekcja key={s.tytul + i} id={"pola/" + i} tytul={s.tytul}>
              <PolaSekcji pola={pola} {...edycja} />
            </Sekcja>
          );
        })}
      </Sekcja>
    </>
  );
}

const DATY_Z_WYNIKU: Record<string, (typeof DATY_OKRESOWE)[number][0] | "poprzednia_ocena_poziom"> = {
  "potwierdzenie_kryteriow.oceniajacy.data": "data_ustalenia_kryteriow",
  "potwierdzenie_kryteriow.oceniany.data": "data_zapoznania_z_kryteriami",
  "okres_oceny.od": "data_zapoznania_z_kryteriami",
  "okres_oceny.do": "data_sporzadzenia_oceny",
  "dokonanie_oceny.oceniajacy.data": "data_sporzadzenia_oceny",
  "zapoznanie.oceniany.data": "data_zapoznania_z_ocena",
  "poprzednia_ocena.poziom": "poprzednia_ocena_poziom",
};

export function Arkusz({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
  onZmienOcene,
  zalogowanyId,
}: Krok7Props) {
  const [zakonczenie, setZakonczenie] = useState<ZakonczenieOceny | null>(null);
  const [dataZapoznania, setDataZapoznania] = useState<string | null>(null);
  const zakonczony = proces.status !== "W_TOKU" || zakonczenie !== null;
  const edycja = moznaProwadzic && !zakonczony;
  const [arkusz, setArkusz] = useState<ArkuszOkresowy | null>(null);
  const [wynik, setWynik] = useState<WynikOkresowy | null>(null);
  const [f, setF] = useState<DaneWyniku | null>(null);
  const [sprawdzonePola, setSprawdzonePola] = useState<Wartosci>({});
  const [zmiany, setZmiany] = useState<Wartosci>({});
  const [blad, setBlad] = useState<string | null>(null);
  const [bladWynikuApi, setBladWynikuApi] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [przelozony, setPrzelozony] = useState<Pracownik>();
  const [odswiez, setOdswiez] = useState(false);

  useEffect(() => {
    let aktywny = true;
    Promise.allSettled([
      pobierzWynik(token, proces.id),
      pobierzArkusz(token, proces.id),
      edycja ? pobierzPrzelozonego(token, osoba, zalogowanyId) : undefined,
      edycja ? pobierzKrok2(token, proces.id) : undefined,
      edycja ? zRozmowy(token, proces.id) : undefined,
    ]).then(([w, a, kierownik, krok2, rozmowa]) => {
      if (!aktywny) return;
      const zatwierdzony = a.status === "fulfilled" && a.value.zatwierdzony;
      if (w.status === "fulfilled") {
        setWynik(w.value);
        const dane = w.value.dane;
        const wybor = krok2.status === "fulfilled" ? krok2.value?.wybor : undefined;
        // Dzień ustalenia kryteriów jak w API (dzien_ustalenia_kryteriow): data rozmowy z części I, bez niej dzień zapisu.
        const zapis = wybor?.zapisano && Number.isFinite(Date.parse(wybor.zapisano)) ? dzienZapisu(new Date(wybor.zapisano)) : null;
        const kryteria = wybor?.zapoznanie ?? zapis;
        setF(edycja && !zatwierdzony ? {
          ...dane,
          data_ustalenia_kryteriow: dane.data_ustalenia_kryteriow ?? kryteria,
          data_zapoznania_z_kryteriami: dane.data_zapoznania_z_kryteriami ?? kryteria,
          data_sporzadzenia_oceny: dane.data_sporzadzenia_oceny ?? dzienZapisu(new Date()),
          poprzednia_ocena_poziom: w.value.poprzednia_ocena?.poziom ?? dane.poprzednia_ocena_poziom,
        } : dane);
      } else setBladWynikuApi(bladWyniku(w.reason));
      if (a.status === "fulfilled") {
        setArkusz(a.value);
        const szef = kierownik.status === "fulfilled" ? kierownik.value : undefined;
        setPrzelozony(szef);
        if (edycja && !zatwierdzony) {
          const domyslne = podpowiedziPol(a.value, szef);
          for (const p of edytowalnePola(a.value)) {
            if (p.wartosc?.trim()) continue;
            const z = rozmowa.status === "fulfilled" ? rozmowa.value : undefined;
            if (p.id === "wnioski_iprz") domyslne[p.id] = z?.wnioski ?? null;
            if (p.id === "rozmowa_oceniajaca.data") domyslne[p.id] = z?.data ?? null;
          }
          setZmiany(domyslne);
        }
      } else setBlad(bladArkusza(a.reason).tekst);
    });
    return () => {
      aktywny = false;
    };
  }, [token, proces.id, osoba, zalogowanyId, edycja]);

  async function wykonaj(akcja: () => Promise<void>) {
    if (czekam) return;
    setCzekam(true);
    setBlad(null);
    try {
      await akcja();
    } catch (err) {
      const { tekst, braki } = bladArkusza(err);
      setBlad(tekst);
      if (braki) setArkusz((a) => a && { ...a, braki, pdf_dostepny: false, zatwierdzony: false });
    } finally {
      setCzekam(false);
    }
  }

  const naglowek = (
    <Naglowek
      osoba={osoba}
      tytul="Zakończenie oceny"
      opis={`Ocena okresowa · arkusz ${proces.arkusz}`}
      wstecz="Wróć do rozmowy"
      onWstecz={onWstecz}
    />
  );
  if (!arkusz && !wynik)
    return (
      <div className="oc-ekran k7">
        {naglowek}
        <Wczytywanie blad={blad ?? bladWynikuApi} />
      </div>
    );

  let formularz: Formularz = arkusz ?? { sekcje: [], braki: [] };
  if (wynik?.czesc_iii.dolaczana && f && !f.dolacz_wniosek_o_stopien) {
    const sekcje = formularz.sekcje.filter((s) => !s.pola.some((p) => p.id === "wniosek_o_stopien.stopien"));
    const ids = new Set(sekcje.flatMap((s) => s.pola.map((p) => p.id)));
    formularz = { ...formularz, sekcje, braki: formularz.braki.filter((b) => ids.has(b.id)) };
  }
  const edytowalne = edytowalnePola(formularz);
  const wnioski = formularz.sekcje.flatMap((s) => s.pola).find((p) => p.id === "wnioski_iprz" && p.widoczne);
  const pola = Object.fromEntries(edytowalne.map((p) => [p.id, p.id in zmiany ? zmiany[p.id] : p.wartosc]));
  const ruszonePola = edytowalne.some((p) => pola[p.id] !== p.wartosc);
  const ruszonyWynik = !!wynik && (!wynik.zapisany || JSON.stringify(f) !== JSON.stringify(wynik.dane));
  const daneWyniku = wynik &&
    f && {
      wynik,
      f,
      ustaw: (v: Partial<DaneWyniku>) => setF((p) => p && { ...p, ...v }),
      blokada: czekam || !edycja,
    };
  const brakiWyniku: Brak[] = [];
  const dodajDate = (cel: string, tekst: string, wartosc?: string | null, wymagana = false, grupa = "daty") => {
    if (!poprawnaData(wartosc) || (wymagana && !wartosc))
      brakiWyniku.push({ cel, tekst: `Daty oceny: ${tekst}`, grupa, opis: "Podaj datę w formacie RRRR-MM-DD." });
  };
  if (f && wynik) {
    if (wynik.uzasadnienie_wymagane && !f.uzasadnienie?.trim())
      brakiWyniku.push({ cel: "uzasadnienie", tekst: "Uzasadnienie oceny" });
    for (const [k, nazwa] of DATY_OKRESOWE) dodajDate(k, nazwa, f[k]);
    dodajDate("data_zapoznania_z_poprzednia_ocena", "Zapoznanie z poprzednią oceną", f.data_zapoznania_z_poprzednia_ocena, false, "wyjatki");
    if (f.zmiana_stanowiska) dodajDate("data_zmiany_stanowiska", "Data zmiany stanowiska", f.zmiana_stanowiska.data, true, "wyjatki");
    if (f.zmiana_terminu) {
      dodajDate("nowy_termin", "Nowy termin", f.zmiana_terminu.nowy_termin, true, "wyjatki");
      dodajDate("data_zawiadomienia", "Data zawiadomienia", f.zmiana_terminu.data_zawiadomienia, true, "wyjatki");
    }
  }
  // Po poprawieniu dat ich kolejność i obliczony termin ponownie sprawdzi API przy zapisie.
  const zmienioneDaty = f && wynik && (
    DATY_OKRESOWE.some(([k]) => f[k] !== wynik.dane[k]) ||
    f.data_zapoznania_z_poprzednia_ocena !== wynik.dane.data_zapoznania_z_poprzednia_ocena ||
    JSON.stringify(f.zmiana_stanowiska) !== JSON.stringify(wynik.dane.zmiana_stanowiska) ||
    JSON.stringify(f.zmiana_terminu) !== JSON.stringify(wynik.dane.zmiana_terminu)
  );
  const zmianaDatArkusza = edytowalne.some((p) => p.rodzaj === "data" &&
    pola[p.id] !== (p.id in sprawdzonePola ? sprawdzonePola[p.id] : p.wartosc));
  const brakiSerwera = formularz.braki.filter((b) => {
    if (b.id === "wynik_okresowy") return false;
    if (b.id === "okres_oceny.do" || b.id === "rozmowa_oceniajaca.data")
      return b.komunikat.startsWith("Uzupełnij pole") || (!zmienioneDaty && !zmianaDatArkusza);
    return true;
  });
  const braki = [
    ...brakiWyniku,
    ...brakiPol(formularz, pola, brakiSerwera, (b) => {
      if (!daneWyniku) return;
      if (b.id === "uzasadnienie") return { cel: "uzasadnienie", grupa: undefined };
      if (DATY_Z_WYNIKU[b.id]) return { cel: DATY_Z_WYNIKU[b.id], grupa: b.id === "poprzednia_ocena.poziom" ? "wyjatki" : "daty" };
    }, (p) => p.id === "uzasadnienie" ? f?.uzasadnienie : p.id === "poprzednia_ocena.poziom"
      ? wynik?.poprzednia_ocena?.poziom ?? f?.poprzednia_ocena_poziom : f?.[DATY_Z_WYNIKU[p.id]])
      .filter((b) => !(zmienioneDaty && b.cel === "pole-termin_sporzadzenia_oceny")),
  ];
  if (!wynik) braki.push({ cel: "brak-wyniku", tekst: "Oceny cząstkowe: ustalenie wyniku" });
  for (const tekst of wynik?.terminy.braki ?? []) {
    const pole = tekst.includes("zapoznania z kryteriami")
      ? "data_zapoznania_z_kryteriami"
      : tekst.includes("ustalenia kryteriów")
        ? "data_ustalenia_kryteriow"
        : tekst.includes("poprzednią oceną negatywną")
          ? "data_zapoznania_z_poprzednia_ocena"
          : null;
    if (pole && f?.[pole]) continue;
    braki.push({ tekst: `Terminy: ${tekst}`, cel: pole ?? "terminy", grupa: pole === "data_zapoznania_z_poprzednia_ocena" ? "wyjatki" : pole ? "daty" : "terminy", tylkoTermin: true });
  }
  if (!arkusz || odswiez) braki.push({ cel: "odswiez-arkusz", tekst: "Wczytanie arkusza" });
  const brak = braki.some((b) => !b.tylkoTermin);
  const zlaData = edytowalne.some((p) => p.rodzaj === "data" && !poprawnaData(pola[p.id]));
  const pdf = !!arkusz?.pdf_dostepny && !brak && !ruszonePola && !ruszonyWynik && !czekam;
  const zatwierdzony = !!arkusz?.zatwierdzony && !ruszonePola && !ruszonyWynik && !odswiez;
  const nazwaPdf = `arkusz-${proces.arkusz}-${osoba.nazwisko}.pdf`;
  const pobierz = () => pdf && wykonaj(async () => zapiszPlik(await pobierzArkuszPdf(token, proces.id), nazwaPdf));
  const drukuj = () => pdf && wykonaj(() => drukujDoPodpisu(() => pobierzArkuszPdf(token, proces.id), nazwaPdf));
  function zapisz(zatwierdz: boolean) {
    if (!arkusz || !edycja || zlaData || brakiWyniku.length || odswiez || (zatwierdz && brak)) return;
    return wykonaj(async () => {
      let aktualny = arkusz;
      if (ruszonyWynik && daneWyniku) {
        const w = await zapiszWynik(token, proces.id, {
          ...daneWyniku.f,
          dolacz_wniosek_o_stopien: daneWyniku.wynik.czesc_iii.dostepna && daneWyniku.f.dolacz_wniosek_o_stopien,
        });
        setWynik(w);
        setF(w.dane);
        setOdswiez(true);
        aktualny = await pobierzArkusz(token, proces.id);
        setArkusz(aktualny);
        setOdswiez(false);
      }
      // Po zapisie wyniku część III może mieć inny zestaw pól edytowalnych.
      const aktualneZmiany = { ...zmiany };
      if (aktualny !== arkusz) {
        const nowePodpowiedzi = podpowiedziPol(aktualny, przelozony);
        const miejsca = edytowalne.filter((p) => p.id.endsWith(".miejscowosc"));
        const wspolna = miejsca.length && pola[miejsca[0].id];
        for (const p of edytowalnePola(aktualny)) {
          if (p.id in pola || p.wartosc) continue;
          if (p.id.endsWith(".miejscowosc") && wspolna && miejsca.every((m) => pola[m.id] === wspolna)) {
            aktualneZmiany[p.id] = wspolna;
          } else if (nowePodpowiedzi[p.id]) aktualneZmiany[p.id] = nowePodpowiedzi[p.id];
        }
      }
      const komplet = Object.fromEntries(edytowalnePola(aktualny).map((p) =>
        [p.id, p.id in aktualneZmiany ? aktualneZmiany[p.id] : p.wartosc]));
      setZmiany(aktualneZmiany);
      setSprawdzonePola(komplet);
      setArkusz(await zapiszArkusz(token, proces.id, komplet, zatwierdz));
      setSprawdzonePola({});
      setZmiany({});
    });
  }
  const podglad = { ...pola };
  if (wynik && f) {
    const dolaczony = wynik.czesc_iii.dostepna && f.dolacz_wniosek_o_stopien;
    podglad["wniosek_o_stopien.status"] = osoba.korpus === "urzednik_sc" ? (dolaczony ? "TAK" : "NIE") : "NIE DOTYCZY";
    for (const [id, klucz] of Object.entries(DATY_Z_WYNIKU)) {
      if (!(id in pola)) podglad[id] = f[klucz];
    }
    podglad.uzasadnienie = f.uzasadnienie;
    podglad["poprzednia_ocena.poziom"] = wynik.poprzednia_ocena?.poziom ?? f.poprzednia_ocena_poziom;
  }
  const edycjaPol = {
    wartosci: podglad, braki, edycja: edycja && !czekam,
    ustaw: (id: string, v: string | null) => setZmiany((p) => ({ ...p, [id]: v })),
  };
  const datyWzoru = <DatyWzoru formularz={formularz} {...edycjaPol} />;
  const wartoscWnioskow = wnioski && wnioski.id in pola ? pola[wnioski.id] : wnioski?.wartosc ?? null;
  const ustawWnioski = (tekst: string) => edycjaPol.ustaw("wnioski_iprz", tekst || null);
  const ezd = arkusz?.rejestracja_ezd;
  // Zakończenie (§ 12 ust. 1): datę zapoznania wpisuje się po podpisie ocenianego na wydruku, więc pole startuje puste.
  const zapoznanie = zakonczenie ? (
    <p className="sukces">
      Ocena zakończona: zapoznanie z oceną {data(zakonczenie.data_zapoznania_z_ocena)}. Ocena trafiła do kartoteki pracownika.
    </p>
  ) : zatwierdzony && edycja ? (
    <>
      <PoleDaty id="data-zapoznania" nazwa="Data zapoznania ocenianego z oceną" wartosc={dataZapoznania} onZmiana={setDataZapoznania} />
      <button
        type="button"
        className="jasny"
        disabled={czekam || !dataZapoznania || !poprawnaData(dataZapoznania)}
        onClick={() => dataZapoznania && wykonaj(async () => setZakonczenie(await zakonczOcene(token, proces.id, dataZapoznania)))}
      >
        Zakończ ocenę
      </button>
    </>
  ) : null;
  return (
    <div className="oc-ekran k7">
      {naglowek}
      <Podsumowanie
        key={JSON.stringify(formularz.braki)}
        braki={braki}
        blad={blad}
        podpis={zatwierdzony ? "Arkusz włącza się do akt osobowych, kopię doręcza się ocenianemu (§ 12 ust. 2)." : undefined}
        onWstecz={onWstecz}
        dzieci={
          <>
            {daneWyniku && <PoleOpisowe id="uzasadnienie"
              etykieta={`Uzasadnienie oceny ${daneWyniku.wynik.uzasadnienie_wymagane ? "(wymagane)" : "(opcjonalnie)"}`}
              wartosc={daneWyniku.f.uzasadnienie} wymagane={daneWyniku.wynik.uzasadnienie_wymagane}
              blokada={daneWyniku.blokada} wiersze={3} onZmiana={(tekst) => daneWyniku.ustaw({ uzasadnienie: tekst })} />}
            {wnioski && (
              <div className="sekcja">
                <PoleOpisowe id="pole-wnioski_iprz" etykieta={ETYKIETA_IPRZ} wartosc={wartoscWnioskow}
                  blokada={!edycjaPol.edycja || !wnioski.edytowalne} wiersze={5} onZmiana={ustawWnioski} />
                {edycja && wnioski.edytowalne && <PropozycjeZwarte token={token} procesId={proces.id}
                  wartosc={wartoscWnioskow} blokada={czekam} onZmiana={ustawWnioski} />}
              </div>
            )}
            {daneWyniku ? <DaneOkresowej {...daneWyniku}>{datyWzoru}</DaneOkresowej> :
              <Sekcja id="daty" tytul="Daty (z wcześniejszych kroków)">{datyWzoru}</Sekcja>}
            {arkusz && (
              <PolaWzoru
                formularz={formularz}
                maWynik={!!daneWyniku}
                {...edycjaPol}
                ustawWiele={(v) => setZmiany((p) => ({ ...p, ...v }))}
              />
            )}
          </>
        }
        bok={
          <>
            {daneWyniku ? (
              <BokOkresowej {...daneWyniku} onZmienOcene={edycja ? onZmienOcene : undefined} zapoznanie={zapoznanie} />
            ) : (
              <>
                <Werdykt wynik={null} warunki={[]} />
                <p id="brak-wyniku" tabIndex={-1}>
                  {bladWynikuApi}
                  {edycja && onZmienOcene && <button className="link" type="button" onClick={onZmienOcene}>Wróć do ocen cząstkowych</button>}
                </p>
              </>
            )}
            {zatwierdzony && <p className="sukces">Arkusz zatwierdzony.</p>}
          </>
        }
        akcje={
          <>
            {(!arkusz || odswiez) && (
              <button
                type="button"
                id="odswiez-arkusz"
                className="jasny"
                disabled={czekam}
                onClick={() =>
                  wykonaj(async () => {
                    setArkusz(await pobierzArkusz(token, proces.id));
                    setSprawdzonePola({});
                    setOdswiez(false);
                  })
                }
              >
                Wczytaj arkusz ponownie
              </button>
            )}
            {edycja && (
              <button
                type="button"
                className="jasny"
                disabled={!arkusz || czekam || zlaData || brakiWyniku.length > 0 || odswiez}
                onClick={() => zapisz(false)}
              >
                Zapisz szkic
              </button>
            )}
            {arkusz?.pdf_dostepny && !zatwierdzony && edycja && (
              <button type="button" className="link" disabled={!pdf} onClick={pobierz}>
                Pobierz zapisany arkusz (PDF)
              </button>
            )}
            {wynik?.zawiadomienie_dostepne && (
              <button
                type="button"
                className="link"
                disabled={czekam || ruszonyWynik}
                onClick={() =>
                  wykonaj(async () =>
                    zapiszPlik(
                      await pobierzZawiadomienie(token, proces.id),
                      `zawiadomienie-zmiana-terminu-${proces.id}.pdf`,
                    ),
                  )
                }
              >
                Pobierz zawiadomienie § 8 (PDF)
              </button>
            )}
            {edycja && zatwierdzony && (
              <button
                type="button"
                className="link"
                disabled={!pdf}
                onClick={() =>
                  pdf &&
                  wykonaj(async () => {
                    await zarejestrujEzd(token, proces.id);
                    setArkusz(await pobierzArkusz(token, proces.id));
                  })
                }
              >
                Zarejestruj w EZD (próbnie)
              </button>
            )}
            {ezd && (
              <p className="sukces">
                Próbna rejestracja w EZD: {ezd.numer_sprawy}, {data(ezd.zarejestrowano.slice(0, 10))}, skrót PDF{" "}
                {ezd.sha256_pdf.slice(0, 12)}…
              </p>
            )}
          </>
        }
        glowna={
          zakonczony ? (
            <div className="k7-zakonczona"><strong>Ocena zakończona</strong>
              {pdf && <button type="button" onClick={pobierz}>Pobierz arkusz (PDF)</button>}
            </div>
          ) : zatwierdzony || !edycja ? (
            <span className="k7-zakonczona">
              <button type="button" className="link" disabled={!pdf} onClick={pobierz}>Pobierz PDF</button>
              <button type="button" disabled={!pdf} onClick={drukuj}>Drukuj do podpisu</button>
            </span>
          ) : (
            <button type="button" disabled={brak || czekam} onClick={() => zapisz(true)}>
              Zatwierdź arkusz
            </button>
          )
        }
      />
    </div>
  );
}
