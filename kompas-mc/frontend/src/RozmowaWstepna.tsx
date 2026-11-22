import { useEffect, useState } from "react";
import { pobierzPdfPierwszej, pobierzPierwsza, zapiszPierwsza, type StanPierwszejOceny, type Termin } from "./api";
import { PoleDaty, bladWyniku, poprawnaData, zapiszPlik } from "./Wynik";
import { data } from "./zespol-dane";

const dzisIso = () => new Date().toLocaleDateString("sv-SE");
const dzien = (s: StanPierwszejOceny, klucz: string) => (s.terminy[klucz] as Termin | null | undefined)?.data ?? null;

/** Koniec kroku 2 w pierwszej ocenie: rozmowa wstępna wyznacza termin sprawozdania i kończy się podpisem
 *  części I–II arkusza (rozp. 2015 § 3–4, arkusz pierwszej oceny, sekcja „Rozmowa wstępna”). */
export function RozmowaWstepna({
  token,
  procesId,
  moznaProwadzic,
  onPracownik,
}: {
  token: string;
  procesId: number;
  moznaProwadzic: boolean;
  onPracownik: () => void;
}) {
  const [stan, setStan] = useState<StanPierwszejOceny | null>(null);
  const [dataRozmowy, setDataRozmowy] = useState<string | null>(null);
  const [koniec, setKoniec] = useState<string | null>(null);
  const [pracuje, setPracuje] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    pobierzPierwsza(token, procesId)
      .then((s) => {
        setStan(s);
        setDataRozmowy(s.dane.data_rozmowy_wstepnej ?? (s.terminy.data_rozmowy_wstepnej as string | null) ?? dzisIso());
        setKoniec(s.dane.wyznaczony_termin_sprawozdania ?? dzien(s, "termin_sprawozdania_od"));
      })
      .catch((err) => setBlad(bladWyniku(err)));
  }, [token, procesId]);

  const rozmowa = stan?.terminy.data_rozmowy_wstepnej as string | null | undefined;
  const sprawozdanieOd = stan && dzien(stan, "termin_sprawozdania_od");
  const sprawozdanieDo = stan && dzien(stan, "termin_sprawozdania_do");
  const ocenaDo = stan && dzien(stan, "pierwsza_ocena_do");
  const zapisane = !!rozmowa && !!sprawozdanieDo;
  // Daty RRRR-MM-DD porównują się jak tekst. Komunikat zanim zapytamy API, bez języka „okna”.
  const pozaZakresem = !!koniec && poprawnaData(koniec) && ((!!sprawozdanieOd && koniec < sprawozdanieOd) || (!!ocenaDo && koniec > ocenaDo));
  const gotowe = !!dataRozmowy && !!koniec && poprawnaData(dataRozmowy) && poprawnaData(koniec) && !pozaZakresem;

  async function drukuj(s: StanPierwszejOceny) {
    zapiszPlik(await pobierzPdfPierwszej(token, s.proces_id, "rozmowa-wstepna.pdf"), `pierwsza-ocena-${s.proces_id}-rozmowa-wstepna.pdf`);
  }

  async function wykonaj() {
    if (!stan) return;
    setPracuje(true);
    setBlad(null);
    try {
      if (zapisane) {
        await drukuj(stan);
        return;
      }
      const s = await zapiszPierwsza(token, procesId, { ...stan.dane, data_rozmowy_wstepnej: dataRozmowy, wyznaczony_termin_sprawozdania: koniec }, false);
      setStan(s);
      await drukuj(s);
      // Karol 02:04: po zapisie i wydruku wracamy do karty, gdzie następnym krokiem jest sprawozdanie (#99).
      onPracownik();
    } catch (err) {
      setBlad(bladWyniku(err));
    } finally {
      setPracuje(false);
    }
  }

  return (
    <div className="k2-ustalone" role="status">
      {zapisane ? (
        <p className="sukces">
          <strong>Rozmowa wstępna {data(rozmowa)}</strong>
          {sprawozdanieOd && ` · sprawozdanie od ${data(sprawozdanieOd)} do ${data(sprawozdanieDo)}`}
        </p>
      ) : (
        stan && (
          <>
            {moznaProwadzic && (
              <div className="siatka-dat">
                <PoleDaty nazwa="Data rozmowy wstępnej" wartosc={dataRozmowy} onZmiana={setDataRozmowy} />
                <PoleDaty nazwa="Termin sprawozdania pracownika" wartosc={koniec} onZmiana={setKoniec} />
              </div>
            )}
            <p className={pozaZakresem ? "blad" : "meta"}>
              Termin sprawozdania wyznaczasz na rozmowie (§ 3 pkt 4)
              {sprawozdanieOd && `: najwcześniej ${data(sprawozdanieOd)}, po 8 miesiącach pracy`}
              {ocenaDo && `, najpóźniej ${data(ocenaDo)}, żeby zdążyć z oceną`}.
            </p>
          </>
        )
      )}
      <div className="k2-akcje">
        <button type="button" className="link k2-do-pracownika" onClick={onPracownik}>
          Wróć do pracownika
        </button>
        {moznaProwadzic && stan && (
          <button
            type="button"
            disabled={pracuje || (!zapisane && !gotowe)}
            onClick={wykonaj}
          >
            {pracuje ? "Przygotowuję PDF…" : zapisane ? "Wydrukuj części I–II do podpisu" : "Zapisz i wydrukuj części I–II"}
          </button>
        )}
      </div>
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}
