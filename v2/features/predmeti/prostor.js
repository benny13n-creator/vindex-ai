/* Vindex V2 — prostor PREDMETI: registar i radnje u njemu.
 *
 * Ruter zna za prostore i za jedan parametar u putanji. Sve dublje od toga je
 * posao prostora — zato ovde, a ne u ruteru, stoji odluka sta znaci
 * `/app-v2/predmeti/nov`.
 *
 * Kontekst se deli po pod-ekranu: registar pamti svoju pretragu i stranu, a
 * zapoceta forma pamti sta je otkucano. Da dele jedan slot, prelazak sa forme
 * na registar bi obrisao jedno ili drugo.
 */

import { montirajPredmete } from "./view.js";
import { montirajNovPredmet } from "./nov.js";
import { montirajAkt } from "./akt.js";

const RADNJE = { nov: montirajNovPredmet, akt: montirajAkt };

export function montirajProstorPredmeti(kontejner, kontekst, param) {
  const svi = kontekst || {};
  const kljuc = RADNJE[param] ? param : "registar";
  const montiraj = RADNJE[param] || montirajPredmete;

  const ciklus = montiraj(kontejner, svi[kljuc] || null);
  const sopstveni = ciklus.kontekst;
  ciklus.kontekst = () => {
    const noviSvi = Object.assign({}, svi);
    try { noviSvi[kljuc] = sopstveni ? sopstveni() : null; } catch (e) { /* nebitno */ }
    return noviSvi;
  };
  return ciklus;
}
