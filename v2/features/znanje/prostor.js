/* Vindex V2 — prostor ZNANJE: propisi i sudska praksa.
 *
 * Tri pitanja, jedan prostor:
 *   /app-v2/znanje         -> sta kaze propis (RAG nad zakonskim korpusom)
 *   /app-v2/znanje/praksa  -> sta je sud vec presudio
 *   /app-v2/znanje/rokovi  -> do kada (zastarelost i procesni rokovi)
 *
 * Praksa NIJE peti prostor i nema stavku u globalnoj navigaciji. Legacy ima
 * „Sudska praksa" kao zaseban sidebar item, ali to nije dokaz da V2 treba
 * novu destinaciju — sposobnost se prenosi, informaciona arhitektura ne.
 *
 * Kontekst se deli po pod-ekranu: pitanje o propisu i pretraga prakse pamte
 * se odvojeno, pa prelazak sa jednog na drugo ne brise ono sto je otkucano.
 */

import { montirajZnanje } from "./view.js";
import { montirajPraksu } from "./praksa.js";
import { montirajRokove } from "./rokovi.js";

const RADNJE = { praksa: montirajPraksu, rokovi: montirajRokove };

export function montirajProstorZnanje(kontejner, kontekst, param) {
  const svi = kontekst || {};
  const kljuc = RADNJE[param] ? param : "propisi";
  const montiraj = RADNJE[param] || montirajZnanje;

  const ciklus = montiraj(kontejner, svi[kljuc] || null);
  const sopstveni = ciklus.kontekst;
  ciklus.kontekst = () => {
    const noviSvi = Object.assign({}, svi);
    try { noviSvi[kljuc] = sopstveni ? sopstveni() : null; } catch (e) { /* nebitno */ }
    return noviSvi;
  };
  return ciklus;
}
