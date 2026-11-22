import { useSyncExternalStore } from "react";
import { Wydra } from "./wydra/Wydra";

const telefon = matchMedia("(max-width: 760px)");
const sledz = (zmiana: () => void) => {
  telefon.addEventListener("change", zmiana);
  return () => telefon.removeEventListener("change", zmiana);
};

/** Treść zadania pkt 2: „System nie ma być dostępny na smartfonach.” Do 760 px style.css ukrywa
 *  aplikację razem z logowaniem, a ten ekran pojawia się w DOM tylko wtedy (bez drugiego h1 na
 *  komputerze). Aplikacja zostaje zamontowana, więc zwężenie okna nie gubi jej stanu (#77). */
export function TylkoKomputer() {
  const naTelefonie = useSyncExternalStore(sledz, () => telefon.matches);
  if (!naTelefonie) return null;
  return (
    <main className="tylko-komputer">
      <Wydra poza="stoi" szerokosc={120} naStart="machanie" />
      <h1>Kompas działa na komputerze</h1>
      <p>Otwórz go w przeglądarce na komputerze.</p>
    </main>
  );
}
