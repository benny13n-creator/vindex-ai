/* Vindex V2 — montiranje aplikacije.
 *
 * Ovo se poziva TEK kada su sesija i pravo pristupa razreseni (boot.js).
 * Do tada u DOM-u nema nijednog poslovnog podatka.
 */

import { montirajLjusku } from "./shell/shell.js";
import { registruj, pokreni } from "./platform/router.js";
import { montirajPredmete } from "./features/predmeti/view.js";

export function pokreniAplikaciju(koren) {
  const glavni = montirajLjusku(koren);
  registruj("predmeti", montirajPredmete);
  pokreni(glavni);
}
