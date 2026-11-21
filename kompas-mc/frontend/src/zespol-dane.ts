import type { Pracownik, ProcesOceny, Sciezka, TerminProcesu } from "./api";

/** Wspólne obliczenia pulpitu, zakładki Zespół i karty pracownika: wszystko z danych API, bez własnych reguł. */

export const data = (iso: string) => iso.slice(0, 10).split("-").reverse().join(".");

/** Komórka z QNT ma postać „Departament … / Wydział …”. */
export function podzial(komorka: string): { departament: string; wydzial: string } {
  const [departament, ...reszta] = komorka.split(" / ");
  return { departament, wydzial: reszta.join(" / ") || departament };
}

/** Pełne lata pracy od daty zatrudnienia do dziś. */
export function lataStazu(od: string, dzis = new Date()): number {
  const d = new Date(od);
  let lata = dzis.getFullYear() - d.getFullYear();
  if (dzis.getMonth() < d.getMonth() || (dzis.getMonth() === d.getMonth() && dzis.getDate() < d.getDate())) lata--;
  return Math.max(0, lata);
}

export function odmiana(n: number, jeden: string, kilka: string, wiele: string): string {
  if (n === 1) return jeden;
  const d = n % 10;
  const s = n % 100;
  return d >= 2 && d <= 4 && (s < 12 || s > 14) ? kilka : wiele;
}

export const osoby = (n: number) => `${n} ${odmiana(n, "osoba", "osoby", "osób")}`;
export const dni = (n: number) => `${n} ${odmiana(n, "dzień", "dni", "dni")}`;
export const lat = (n: number) => `${n} ${odmiana(n, "rok", "lata", "lat")}`;
export const stazTekst = (n: number) => (n < 1 ? "poniżej roku stażu" : `${lat(n)} stażu`);

export function kiedy(dniDo: number): string {
  if (dniDo < 0) return `${dni(-dniDo)} po terminie`;
  if (dniDo === 0) return "dziś";
  return `za ${dni(dniDo)}`;
}

export const NAZWA_SCIEZKI: Record<Sciezka, string> = { pierwsza: "pierwsza ocena", okresowa: "ocena okresowa" };

/** Stan oceny osoby: proces w toku, propozycja ścieżki z analizy kroku 1 albo brak. */
export interface Sprawa {
  osoba: Pracownik;
  proces: ProcesOceny | null;
  proponowana: Sciezka | null;
  termin: TerminProcesu | null;
}

export function nastepnyKrok(s: Sprawa): string {
  if (s.proces) return `Ocena w toku · krok ${s.proces.krok} z 8`;
  if (s.proponowana === "pierwsza") return "Rozpocznij pierwszą ocenę";
  if (s.proponowana === "okresowa") return "Rozpocznij ocenę okresową";
  return "Ustal ścieżkę oceny";
}

/** Grupy według departamentu i wydziału, w kolejności alfabetycznej. */
export function wedlugKomorek<T>(lista: T[], komorka: (x: T) => string) {
  const mapa = new Map<string, Map<string, T[]>>();
  for (const x of lista) {
    const { departament, wydzial } = podzial(komorka(x));
    const dep = mapa.get(departament) ?? new Map<string, T[]>();
    dep.set(wydzial, [...(dep.get(wydzial) ?? []), x]);
    mapa.set(departament, dep);
  }
  return [...mapa.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "pl"))
    .map(([departament, wydzialy]) => ({
      departament,
      wydzialy: [...wydzialy.entries()].sort(([a], [b]) => a.localeCompare(b, "pl")).map(([wydzial, ludzie]) => ({ wydzial, ludzie })),
    }));
}
