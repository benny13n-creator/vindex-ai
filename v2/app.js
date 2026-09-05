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
import { montirajProstorPredmeti } from "./features/predmeti/prostor.js";
import { montirajPredmetProstor } from "./features/dosije/prostor.js";
import { montirajPretragu } from "./features/pretraga/view.js";
import { montirajZnanje } from "./features/znanje/view.js";
import { montirajKancelariju } from "./features/kancelarija/view.js";

/** Prostori izgradjeni u ovoj verziji. Raste sa kapijama, nikad unapred. */
export const IZGRADJENI = ["danas", "predmeti", "znanje", "kancelarija"];

export function pokreniAplikaciju(koren) {
  const glavni = montirajLjusku(koren, { izgradjeni: IZGRADJENI });

  registruj("danas", montirajDanas);
  // Prostor PREDMETI sam razresava radnje u sebi (`/predmeti/nov`).
  registruj("predmeti", montirajProstorPredmeti);
  // `predmet` je OBJEKAT, ne prostor: ne pojavljuje se u globalnoj navigaciji,
  // ali ima sopstvenu rutu `/app-v2/predmet/<id>` da deep link i back rade.
  registruj("predmet", montirajPredmetProstor);
  // Pretraga je UTILITY, ne prostor: ima rutu, nema mesto u globalnoj navigaciji.
  registruj("znanje", montirajZnanje);
  registruj("kancelarija", montirajKancelariju);
  registruj("pretraga", montirajPretragu);
  postaviPodrazumevani("danas");

  pokreni(glavni);
}
