/* Vindex V2 — ljuska.
 *
 * Namerno mala. U Wave 1 postoji tacno jedan ekran, pa ljuska nosi samo ono
 * bez cega korisnik ne zna gde je:
 *   - da je u Vindexu
 *   - da je u Predmetima
 *   - koji je nalog prijavljen i kako izlazi
 *
 * Cega OVDE nema i zasto: bocne trake, i nijedne stavke za Danas / Znanje /
 * Kancelariju / Usklađenost. Onemogucena navigacija za module koji ne postoje
 * je mrtav UI koji obecava, a implicitno bi zakljucala buducu globalnu
 * navigaciju pre nego sto je iko odlucio kako izgleda (Z015 §15).
 *
 * Ljuska je CRNA scena pune sirine, sadrzaj ide u aplikacijsku PAPIR scenu.
 */

import { korisnik, PRIJAVA } from "../platform/auth.js";

export function montirajLjusku(koren) {
  koren.replaceChildren();
  koren.dataset.faza = "aplikacija";

  const app = document.createElement("div");
  app.className = "v2-app";

  // ── Crna scena: puna sirina, sadrzaj u meri ──
  const ljuska = document.createElement("header");
  ljuska.className = "v2-scena v2-scena--crna v2-ljuska";

  const red = document.createElement("div");
  red.className = "v2-scena__unutra v2-ljuska__red";

  const znak = document.createElement("span");
  znak.className = "v2-znak";
  znak.textContent = "Vindex";

  const odeljak = document.createElement("span");
  odeljak.className = "v2-ljuska__odeljak";
  odeljak.textContent = "Predmeti";
  odeljak.setAttribute("aria-current", "page");

  const nalog = document.createElement("div");
  nalog.className = "v2-ljuska__nalog";
  const k = korisnik();
  if (k && k.email) {
    const email = document.createElement("span");
    email.className = "v2-ljuska__email";
    email.title = k.email;
    email.textContent = k.email;
    nalog.appendChild(email);
  }
  const izlaz = document.createElement("a");
  izlaz.className = "v2-tekst-akcija";
  izlaz.href = PRIJAVA;
  izlaz.textContent = "Nalog";
  nalog.appendChild(izlaz);

  red.append(znak, odeljak, nalog);
  ljuska.appendChild(red);

  // ── Papir scena: puna sirina, ekran se montira unutra ──
  const glavni = document.createElement("main");
  glavni.className = "v2-scena v2-scena--papir v2-glavni";
  glavni.id = "v2-glavni";

  app.append(ljuska, glavni);
  koren.appendChild(app);

  return glavni;
}
