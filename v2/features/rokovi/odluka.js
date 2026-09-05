/* Vindex V2 — odluka o predlozenom roku.
 *
 * Jedna kontrola za ceo proizvod: predlozen rok se potvrdjuje ili odbija na
 * isti nacin u Danas i u Dosijeu. Dve implementacije bi znacile dve
 * mogucnosti da se ista pravna radnja ponasa razlicito.
 *
 * STA POTVRDA JESTE, A STA NIJE (backend to izricito kaze, pa i ekran mora):
 * potvrda NE tvrdi da je rok cinjenicno tacan — tvrdi da ga je covek video i
 * prihvatio za upotrebu. Tek posle nje rok sme da pokrene podsetnik i sme da
 * bude prikazan klijentu. Zato tekst kontrole govori o preuzimanju
 * odgovornosti, ne o „tacnosti".
 *
 * ODBIJANJE NE BRISE. Odbijen rok ostaje u hronologiji sa stanjem `odbijen`;
 * ne pokrece nista i ne prikazuje se klijentu. Ekran to i kaze, jer bi
 * „Obriši" bila neistina o tome sta se desilo sa podatkom.
 *
 * NEUSPEH JE TIH SAMO AKO SE PRECUTI. Backend na neuspeo upis odluke vraca
 * 503 sa porukom da rok OSTAJE nepotvrdjen. Ta razlika se prenosi doslovno:
 * red se vraca u pocetno stanje, a ne prikazuje se kao razresen.
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu } from "../../platform/auth.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

/**
 * @param {object} rok        { id, opis }
 * @param {object} ciklus     zivotni ciklus ekrana (za slusaoce i prekidac)
 * @param {(ishod:{id:string,odluka:"potvrdjen"|"odbijen"})=>void} naOdluku
 * @returns {HTMLElement} kontrola koja se ubacuje u red roka
 */
export function kontrolaOdluke(rok, ciklus, naOdluku) {
  const omot = el("span", "v2-odluka");

  const potvrdi = el("button", "v2-dugme v2-dugme--sitno", "Potvrdi");
  potvrdi.type = "button";
  potvrdi.setAttribute("aria-label", "Potvrdi rok: " + rok.opis);

  const odbij = el("button", "v2-dugme v2-dugme--sitno v2-dugme--opasno", "Odbij");
  odbij.type = "button";
  odbij.setAttribute("aria-label", "Odbij rok: " + rok.opis);

  const stanje = el("span", "v2-odluka__stanje");
  stanje.setAttribute("role", "status");
  stanje.hidden = true;

  omot.append(potvrdi, odbij, stanje);

  let radi = false;

  function zakljucaj(na) {
    radi = na;
    potvrdi.disabled = na;
    odbij.disabled = na;
  }

  function javi(tekst, greska) {
    stanje.className = "v2-odluka__stanje" + (greska ? " v2-odluka__stanje--greska" : "");
    stanje.textContent = tekst;
    stanje.hidden = false;
  }

  async function odluci(putanja, imeRadnje, ishod) {
    if (radi) return;
    zakljucaj(true);
    javi("Beleži se…", false);
    const prekidac = ciklus.prekidac();
    try {
      await posalji(`/api/rokovi/${encodeURIComponent(rok.id)}/${putanja}`,
                    { telo: {}, signal: prekidac.signal });
    } catch (e) {
      if (jePrekid(e) || ciklus.ugasen) return;
      zakljucaj(false);
      if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      // Backend na 503 izricito kaze da rok OSTAJE nepotvrdjen. Prenosimo to,
      // umesto uopstenog „greska" posle kojeg advokat ne zna sta je stanje.
      javi(imeRadnje + " nije zabeleženo. Rok ostaje nepotvrđen. " + porukaZaKorisnika(e), true);
      return;
    }
    if (ciklus.ugasen) return;
    potvrdi.remove();
    odbij.remove();
    javi(ishod === "potvrdjen" ? "Potvrđeno." : "Odbijeno — ostaje u hronologiji.", false);
    if (typeof naOdluku === "function") naOdluku({ id: rok.id, odluka: ishod });
  }

  ciklus.slusaj(potvrdi, "click", () => odluci("potvrdi", "Potvrđivanje", "potvrdjen"));
  ciklus.slusaj(odbij, "click", () => odluci("odbij", "Odbijanje", "odbijen"));

  return omot;
}
