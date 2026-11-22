# Wydra Kompasu · siedem stanów

Skopiuj pliki z tej paczki do `kompas-mc/frontend/src/wydra/`. Istniejące wywołania komponentu zachowują domyślną pozę i dotychczasowe właściwości. Poniższy przykład pokazuje skupioną wydrę. Kliknięcie uruchamia senność.

```tsx
<Wydra poza="sklada" naStart="skupienie" naKlik="sennosc" samoczynnie={false} />
```

| Poza | Ruch | Długość ruchu |
|---|---|---:|
| stoi | nasluchiwanie | 5,8 s |
| sklada | skupienie | 6,6 s |
| stoi | radosc | 5,2 s |
| sklada | sennosc | 7,8 s |
| stoi | machanie | 3,6 s |
| stoi | podskok | 3,0 s |
| prosi | proszenie | 4,4 s |

Każda nazwa ruchu jest także właściwością liczbową komponentu. Zmiana jej wartości na liczbę niezerową wyzwala ruch pasujący do bieżącej pozy. Podczas trwającego gestu komponent kończy bieżącą sekwencję.

Odtwarzacz używa źródłowej pozy 578 × 649 px i jednej tekstury powiek. Przebieg ruchów w sekundach opisuje funkcja `performanceAt` w `wydra-player.js`. W środowisku bez WebGL wydra zostaje w pozie spoczynkowej (zapasowe klipy WebP z paczki, ok. 23 MB, nie weszły do repozytorium). Preferencja ograniczenia ruchu zachowuje pozę spoczynkową.

Źródłem postaci są pliki PNG projektu harn0ld/Kompas-Kompetencji, rewizja c8b4464bfa643778283ffb7017a16fabcbb2c1e3, na warunkach podanych w LICENSE. Wbudowany ImageGen posłużył do wygenerowania detalu zamkniętych powiek. Teksturę dopasowano do obu ujęć głowy. Animacja korzysta z niej lokalnie w okolicach oczu.

## Polecenie do przygotowania powiek

Precise object edit for a character animation texture. Edit the attached two-panel reference in place. Keep exactly the two existing poses, framing, scale and the relative facial landmarks in each panel. In both panels close both eyes completely in a natural, relaxed blink. Soft rounded eyelids coated in the SAME warm brown fur as the forehead, very short soft fur at the lash line, a single subtle anatomically curved dark lash seam with gently lowered center, following the original eye tilt. No iris, whites or catchlights visible. No makeup. Preserve eyebrows, noses, mouths, fluffy muzzles, whiskers, ears, expression, warm 3D rendering, illumination and background exactly. The only change is the four closed eyelids. Keep both faces side by side as shown, no text, no outlines, no new details.
