/* Vindex V2 — boot.
 *
 * Redosled je obavezan i namerno spor na pravom mestu:
 *
 *   1. dokument (bez poslovnog sadrzaja)
 *   2. sesija
 *   3. ako nema sesije  -> kanonska prijava
 *   4. /api/plan/status -> kanonski izvor prava
 *   5. v2_pristup?
 *   6. tek tada montiranje aplikacije
 *   7. tek tada prvi poslovni poziv (Predmeti)
 *
 * Sto se u ovom fajlu NE radi: ne donosi se bezbednosna odluka. `v2_pristup`
 * je rollout kapija, ne zamena za autorizaciju — svaki poslovni endpoint iza
 * ovoga i dalje proverava sopstvene dozvole na serveru. Kada bi neko obrisao
 * ovu proveru u pretrazivacu, dobio bi ekran bez podataka, ne podatke.
 *
 * Korisniku se NIKAD ne prikazuje naziv kapije, broj statusa ni rec „rollout".
 */

import { razresiSesiju, naPrijavu } from "./platform/auth.js";
import { dohvati } from "./platform/http.js";
import { VRSTA } from "./platform/errors.js";
import { greska as logGreska } from "./platform/log.js";
import { pokreniAplikaciju } from "./app.js";

const KOREN_ID = "v2-koren";
const LEGACY = "/app";

function porukaBoot(tekst) {
  const koren = document.getElementById(KOREN_ID);
  if (!koren) return;
  koren.dataset.faza = "poruka";
  koren.replaceChildren();
  const okvir = document.createElement("div");
  okvir.className = "v2-boot";
  const p = document.createElement("p");
  p.className = "v2-boot__tekst";
  p.setAttribute("role", "status");
  p.textContent = tekst;
  okvir.appendChild(p);
  koren.appendChild(okvir);
}

/** Nudi legacy Vindex bez pominjanja kapije. Neutralno, bez „uskoro". */
function naLegacy() {
  window.location.replace(LEGACY);
}

async function boot() {
  const koren = document.getElementById(KOREN_ID);
  if (!koren) return;

  // 2–3. Sesija
  let sesija;
  try {
    sesija = await razresiSesiju();
  } catch (e) {
    sesija = null;
  }
  if (!sesija) { naPrijavu(); return; }

  // 4. Kanonski izvor prava. Ovo NIJE poslovni podatak — nema predmeta,
  //    klijenata ni dokumenata; samo stanje naloga.
  let stanje;
  try {
    stanje = await dohvati("/api/plan/status");
  } catch (e) {
    if (e && e.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
    if (e && e.vrsta === VRSTA.ZABRANJENO) { naLegacy(); return; }
    logGreska("boot: stanje naloga nije dostupno", e && e.vrsta);
    porukaBoot("Vindex trenutno nije dostupan. Pokušajte ponovo za koji trenutak.");
    return;
  }

  // 5–6. Kapija. Fail-closed: sve sto nije tacno `true` je nedostupno.
  if (!stanje || stanje.v2_pristup !== true) { naLegacy(); return; }

  koren.dataset.faza = "aplikacija";
  pokreniAplikaciju(koren);
}

// Service worker je iskljucen za /app-v2 u `static/sw.js`. Stariji SW koji je
// vec instaliran kod korisnika to jos ne zna, pa ga ovde guramo da se azurira.
// Bez ovoga bi prvi offline pokusaj na /app-v2 kod takvog korisnika i dalje
// mogao dobiti legacy dokument.
function osveziServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.getRegistration("/")
    .then(reg => { if (reg) reg.update(); })
    .catch(() => { /* nedostupan SW ne sme da obori boot */ });
}

osveziServiceWorker();
boot();
