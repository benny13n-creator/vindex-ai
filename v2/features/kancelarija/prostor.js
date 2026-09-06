/* Vindex V2 — prostor KANCELARIJA.
 *
 * Tri pogleda, jedan prostor:
 *   /app-v2/kancelarija            -> nalog, klijenti, naplata, tim
 *   /app-v2/kancelarija/finansije  -> sta je naplaceno, sta duguju, sta nije
 *                                     fakturisano, godisnji pregled
 *   /app-v2/kancelarija/tarife     -> satnica i Advokatska tarifa
 *
 * Finansije i Tarife NISU novi prostori i nemaju stavku u globalnoj
 * navigaciji. Legacy ima zasebne sidebar stavke za izvestaje i tarife, ali
 * to nije dokaz da V2 treba nove destinacije — sposobnost se prenosi,
 * informaciona arhitektura ne.
 */

import { montirajKancelariju } from "./view.js";
import { montirajFinansije } from "./finansije.js";
import { montirajTarife } from "./tarife.js";

const RADNJE = { finansije: montirajFinansije, tarife: montirajTarife };

export function montirajProstorKancelarija(kontejner, kontekst, param) {
  const svi = kontekst || {};
  const kljuc = RADNJE[param] ? param : "kancelarija";
  const montiraj = RADNJE[param] || montirajKancelariju;

  const ciklus = montiraj(kontejner, svi[kljuc] || null);
  const sopstveni = ciklus.kontekst;
  ciklus.kontekst = () => {
    const noviSvi = Object.assign({}, svi);
    try { noviSvi[kljuc] = sopstveni ? sopstveni() : null; } catch (e) { /* nebitno */ }
    return noviSvi;
  };
  return ciklus;
}
