/* Vindex V2 — prostor DANAS: pregled dana i kalendar.
 *
 *   /app-v2/danas           sta trazi moju paznju
 *   /app-v2/danas/kalendar  sta me ceka
 *
 * Kalendar nije peti prostor: to je drugo pitanje nad istim izvorima.
 * Kontekst se deli po pod-ekranu, pa izbor prozora u kalendaru prezivi
 * odlazak na Danas i natrag.
 */

import { montirajDanas } from "./view.js";
import { montirajKalendar } from "./kalendar.js";
import { montirajBrifing } from "./brifing.js";
import { montirajObavestenja } from "./obavestenja.js";

const RADNJE = { kalendar: montirajKalendar, brifing: montirajBrifing,
                 obavestenja: montirajObavestenja };

export function montirajProstorDanas(kontejner, kontekst, param) {
  const svi = kontekst || {};
  const kljuc = RADNJE[param] ? param : "pregled";
  const montiraj = RADNJE[param] || montirajDanas;

  const ciklus = montiraj(kontejner, svi[kljuc] || null);
  const sopstveni = ciklus.kontekst;
  ciklus.kontekst = () => {
    const noviSvi = Object.assign({}, svi);
    try { noviSvi[kljuc] = sopstveni ? sopstveni() : null; } catch (e) { /* nebitno */ }
    return noviSvi;
  };
  return ciklus;
}
