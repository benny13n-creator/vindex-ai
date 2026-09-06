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
import { montirajProstorDanas } from "./features/danas/prostor.js";
import { montirajProstorPredmeti } from "./features/predmeti/prostor.js";
import { montirajPredmetProstor } from "./features/dosije/prostor.js";
import { montirajPretragu } from "./features/pretraga/view.js";
import { montirajProstorZnanje } from "./features/znanje/prostor.js";
import { montirajProstorKancelarija } from "./features/kancelarija/prostor.js";
import { montirajUskladjenost } from "./features/uskladjenost/view.js";
import { montirajProstorKlijent } from "./features/klijent/view.js";

/** Prostori izgradjeni u ovoj verziji. Raste sa kapijama, nikad unapred. */
// „Uskladjenost" je IZGRADJENA, ali je uslovna: da li se vidi odlucuje
// `sme` iz boot-a, na osnovu prava naloga. Izgradjenost i pravo su dve
// razlicite odluke i namerno se ne mesaju (vidi domain/spaces.js).
export const IZGRADJENI = ["danas", "predmeti", "znanje", "kancelarija", "uskladjenost"];

export function pokreniAplikaciju(koren, { sme } = {}) {
  const glavni = montirajLjusku(koren, { izgradjeni: IZGRADJENI, sme });

  // Prostor DANAS sam razresava svoje radnje ().
  registruj("danas", montirajProstorDanas);
  // Prostor PREDMETI sam razresava radnje u sebi (`/predmeti/nov`).
  registruj("predmeti", montirajProstorPredmeti);
  // `predmet` je OBJEKAT, ne prostor: ne pojavljuje se u globalnoj navigaciji,
  // ali ima sopstvenu rutu `/app-v2/predmet/<id>` da deep link i back rade.
  registruj("predmet", montirajPredmetProstor);
  // `klijent` je takodje OBJEKAT: `/app-v2/klijent/<id>` i radnja
  // `/app-v2/klijent/nov`. Nema stavku u globalnoj navigaciji --
  // do klijenta se stize iz Kancelarije i iz pretrage.
  registruj("klijent", montirajProstorKlijent);
  // Prostor ZNANJE sam razresava svoje radnje ().
  registruj("znanje", montirajProstorZnanje);
  registruj("kancelarija", montirajProstorKancelarija);
  // Uslovni prostor se registruje SAMO ako nalog na njega ima pravo.
  // Da se registruje uvek, rucno otkucana putanja `/app-v2/uskladjenost`
  // otvorila bi ekran kome nalog ne sme da pristupi — kapija bi bila
  // samo u navigaciji, a ne u ruti. (Server i dalje proverava svoje
  // dozvole; ovo je da UI ne obeca ono sto backend odbija.)
  if (!sme || sme("uskladjenost")) registruj("uskladjenost", montirajUskladjenost);
  // Pretraga je UTILITY, ne prostor: ima rutu, nema mesto u globalnoj navigaciji.
  registruj("pretraga", montirajPretragu);
  postaviPodrazumevani("danas");

  pokreni(glavni);
}
