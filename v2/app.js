/* Vindex V2 — montiranje aplikacije.
 *
 * Poziva se TEK kada su sesija i pravo pristupa razreseni (boot.js).
 *
 * `IZGRADJENI` je jedini spisak prostora koji stvarno postoje u ovoj verziji.
 * Prostor se ovde dodaje kada njegova kapija prodje — ne ranije. Zbog toga u
 * navigaciji nema nijedne stavke koja ne vodi nikuda.
 *
 * Podrazumevani prostor posle prijave je DANAS, jer prvo pitanje advokata
 * ujutru nije „gde su moji predmeti" nego „sta me danas ceka".
 */

import { montirajLjusku } from "./shell/shell.js";
import { registruj, pokreni, postaviPodrazumevani } from "./platform/router.js";
import { montirajDanas } from "./features/danas/view.js";
import { montirajPredmete } from "./features/predmeti/view.js";
import { montirajDosije } from "./features/dosije/view.js";
import { montirajPretragu } from "./features/pretraga/view.js";

/** Prostori izgradjeni u ovoj verziji. Raste sa kapijama, nikad unapred. */
export const IZGRADJENI = ["danas", "predmeti"];

export function pokreniAplikaciju(koren) {
  const glavni = montirajLjusku(koren, { izgradjeni: IZGRADJENI });

  registruj("danas", montirajDanas);
  registruj("predmeti", montirajPredmete);
  // `predmet` je OBJEKAT, ne prostor: ne pojavljuje se u globalnoj navigaciji,
  // ali ima sopstvenu rutu `/app-v2/predmet/<id>` da deep link i back rade.
  registruj("predmet", montirajDosije);
  // Pretraga je UTILITY, ne prostor: ima rutu, nema mesto u globalnoj navigaciji.
  registruj("pretraga", montirajPretragu);
  postaviPodrazumevani("danas");

  pokreni(glavni);
}
