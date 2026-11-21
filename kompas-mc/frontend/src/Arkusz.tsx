import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzArkusz,
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

export function brakiPol(
  formularz: Formularz,
  pola: Wartosci,
  zSerwera: BrakArkusza[],
  powiazanie: (b: BrakArkusza) => Partial<Brak> | undefined,
) {
  const lista: Brak[] = [];
  for (const [i, s] of formularz.sekcje.entries()) {
    if (!s.widoczna) continue;
    for (const p of s.pola.filter((p) => p.widoczne)) {
      const cel = { cel: "pole-" + p.id, grupa: "pola/" + i };
      const wartosc = p.edytowalne && p.id in pola ? pola[p.id] : p.wartosc;
      const bledy = zSerwera.filter((b) => b.id === p.id);
      if (p.edytowalne && p.rodzaj === "data" && !poprawnaData(wartosc)) {
        lista.push({ ...cel, tekst: p.etykieta, opis: "Wpisz istniejącą datę w formacie RRRR-MM-DD." });
      } else if (p.edytowalne && p.wymagane && !wartosc?.trim() && !bledy.length) {
        lista.push({ ...cel, tekst: p.etykieta });
      }
      for (const b of bledy) {
        if (p.edytowalne && wartosc !== p.wartosc && wartosc?.trim() && b.komunikat.startsWith("Uzupełnij pole")) continue;
        lista.push({ ...cel, tekst: b.etykieta, opis: b.komunikat, ...(p.edytowalne ? {} : powiazanie(b)) });
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

export function PolaWzoru({ formularz, ...edycja }: EdycjaPol & { formularz: Formularz }) {
  return (
    <>
      <Sekcja id="pola" tytul="Pola arkusza">
        {formularz.sekcje.map(
          (s, i) =>
            s.widoczna && (
              <Sekcja key={s.tytul} id={"pola/" + i} tytul={s.tytul}>
                <PolaSekcji pola={s.pola.filter((p) => p.widoczne)} {...edycja} />
              </Sekcja>
            ),
        )}
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

const DATY_Z_WYNIKU: Record<string, string> = {
  "potwierdzenie_kryteriow.oceniajacy.data": "data_ustalenia_kryteriow",
  "potwierdzenie_kryteriow.oceniany.data": "data_zapoznania_z_kryteriami",
  "okres_oceny.od": "data_zapoznania_z_kryteriami",
  "okres_oceny.do": "data_sporzadzenia_oceny",
  "dokonanie_oceny.oceniajacy.data": "data_sporzadzenia_oceny",
  "zapoznanie.oceniany.data": "data_zapoznania_z_ocena",
  "poprzednia_ocena.poziom": "poprzednia_ocena_poziom",
};

export function Okresowa({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
  onDalej,
  widok,
}: Krok7Props & { widok: "wynik" | "arkusz" }) {
  const [arkusz, setArkusz] = useState<ArkuszOkresowy | null>(null);
  const [wynik, setWynik] = useState<WynikOkresowy | null>(null);
  const [f, setF] = useState<DaneWyniku | null>(null);
  const [zmiany, setZmiany] = useState<Wartosci>({});
  const [blad, setBlad] = useState<string | null>(null);
  const [bladWynikuApi, setBladWynikuApi] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [odswiez, setOdswiez] = useState(false);

  useEffect(() => {
    let aktywny = true;
    Promise.allSettled([pobierzWynik(token, proces.id), pobierzArkusz(token, proces.id)]).then(([w, a]) => {
      if (!aktywny) return;
      if (w.status === "fulfilled") {
        setWynik(w.value);
        setF(w.value.dane);
      } else setBladWynikuApi(bladWyniku(w.reason));
      if (a.status === "fulfilled") setArkusz(a.value);
      else setBlad(bladArkusza(a.reason).tekst);
    });
    return () => {
      aktywny = false;
    };
  }, [token, proces.id]);

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
      tytul={widok === "wynik" ? "Podsumowanie oceny" : `Arkusz ${proces.arkusz}`}
      opis={`Ocena okresowa · arkusz ${proces.arkusz}`}
      wstecz={widok === "wynik" ? "Wróć do rozmowy" : "Wróć do wyniku i terminów"}
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

  const formularz = arkusz ?? { sekcje: [], braki: [], przypisy: {} };
  const edytowalne = formularz.sekcje.flatMap((s) => s.pola).filter((p) => p.edytowalne);
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
      brakiWyniku.push({ cel, tekst, grupa: "dane", opis: "Podaj datę w formacie RRRR-MM-DD." });
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
  const braki = [
    ...brakiWyniku,
    ...brakiPol(formularz, pola, formularz.braki, (b) => {
      if (b.id === "wynik_okresowy")
        return { cel: "zapis-wyniku", tekst: "Zapis aktualnego wyniku i terminów", opis: undefined };
      if (!daneWyniku) return;
      if (b.id === "uzasadnienie") return { cel: "uzasadnienie", grupa: undefined };
      if (DATY_Z_WYNIKU[b.id]) return { cel: DATY_Z_WYNIKU[b.id], grupa: "dane" };
    }),
  ];
  if (ruszonyWynik && !braki.some((b) => b.cel === "zapis-wyniku"))
    braki.push({ cel: "zapis-wyniku", tekst: "Zapis aktualnego wyniku i terminów" });
  for (const tekst of wynik?.terminy.braki ?? []) {
    const pole = tekst.includes("zapoznania z kryteriami")
      ? "data_zapoznania_z_kryteriami"
      : tekst.includes("ustalenia kryteriów")
        ? "data_ustalenia_kryteriow"
        : tekst.includes("poprzednią oceną negatywną")
          ? "data_zapoznania_z_poprzednia_ocena"
          : null;
    braki.push({ tekst, cel: pole ?? "terminy", grupa: pole ? "dane" : "terminy", tylkoTermin: true });
  }
  if (!arkusz || odswiez) braki.push({ cel: "odswiez-arkusz", tekst: "Wczytanie arkusza" });
  const brak = braki.some((b) => !b.tylkoTermin);
  const zlaData = edytowalne.some((p) => p.rodzaj === "data" && !poprawnaData(pola[p.id]));
  const pdf = !!arkusz?.pdf_dostepny && !brak && !ruszonePola && !czekam;
  const zatwierdzony = !!arkusz?.zatwierdzony && !ruszonePola && !ruszonyWynik && !odswiez;
  const pobierz = () =>
    pdf &&
    wykonaj(async () =>
      zapiszPlik(await pobierzArkuszPdf(token, proces.id), `arkusz-${proces.arkusz}-${osoba.nazwisko}.pdf`),
    );
  function zapisz(zatwierdz: boolean) {
    if (!arkusz || !moznaProwadzic || zlaData || odswiez || (zatwierdz && brak)) return;
    return wykonaj(async () => {
      setArkusz(await zapiszArkusz(token, proces.id, pola, zatwierdz));
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
        podpis={arkusz?.komunikat_podpis ?? ""}
        onWstecz={onWstecz}
        dzieci={
          <>
            {daneWyniku && <DaneOkresowej {...daneWyniku} />}
            {arkusz && (
              <PolaWzoru
                formularz={arkusz}
                wartosci={pola}
                braki={braki}
                edycja={moznaProwadzic && !czekam}
                ustaw={(id, v) => setZmiany((p) => ({ ...p, [id]: v }))}
              />
            )}
          </>
        }
        bok={
          <>
            {daneWyniku ? (
              <BokOkresowej {...daneWyniku} />
            ) : (
              <>
                <Werdykt wynik={null} warunki={[]} />
                <p id="zapis-wyniku" tabIndex={-1}>
                  {bladWynikuApi}
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
                    setOdswiez(false);
                  })
                }
              >
                Wczytaj arkusz ponownie
              </button>
            )}
            {daneWyniku && (
              <div id="zapis-wyniku" tabIndex={-1}>
                {moznaProwadzic ? (
                  <button
                    type="button"
                    className="jasny"
                    disabled={czekam || brakiWyniku.length > 0}
                    onClick={() =>
                      wykonaj(async () => {
                        const w = await zapiszWynik(token, proces.id, {
                          ...daneWyniku.f,
                          dolacz_wniosek_o_stopien:
                            daneWyniku.wynik.czesc_iii.dostepna && daneWyniku.f.dolacz_wniosek_o_stopien,
                        });
                        setWynik(w);
                        setF(w.dane);
                        setOdswiez(true);
                        setArkusz(await pobierzArkusz(token, proces.id));
                        setOdswiez(false);
                      })
                    }
                  >
                    Zapisz wynik i terminy
                  </button>
                ) : (
                  <span className="meta">Wynik i terminy zapisuje przełożony.</span>
                )}
                {wynik?.zapisany && !ruszonyWynik && <span className="meta"> Wynik zapisany.</span>}
              </div>
            )}
            {moznaProwadzic && (
              <button
                type="button"
                className="jasny"
                disabled={!arkusz || czekam || zlaData || odswiez}
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
            <button type="button" className="link" onClick={onDalej}>
              {widok === "wynik" ? "Dalej: arkusz oceny" : "Dalej: wnioski rozwojowe"}
            </button>
            {ruszonePola && <span className="meta">Masz niezapisane zmiany w arkuszu.</span>}
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

export function Arkusz(props: Krok7Props) {
  return <Okresowa key={props.proces.id} {...props} widok="arkusz" />;
}
