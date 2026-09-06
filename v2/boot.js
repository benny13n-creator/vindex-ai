/* Vindex V2 — boot.
 *
 * Redosled je obavezan i namerno spor na pravom mestu:
 *
 *   1. dokument (bez poslovnog sadrzaja)
 *   2. sesija
 *   3. ako nema sesije  -> kanonska prijava
 *   4. /api/plan/status -> kanonski izvor prava
 *   5. v2_pristup?
 *   6. /api/me -> pravo na uslovni peti prostor (Usklađenost)
 *   7. tek tada montiranje aplikacije
 *   8. tek tada prvi poslovni poziv (Predmeti)
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
import { zapamtiPlan } from "./platform/nalog.js";

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
    // 429 se NE sme prikazati kao „Vindex nije dostupan": advokat tada misli
    // da je aplikacija pala i ponavlja pokusaj, cime ostaje zakljucan duze.
    porukaBoot(e && e.vrsta === VRSTA.PREVISE
      ? "Previše zahteva u kratkom roku. Sačekajte koji minut pa osvežite stranicu."
      : "Vindex trenutno nije dostupan. Pokušajte ponovo za koji trenutak.");
    return;
  }

  // 5–6. Kapija. Fail-closed: sve sto nije tacno `true` je nedostupno.
  if (!stanje || stanje.v2_pristup !== true) { naLegacy(); return; }

  // Stanje naloga se PAMTI: Kancelarija ga prikazuje bez novog poziva.
  // `/api/plan/status` ima granicu od 60 na sat, pa bi ponovni poziv iz
  // ekrana trosio istu granicu za podatak koji je vec procitan.
  zapamtiPlan(stanje);

  // 7. Uslovni peti prostor. `/api/plan/status` NE nosi pravo na digitalnu
  //    imovinu — nosi ga `/api/me`. Poziv je zaseban i NIJE blokirajuci:
  //    ako padne, Usklađenost se ne prikazuje, a ostatak aplikacije radi.
  //    FAIL-CLOSED: prostor za koji pravo nije DOKAZANO se ne prikazuje.
  let sme = () => true;
  try {
    const ja = await dohvati("/api/me");
    const daSme = !!(ja && ja.digitalna_imovina_aktivirano === true);
    sme = (kljuc) => (kljuc === "uskladjenost" ? daSme : true);
  } catch (e) {
    logGreska("boot: pravo na Usklađenost nije dokazano", e && e.vrsta);
    sme = (kljuc) => kljuc !== "uskladjenost";
  }

  koren.dataset.faza = "aplikacija";
  pokreniAplikaciju(koren, { sme });
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
