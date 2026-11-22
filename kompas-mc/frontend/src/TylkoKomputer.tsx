import { Wydra } from "./wydra/Wydra";

/** Treść zadania pkt 2: „System nie ma być dostępny na smartfonach.” Do 760 px style.css ukrywa
 *  aplikację razem z logowaniem i pokazuje tylko ten ekran; szerzej jest ukryty (#77). */
export function TylkoKomputer() {
  return (
    <main className="tylko-komputer">
      <Wydra poza="stoi" szerokosc={120} naStart="machanie" />
      <h1>Kompas działa na komputerze</h1>
      <p>Otwórz go w przeglądarce na komputerze.</p>
    </main>
  );
}
