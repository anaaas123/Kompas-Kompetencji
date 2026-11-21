import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzArkusz,
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
  type ArkuszOkresowy,
  type BrakArkusza,
  type PoleArkusza,
} from "./api";
import { Zwijane } from "./Zwijane";
import {
  BladPola,
  BokOkresowej,
  DaneOkresowej,
  DATY_OKRESOWE,
  Naglowek,
  Podsumowanie,
  PoleDaty,
  Sekcja,
  Wczytywanie,
  Werdykt,
  bladWyniku,
  data,
  poprawnaData,
  zapiszPlik,
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
  if (p.wartosc === null || p.wartosc === "") return <span className="meta">—</span>;
  if (p.rodzaj === "data") return <>{data(p.wartosc)}</>;
  if (p.rodzaj === "wybor_punktow") return <>{p.wartosc} pkt</>;
  if (p.rodzaj === "liczba_dziesietna") return <>{p.wartosc.replace(".", ",")}</>;
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
  const przypisy = p.przypisy.length > 0 && <sup className="meta"> {p.przypisy.join(", ")}</sup>;
  // Tekst stały wzoru (oświadczenie, nazwa kryterium) bywa jednocześnie etykietą i wartością: pokazujemy go raz.
  const tenSamTekst = !edycja && (p.wartosc ?? "").trim().toLowerCase() === p.etykieta.trim().toLowerCase();
  if (tenSamTekst) {
    return (
      <div className="pole-arkusza">
        <span className="tekst-pola">{p.wartosc}</span>
        {przypisy}
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
        <span>
          {p.etykieta}
          {przypisy}
        </span>
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
          <Wartosc p={p} />
        </div>
      )}
      {brak && <p className="blad">{brak.komunikat}</p>}
    </div>
  );
}

type Formularz = Pick<ArkuszOkresowy, "sekcje" | "przypisy" | "braki">;
type Wartosci = Record<string, string | null>;

export function dzisiaj() {
  const d = new Date();
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
}

export async function pobierzPrzelozonego(token: string, osoba: Pracownik, zalogowanyId?: string | null) {
  const osoby = await pobierzPracownikow(token);
  return osoby.find((p) => p.osoba_id === osoba.przelozony_id) ?? osoby.find((p) => p.osoba_id === zalogowanyId);
}

function edytowalnePola(formularz: Formularz) {
  return formularz.sekcje.flatMap((s) => s.pola).filter((p) => p.edytowalne);
}

export function podpowiedziPol(formularz: Formularz, przelozony?: Pracownik) {
  const zmiany: Wartosci = {};
  if (!przelozony) return zmiany;
  const dane: Wartosci = {
    imie: przelozony.imie, nazwisko: przelozony.nazwisko, stanowisko: przelozony.stanowisko,
    komorka_organizacyjna: przelozony.komorka,
  };
  for (const p of edytowalnePola(formularz)) {
    if (p.wartosc?.trim()) continue;
    if (/^(bezposredni_przelozony|oceniajacy\.czesc_I{1,2})\./.test(p.id)) {
      const wartosc = dane[p.id.split(".").pop()!];
      if (wartosc) zmiany[p.id] = wartosc;
    } else if (p.id === "wniosek_o_stopien.oceniajacy.imie_nazwisko_lub_pieczatka") {
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
        : { cel: "pole-" + p.id, grupa: p.id === "wnioski_iprz" ? undefined : "pola/" + i };
      const tekst = cel.cel === "miejscowosc" ? "Arkusz: miejscowość" : `${nazwaSekcji(p, s.tytul)}: ${p.etykieta.charAt(0).toLocaleLowerCase("pl") + p.etykieta.slice(1)}`;
      const aktualna = p.edytowalne ? pola[p.id] : wartoscProcesu(p);
      const wartosc = aktualna === undefined ? p.wartosc : aktualna;
      const bledy = zSerwera.filter((b) => b.id === p.id);
      const wymagane = p.wymagane || bledy.some((b) => b.komunikat.startsWith("Uzupełnij pole"));
      const brak = { id: p.id, etykieta: p.etykieta, komunikat: "Uzupełnij pole." };
      const miejsce = { ...cel, tekst, ...(p.edytowalne ? {} : powiazanie(brak)) };
      if (p.edytowalne && p.rodzaj === "data" && !poprawnaData(wartosc)) {
        lista.push({ ...miejsce, opis: "Wpisz istniejącą datę w formacie RRRR-MM-DD." });
      } else if (wymagane && !wartosc?.trim()) {
        lista.push({ ...miejsce, opis: "Uzupełnij pole." });
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
          edycja={edycja && p.edytowalne}
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

export function PolaWzoru({ formularz, ustawWiele, ...edycja }: EdycjaPol & {
  formularz: Formularz;
  ustawWiele: (pola: Wartosci) => void;
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
          <BladPola cel="miejscowosc" />
          <Sekcja id="miejsca" tytul="Miejscowości w poszczególnych polach">
            {formularz.sekcje.map((s) => s.pola.filter((p) => miejsca.includes(p)).map((p) => {
              const role: Record<string, string> = {
                oceniany: "oceniany", oceniajacy: "oceniający", przelozony: "przełożony", kierujacy: "kierujący komórką",
              };
              const rola = role[p.id.split(".")[1]];
              return (
                <Pole key={p.id} p={{ ...p, etykieta: [s.tytul, rola].filter(Boolean).join(" · ") }}
                  wartosc={wartosc(p)} edycja={edycja.edycja} onZmiana={(v) => edycja.ustaw(p.id, v)} />
              );
            }))}
          </Sekcja>
        </div>
      )}
      <Sekcja id="pola" tytul="Pola arkusza">
        {formularz.sekcje.map((s, i) => {
          const pola = s.pola.filter((p) => p.widoczne && p.id !== "wnioski_iprz" && p.id !== "wnioski_rozwojowe" && !miejsca.includes(p));
          return s.widoczna && pola.length > 0 && (
            <Sekcja key={s.tytul + i} id={"pola/" + i} tytul={s.tytul}>
              <PolaSekcji pola={pola} {...edycja} />
            </Sekcja>
          );
        })}
      </Sekcja>
      <Sekcja id="przypisy" tytul="Przypisy wzoru">
        <ol className="slad">
          {Object.entries(formularz.przypisy).map(([nr, tekst]) => (
            <li key={nr} value={Number(nr)}>
              {tekst}
            </li>
          ))}
        </ol>
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
  onDalej,
  onZmienOcene,
  zalogowanyId,
}: Krok7Props) {
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
      moznaProwadzic ? pobierzPrzelozonego(token, osoba, zalogowanyId) : undefined,
    ]).then(([w, a, kierownik]) => {
      if (!aktywny) return;
      const zatwierdzony = a.status === "fulfilled" && a.value.zatwierdzony;
      if (w.status === "fulfilled") {
        setWynik(w.value);
        const dane = w.value.dane;
        setF(moznaProwadzic && !zatwierdzony && !dane.data_sporzadzenia_oceny
          ? { ...dane, data_sporzadzenia_oceny: dzisiaj() } : dane);
      } else setBladWynikuApi(bladWyniku(w.reason));
      if (a.status === "fulfilled") {
        setArkusz(a.value);
        if (kierownik.status === "fulfilled") {
          setPrzelozony(kierownik.value);
          if (!zatwierdzony) setZmiany(podpowiedziPol(a.value, kierownik.value));
        }
      } else setBlad(bladArkusza(a.reason).tekst);
    });
    return () => {
      aktywny = false;
    };
  }, [token, proces.id, osoba, zalogowanyId, moznaProwadzic]);

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
      tytul="Podsumowanie oceny"
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

  let formularz: Formularz = arkusz ?? { sekcje: [], braki: [], przypisy: {} };
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
      blokada: czekam || !moznaProwadzic,
    };
  const brakiWyniku: Brak[] = [];
  const dodajDate = (cel: string, tekst: string, wartosc?: string | null, wymagana = false) => {
    if (!poprawnaData(wartosc) || (wymagana && !wartosc))
      brakiWyniku.push({ cel, tekst: `Daty oceny: ${tekst}`, grupa: "dane", opis: "Podaj datę w formacie RRRR-MM-DD." });
  };
  if (f && wynik) {
    if (wynik.uzasadnienie_wymagane && !f.uzasadnienie?.trim())
      brakiWyniku.push({ cel: "uzasadnienie", tekst: "Uzasadnienie oceny" });
    for (const [k, nazwa] of DATY_OKRESOWE) dodajDate(k, nazwa, f[k]);
    dodajDate("data_zapoznania_z_poprzednia_ocena", "Zapoznanie z poprzednią oceną", f.data_zapoznania_z_poprzednia_ocena);
    if (f.zmiana_terminu) {
      dodajDate("nowy_termin", "Nowy termin", f.zmiana_terminu.nowy_termin, true);
      dodajDate("data_zawiadomienia", "Data zawiadomienia", f.zmiana_terminu.data_zawiadomienia, true);
    }
  }
  // Po poprawieniu dat ich kolejność i obliczony termin ponownie sprawdzi API przy zapisie.
  const zmienioneDaty = f && wynik && (
    DATY_OKRESOWE.some(([k]) => f[k] !== wynik.dane[k]) ||
    f.data_zapoznania_z_poprzednia_ocena !== wynik.dane.data_zapoznania_z_poprzednia_ocena ||
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
      if (DATY_Z_WYNIKU[b.id]) return { cel: DATY_Z_WYNIKU[b.id], grupa: "dane" };
    }, (p) => p.id === "uzasadnienie" ? f?.uzasadnienie : f?.[DATY_Z_WYNIKU[p.id]])
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
    braki.push({ tekst: `Terminy: ${tekst}`, cel: pole ?? "terminy", grupa: pole ? "dane" : "terminy", tylkoTermin: true });
  }
  if (!arkusz || odswiez) braki.push({ cel: "odswiez-arkusz", tekst: "Wczytanie arkusza" });
  const brak = braki.some((b) => !b.tylkoTermin);
  const zlaData = edytowalne.some((p) => p.rodzaj === "data" && !poprawnaData(pola[p.id]));
  const pdf = !!arkusz?.pdf_dostepny && !brak && !ruszonePola && !ruszonyWynik && !czekam;
  const zatwierdzony = !!arkusz?.zatwierdzony && !ruszonePola && !ruszonyWynik && !odswiez;
  const pobierz = () =>
    pdf &&
    wykonaj(async () =>
      zapiszPlik(await pobierzArkuszPdf(token, proces.id), `arkusz-${proces.arkusz}-${osoba.nazwisko}.pdf`),
    );
  function zapisz(zatwierdz: boolean) {
    if (!arkusz || !moznaProwadzic || zlaData || brakiWyniku.length || odswiez || (zatwierdz && brak)) return;
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
  const ezd = arkusz?.rejestracja_ezd;
  return (
    <div className="oc-ekran k7">
      {naglowek}
      <Podsumowanie
        key={JSON.stringify(formularz.braki)}
        braki={braki}
        blad={blad}
        podpis={arkusz?.komunikat_podpis ?? "PDF i „Zatwierdź” nie są podpisem."}
        onWstecz={onWstecz}
        dzieci={
          <>
            {daneWyniku && <DaneOkresowej {...daneWyniku} />}
            {arkusz && (
              <PolaWzoru
                formularz={formularz}
                wartosci={pola}
                braki={braki}
                edycja={moznaProwadzic && !czekam}
                ustawWiele={(v) => setZmiany((p) => ({ ...p, ...v }))}
                ustaw={(id, v) => setZmiany((p) => ({ ...p, [id]: v }))}
              />
            )}
          </>
        }
        bok={
          <>
            {daneWyniku ? (
              <BokOkresowej {...daneWyniku} onZmienOcene={moznaProwadzic ? onZmienOcene : undefined} />
            ) : (
              <>
                <Werdykt wynik={null} warunki={[]} />
                <p id="brak-wyniku" tabIndex={-1}>
                  {bladWynikuApi}
                  {onZmienOcene && <button className="link" type="button" onClick={onZmienOcene}>Wróć do ocen cząstkowych</button>}
                </p>
              </>
            )}
            {wnioski && (
              <div id="pole-wnioski_iprz" tabIndex={-1}>
                <Pole p={wnioski} wartosc={pola.wnioski_iprz} edycja={wnioski.edytowalne && moznaProwadzic && !czekam}
                  onZmiana={(v) => setZmiany((p) => ({ ...p, wnioski_iprz: v }))} />
                <BladPola cel="pole-wnioski_iprz" />
                {moznaProwadzic && <button className="link" type="button" onClick={onDalej}>Zobacz propozycje z kroków 3–5</button>}
              </div>
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
            {moznaProwadzic && (
              <button
                type="button"
                className="jasny"
                disabled={!arkusz || czekam || zlaData || brakiWyniku.length > 0 || odswiez}
                onClick={() => zapisz(false)}
              >
                Zapisz szkic
              </button>
            )}
            {arkusz?.pdf_dostepny && !zatwierdzony && moznaProwadzic && (
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
            {moznaProwadzic && (
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
            {(ruszonePola || ruszonyWynik) && moznaProwadzic && <span className="meta">Masz niezapisane zmiany w arkuszu.</span>}
          </>
        }
        glowna={
          zatwierdzony || !moznaProwadzic ? (
            <button type="button" disabled={!pdf} onClick={pobierz}>
              Pobierz arkusz (PDF)
            </button>
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
