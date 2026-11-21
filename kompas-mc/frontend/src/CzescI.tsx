import { useState } from "react";
import { pobierzCzescIPdf, zapiszZapoznanie, type EtapOsoby, type ProcesOceny, type WyborKroku2 } from "./api";
import { opisBledu } from "./Krok1";
import { PoleDaty, poprawnaData, zapiszPlik } from "./Wynik";
import { data } from "./zespol-dane";

// Zagadnienia rozmowy na początku okresu, rozp. 2016 § 5 ust. 1 pkt 1–4.
const ZAGADNIENIA = [
  "główne obowiązki z opisu stanowiska",
  "kryteria obowiązkowe i wybrane dodatkowe",
  "Twoje oczekiwania co do spełniania kryteriów",
  "cele na okres oceny, jeśli ich wyznaczenie jest uzasadnione",
];

/** Zakończenie części I arkusza oceny okresowej: PDF do podpisu i zapisana data rozmowy i zapoznania
 *  z kryteriami (rozp. 2016 § 5 ust. 1 i 3, § 6). Na końcu okresu („ocena”) część I już istnieje
 *  na papierze, więc przełożony przepisuje z niej datę i przechodzi do rozmowy oceniającej. */
export function ZakonczenieCzesciI({
  token,
  proces,
  wybor,
  cykl,
  moznaProwadzic,
  onZapisano,
  onDalej,
  onPracownik,
}: {
  token: string;
  proces: ProcesOceny;
  wybor: WyborKroku2;
  cykl: EtapOsoby | null;
  moznaProwadzic: boolean;
  onZapisano: (p: ProcesOceny) => void;
  onDalej: () => void;
  onPracownik: () => void;
}) {
  const naKoncuOkresu = cykl?.etap === "ocena";
  const [dataZapoznania, setData] = useState<string | null>(wybor.zapoznanie ?? new Date().toLocaleDateString("sv-SE"));
  const [czekam, setCzekam] = useState(false);
  const [drukuje, setDrukuje] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const zakonczona = Boolean(wybor.zapoznanie);
  const dodatkowe = wybor.kryteria.filter((k) => k.rodzaj === "DODATKOWE").length;

  async function zapisz() {
    if (!dataZapoznania) return;
    setCzekam(true);
    setBlad(null);
    try {
      onZapisano(await zapiszZapoznanie(token, proces.id, dataZapoznania));
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  async function drukuj() {
    setDrukuje(true);
    setBlad(null);
    try {
      zapiszPlik(await pobierzCzescIPdf(token, proces.id), `arkusz-${proces.arkusz}-${proces.id}-czesc-I.pdf`);
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setDrukuje(false);
    }
  }

  return (
    <div className="k2-ustalone czesc-i" role="status">
      <h2>{zakonczona ? "Część I arkusza zakończona" : "Zakończ część I arkusza"}</h2>
      <p className="meta">
        {wybor.kryteria.length - dodatkowe} kryteriów obowiązkowych
        {dodatkowe > 0 && ` i ${dodatkowe} dodatkowe`}
        {cykl?.termin && ` · ${cykl.termin.nazwa} do ${data(cykl.termin.data)}`}
      </p>
      {naKoncuOkresu ? (
        <p className="meta">
          Część I sporządzono na początku okresu oceny. Wpisz datę rozmowy i zapoznania z kryteriami z podpisanej części I.
        </p>
      ) : (
        <div>
          <p className="meta">Na rozmowie z ocenianym omów (§ 5 ust. 1):</p>
          <ul className="oc-pytania">
            {ZAGADNIENIA.map((z) => (
              <li key={z}>{z}</li>
            ))}
          </ul>
        </div>
      )}
      {zakonczona ? (
        <p className="sukces">
          Rozmowa i zapoznanie z kryteriami: {data(wybor.zapoznanie as string)}. Oryginał arkusza trafia do akt osobowych, kopię
          części I doręczasz ocenianemu (§ 6 ust. 3).
        </p>
      ) : (
        moznaProwadzic && (
          <PoleDaty nazwa="Data rozmowy i zapoznania z kryteriami (§ 6 ust. 2)" wartosc={dataZapoznania} onZmiana={setData} />
        )
      )}
      {blad && <p className="blad">{blad}</p>}
      <div className="k2-akcje">
        <button type="button" className="link k2-do-pracownika" onClick={onPracownik}>
          Wróć do pracownika
        </button>
        {cykl?.etap !== "brak_danych" && (
          <button type="button" className="jasny" disabled={drukuje} onClick={drukuj}>
            {drukuje ? "Przygotowuję PDF…" : "Pobierz część I do podpisu"}
          </button>
        )}
        {moznaProwadzic && !zakonczona && (
          <button type="button" disabled={czekam || !dataZapoznania || !poprawnaData(dataZapoznania)} onClick={zapisz}>
            {czekam ? "Zapisuję…" : "Zapisz i zakończ część I"}
          </button>
        )}
        {zakonczona && naKoncuOkresu && (
          <button type="button" onClick={onDalej}>
            Dalej: rozmowa oceniająca
          </button>
        )}
      </div>
    </div>
  );
}
