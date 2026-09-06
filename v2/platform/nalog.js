/* Vindex V2 — stanje naloga zapamceno pri pokretanju.
 *
 * `/api/plan/status` ima granicu od 60 poziva na sat i boot ga vec zove kao
 * KANONSKI izvor prava. Zvati ga ponovo iz Kancelarije znacilo bi trositi
 * istu granicu za podatak koji je vec u ruci — a advokat koji nekoliko puta
 * otvori Kancelariju zavrsio bi zakljucan iz sopstvene aplikacije.
 *
 * Ovde se cuva ono sto je boot vec procitao. Ako nista nije zapamceno,
 * `procitajPlan()` vraca `null` i ekran to KAZE — ne izmislja plan.
 */

let zapamceno = null;

export function zapamtiPlan(stanje) {
  zapamceno = stanje && typeof stanje === "object" ? stanje : null;
}

export function procitajPlan() {
  return zapamceno;
}
